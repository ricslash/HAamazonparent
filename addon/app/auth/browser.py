"""Browser-based authentication manager using Playwright."""
import asyncio
import logging
import os
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

import aiohttp
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

_LOGGER = logging.getLogger(__name__)

# Stealth JS to inject into every page context
_STEALTH_JS = """
// Override navigator.webdriver
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

// Add chrome object
window.chrome = {
    runtime: {},
    loadTimes: function() {},
    csi: function() {},
    app: {}
};

// Override navigator.plugins
Object.defineProperty(navigator, 'plugins', {
    get: () => [1, 2, 3, 4, 5],
});

// Override navigator.languages
Object.defineProperty(navigator, 'languages', {
    get: () => ['en-US', 'en'],
});

// Override permissions query
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications' ?
        Promise.resolve({ state: Notification.permission }) :
        originalQuery(parameters)
);
"""


class ScheduledReauthManager:
    """Manages scheduled browser re-authentication to keep Amazon cookies fresh."""

    def __init__(
        self,
        storage,
        browser_auth_manager: "BrowserAuthManager",
        reauth_interval: int = 72000,
        health_check_interval: int = 14400,
        max_retries: int = 3,
        amazon_email: str = "",
        amazon_password: str = "",
    ):
        self._storage = storage
        self._browser_auth_manager = browser_auth_manager
        self._reauth_interval = reauth_interval
        self._health_check_interval = health_check_interval
        self._max_retries = max_retries
        self._amazon_email = amazon_email
        self._amazon_password = amazon_password

        self._reauth_task: Optional[asyncio.Task] = None
        self._health_task: Optional[asyncio.Task] = None
        self._last_reauth: Optional[datetime] = None
        self._last_reauth_result: str = "never"
        self._next_reauth: Optional[datetime] = None
        self._last_health_check: Optional[datetime] = None
        self._session_healthy: bool = False
        self._consecutive_failures: int = 0
        self._reauth_lock = asyncio.Lock()
        self._running: bool = False

    @property
    def credentials_configured(self) -> bool:
        return bool(self._amazon_email and self._amazon_password)

    def _randomized_interval(self) -> int:
        """Return reauth interval with ±1 hour jitter."""
        jitter = random.randint(-3600, 3600)
        return max(3600, self._reauth_interval + jitter)

    def start(self):
        """Start the reauth and health check background loops."""
        if self._running:
            return
        self._running = True
        self._reauth_task = asyncio.create_task(self._reauth_loop())
        self._health_task = asyncio.create_task(self._health_check_loop())
        _LOGGER.info(
            f"ScheduledReauthManager started (reauth_interval={self._reauth_interval}s, "
            f"health_check_interval={self._health_check_interval}s, "
            f"credentials={'configured' if self.credentials_configured else 'not configured'})"
        )

    async def stop(self):
        """Stop all background loops."""
        self._running = False
        for task in (self._reauth_task, self._health_task):
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._reauth_task = None
        self._health_task = None
        _LOGGER.info("ScheduledReauthManager stopped")

    async def trigger_reauth(self) -> dict:
        """Manually trigger an immediate re-authentication."""
        if not self.credentials_configured:
            return {"status": "error", "error": "Credentials not configured"}
        if self._reauth_lock.locked():
            return {"status": "already_running"}
        result = await self._execute_reauth_with_retries()
        return result

    async def trigger_health_check(self) -> dict:
        """Manually trigger an immediate health check."""
        return await self._do_health_check()

    async def _reauth_loop(self):
        """Background loop for scheduled re-authentication."""
        # On startup, check if cookies exist. If not, reauth immediately.
        # Otherwise, schedule first reauth after randomized interval.
        try:
            cookies_exist = await self._storage.check_exists()
        except Exception:
            cookies_exist = False

        if cookies_exist and self.credentials_configured:
            delay = self._randomized_interval()
            self._next_reauth = datetime.now(timezone.utc) + timedelta(seconds=delay)
            _LOGGER.info(f"Cookies exist. First reauth scheduled in {delay // 3600}h {(delay % 3600) // 60}m")
        elif self.credentials_configured:
            self._next_reauth = datetime.now(timezone.utc) + timedelta(seconds=30)
            _LOGGER.info("No cookies found. Scheduling reauth in 30s")
        else:
            _LOGGER.info("No credentials configured. Reauth loop will wait for manual auth.")
            # Still run the loop but just sleep and check periodically
            while self._running:
                await asyncio.sleep(60)
            return

        while self._running:
            try:
                now = datetime.now(timezone.utc)
                if self._next_reauth and now < self._next_reauth:
                    wait_seconds = (self._next_reauth - now).total_seconds()
                    await asyncio.sleep(min(wait_seconds, 60))
                    continue

                _LOGGER.info("Scheduled reauth triggered")
                await self._execute_reauth_with_retries()

                # Schedule next reauth
                delay = self._randomized_interval()
                self._next_reauth = datetime.now(timezone.utc) + timedelta(seconds=delay)
                _LOGGER.info(f"Next reauth scheduled in {delay // 3600}h {(delay % 3600) // 60}m")

            except asyncio.CancelledError:
                raise
            except Exception as e:
                _LOGGER.error(f"Reauth loop error: {e}")
                # Schedule retry after a shorter interval on unexpected errors
                self._next_reauth = datetime.now(timezone.utc) + timedelta(minutes=30)
                await asyncio.sleep(60)

    async def _health_check_loop(self):
        """Background loop for periodic health checks."""
        # Wait a bit on startup
        await asyncio.sleep(60)

        while self._running:
            try:
                result = await self._do_health_check()

                if result.get("status") == "expired" and self.credentials_configured:
                    _LOGGER.warning("Health check detected expired session, triggering immediate reauth")
                    if not self._reauth_lock.locked():
                        await self._execute_reauth_with_retries()
                        # Reset next scheduled reauth
                        delay = self._randomized_interval()
                        self._next_reauth = datetime.now(timezone.utc) + timedelta(seconds=delay)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                _LOGGER.error(f"Health check loop error: {e}")

            await asyncio.sleep(self._health_check_interval)

    async def _do_health_check(self) -> dict:
        """Perform a single health check against Amazon API."""
        try:
            cookies_exist = await self._storage.check_exists()
            if not cookies_exist:
                self._session_healthy = False
                self._last_health_check = datetime.now(timezone.utc)
                return {"status": "no_cookies"}

            cookies = await self._storage.load_cookies()

            cookie_header = "; ".join(
                f"{c['name']}={c.get('value', '')}" for c in cookies
            )

            csrf_token = ""
            for c in cookies:
                if c.get("name") == "ft-panda-csrf-token":
                    csrf_token = c.get("value", "")
                    break

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "Accept": "application/json, text/plain, */*",
                "Referer": "https://www.amazon.com/parentdashboard/",
                "Cookie": cookie_header,
                "x-amzn-csrf": csrf_token,
            }

            url = "https://www.amazon.com/parentdashboard/ajax/get-household"

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    self._last_health_check = datetime.now(timezone.utc)

                    if resp.status == 200:
                        self._session_healthy = True
                        _LOGGER.info("Health check: session healthy (HTTP 200)")
                        return {"status": "healthy", "http_status": 200}

                    elif resp.status in (401, 403):
                        self._session_healthy = False
                        _LOGGER.warning(f"Health check: session expired (HTTP {resp.status})")
                        return {"status": "expired", "http_status": resp.status}

                    else:
                        _LOGGER.warning(f"Health check: unexpected status {resp.status}")
                        return {"status": "error", "http_status": resp.status}

        except Exception as e:
            self._session_healthy = False
            self._last_health_check = datetime.now(timezone.utc)
            _LOGGER.error(f"Health check failed: {e}")
            return {"status": "error", "error": str(e)}

    async def _execute_reauth_with_retries(self) -> dict:
        """Execute re-authentication with retry logic."""
        if not self.credentials_configured:
            return {"status": "error", "error": "Credentials not configured"}

        async with self._reauth_lock:
            retry_delays = [300, 900, 1800]  # 5min, 15min, 30min

            for attempt in range(self._max_retries):
                try:
                    _LOGGER.info(f"Reauth attempt {attempt + 1}/{self._max_retries}")
                    success = await self._browser_auth_manager.perform_stealth_reauth(
                        self._amazon_email, self._amazon_password
                    )

                    if success:
                        self._last_reauth = datetime.now(timezone.utc)
                        self._last_reauth_result = "success"
                        self._session_healthy = True
                        self._consecutive_failures = 0
                        _LOGGER.info("Reauth succeeded")
                        return {"status": "success", "attempt": attempt + 1}

                    _LOGGER.warning(f"Reauth attempt {attempt + 1} failed")

                except Exception as e:
                    _LOGGER.error(f"Reauth attempt {attempt + 1} error: {e}")

                self._consecutive_failures += 1

                if attempt < self._max_retries - 1:
                    delay = retry_delays[min(attempt, len(retry_delays) - 1)]
                    _LOGGER.info(f"Waiting {delay}s before retry...")
                    await asyncio.sleep(delay)

            self._last_reauth_result = "failed"
            _LOGGER.error(f"Reauth failed after {self._max_retries} attempts")
            return {"status": "failed", "attempts": self._max_retries}

    def get_status(self) -> dict:
        """Return current reauth manager status."""
        reauth_interval_hours = round(self._reauth_interval / 3600, 1)
        return {
            "session_healthy": self._session_healthy,
            "last_reauth": (
                self._last_reauth.isoformat() if self._last_reauth else None
            ),
            "last_reauth_result": self._last_reauth_result,
            "next_reauth": (
                self._next_reauth.isoformat() if self._next_reauth else None
            ),
            "last_health_check": (
                self._last_health_check.isoformat() if self._last_health_check else None
            ),
            "consecutive_failures": self._consecutive_failures,
            "credentials_configured": self.credentials_configured,
            "reauth_interval_hours": reauth_interval_hours,
        }


class BrowserAuthManager:
    """Manages browser-based authentication sessions."""

    def __init__(self, auth_timeout: int = 300):
        """Initialize browser auth manager."""
        self._sessions: Dict[str, Dict] = {}
        self._playwright = None
        self._auth_timeout = auth_timeout

    async def initialize(self):
        """Initialize Playwright."""
        try:
            self._playwright = await async_playwright().start()
            _LOGGER.info("Playwright initialized successfully")
        except Exception as e:
            _LOGGER.error(f"Failed to initialize Playwright: {e}")
            raise

    # --- Stealth helpers ---

    async def _human_delay(self, min_ms: int = 500, max_ms: int = 2000):
        """Sleep for a random duration to mimic human timing."""
        delay = random.randint(min_ms, max_ms) / 1000.0
        await asyncio.sleep(delay)

    async def _human_type(self, page: Page, selector: str, text: str):
        """Click a field and type text character by character with random delays."""
        await page.click(selector)
        await self._human_delay(200, 500)
        for char in text:
            await page.keyboard.type(char)
            await asyncio.sleep(random.randint(50, 150) / 1000.0)

    async def _human_click(self, page: Page, selector: str):
        """Move mouse to a random point within an element's bounding box, then click."""
        element = page.locator(selector)
        box = await element.bounding_box()
        if box:
            # Pick a random point inside the element
            x = box["x"] + random.uniform(box["width"] * 0.2, box["width"] * 0.8)
            y = box["y"] + random.uniform(box["height"] * 0.2, box["height"] * 0.8)
            await page.mouse.move(x, y, steps=random.randint(5, 15))
            await self._human_delay(100, 300)
            await page.mouse.click(x, y)
        else:
            # Fallback to regular click
            await element.click()

    async def _random_mouse_movement(self, page: Page):
        """Perform 1-3 random mouse movements across the viewport."""
        for _ in range(random.randint(1, 3)):
            x = random.randint(100, 1200)
            y = random.randint(100, 600)
            await page.mouse.move(x, y, steps=random.randint(5, 15))
            await self._human_delay(200, 800)

    # --- Stealth re-authentication ---

    async def perform_stealth_reauth(self, email: str, password: str) -> bool:
        """Perform a full stealth browser re-authentication.

        Uses non-headless Chromium via Xvfb with anti-detection measures.
        Returns True if login succeeded and cookies were saved.
        """
        if not email or not password:
            _LOGGER.warning("Stealth reauth called without credentials")
            return False

        _LOGGER.info("Starting stealth re-authentication...")
        browser = None

        try:
            # Use Xvfb display
            display = os.environ.get("DISPLAY", ":100")

            browser = await self._playwright.chromium.launch(
                headless=False,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--window-size=1366,768",
                    "--disable-features=IsolateOrigins,site-per-process",
                ],
            )

            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                viewport={"width": 1366, "height": 768},
                locale="en-US",
                timezone_id="America/New_York",
                color_scheme="light",
            )

            # Inject stealth JS into every frame
            await context.add_init_script(_STEALTH_JS)

            page = await context.new_page()

            # Overall timeout guard
            async def _do_reauth():
                # Step 1: Navigate to parentdashboard — check if we need to sign in
                _LOGGER.info("Stealth reauth: navigating to parentdashboard...")
                try:
                    resp = await page.goto("https://www.amazon.com/parentdashboard", wait_until="domcontentloaded", timeout=45000)
                    _LOGGER.info(f"Stealth reauth: page loaded (status={resp.status if resp else 'none'}, url={page.url})")
                except Exception as nav_err:
                    _LOGGER.error(f"Stealth reauth: navigation failed: {nav_err}")
                    return False
                await self._human_delay(1000, 3000)

                # If we landed on /intro or aren't on the sign-in page, navigate to sign-in explicitly
                current_url = page.url
                if "ap/signin" not in current_url:
                    _LOGGER.info("Stealth reauth: not on sign-in page, navigating to sign-in explicitly...")
                    sign_in_url = (
                        "https://www.amazon.com/ap/signin?"
                        "openid.pape.max_auth_age=0"
                        "&openid.return_to=https%3A%2F%2Fwww.amazon.com%2Fparentdashboard"
                        "&openid.identity=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select"
                        "&openid.assoc_handle=usflex"
                        "&openid.mode=checkid_setup"
                        "&openid.claimed_id=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select"
                        "&openid.ns=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0"
                    )
                    try:
                        resp = await page.goto(sign_in_url, wait_until="domcontentloaded", timeout=30000)
                        _LOGGER.info(f"Stealth reauth: sign-in page loaded (status={resp.status if resp else 'none'}, url={page.url})")
                    except Exception as nav_err:
                        _LOGGER.error(f"Stealth reauth: sign-in navigation failed: {nav_err}")
                        return False
                    await self._human_delay(1000, 3000)

                await self._random_mouse_movement(page)

                # Step 2b: Wait for sign-in form to render (JS may load it async)
                # Amazon uses multiple sign-in page variants:
                #   Classic: #ap_email + #ap_password + #signInSubmit
                #   New unified: input[name="email"] or input[type="email"] + "Continue" button
                _LOGGER.info("Stealth reauth: waiting for sign-in form to render...")

                # Try multiple known selectors for the email field
                email_selectors = ["#ap_email", "input[name='email']", "input[type='email']", "input[name='loginID']"]
                email_selector = None
                for sel in email_selectors:
                    try:
                        await page.wait_for_selector(sel, timeout=3000)
                        email_selector = sel
                        _LOGGER.info(f"Stealth reauth: found email field with selector '{sel}'")
                        break
                    except Exception:
                        continue

                if not email_selector:
                    _LOGGER.warning("Stealth reauth: no known email field found, dumping page state...")
                    try:
                        title = await page.title()
                        _LOGGER.warning(f"Stealth reauth: page title='{title}', url={page.url}")
                        # Dump all input elements for debugging
                        inputs = await page.eval_on_selector_all(
                            "input",
                            "els => els.map(e => ({tag: e.tagName, id: e.id, name: e.name, type: e.type, placeholder: e.placeholder}))"
                        )
                        _LOGGER.warning(f"Stealth reauth: input elements on page: {inputs}")
                    except Exception as debug_err:
                        _LOGGER.warning(f"Stealth reauth: debug info failed: {debug_err}")
                    _LOGGER.error("Stealth reauth: cannot find email input, aborting")
                    return False

                # Step 3: Fill email
                _LOGGER.info("Stealth reauth: typing email...")
                await self._human_type(page, email_selector, email)
                await self._human_delay(500, 1500)

                # Click continue/submit button
                continue_selectors = ["#continue", "input[id='continue']", "span#continue", "#auth-signin-button", "#signInSubmit"]
                for cont_sel in continue_selectors:
                    cont_btn = page.locator(cont_sel)
                    if await cont_btn.count() > 0:
                        _LOGGER.info(f"Stealth reauth: clicking continue with selector '{cont_sel}'...")
                        await self._human_click(page, cont_sel)
                        try:
                            await page.wait_for_load_state("domcontentloaded", timeout=10000)
                        except Exception as e:
                            _LOGGER.warning(f"Stealth reauth: wait after continue: {e}")
                        _LOGGER.info(f"Stealth reauth: after continue, url={page.url}")
                        await self._human_delay(1000, 2000)
                        break

                # Step 4: Fill password
                _LOGGER.info("Stealth reauth: waiting for password field...")
                password_selectors = ["#ap_password", "input[name='password']", "input[type='password']"]
                password_selector = None
                for sel in password_selectors:
                    try:
                        await page.wait_for_selector(sel, timeout=10000)
                        password_selector = sel
                        _LOGGER.info(f"Stealth reauth: found password field with selector '{sel}'")
                        break
                    except Exception:
                        continue

                if not password_selector:
                    _LOGGER.warning("Stealth reauth: no password field found, dumping page state...")
                    try:
                        inputs = await page.eval_on_selector_all(
                            "input",
                            "els => els.map(e => ({tag: e.tagName, id: e.id, name: e.name, type: e.type}))"
                        )
                        _LOGGER.warning(f"Stealth reauth: input elements: {inputs}, url={page.url}")
                    except Exception:
                        pass
                    _LOGGER.error("Stealth reauth: cannot find password input, aborting")
                    return False

                _LOGGER.info("Stealth reauth: typing password...")
                await self._human_type(page, password_selector, password)
                await self._human_delay(500, 1500)
                await self._random_mouse_movement(page)

                # Click sign-in button
                signin_selectors = ["#signInSubmit", "input[id='signInSubmit']", "#auth-signin-button"]
                for sign_sel in signin_selectors:
                    sign_btn = page.locator(sign_sel)
                    if await sign_btn.count() > 0:
                        _LOGGER.info(f"Stealth reauth: clicking sign-in with selector '{sign_sel}'...")
                        await self._human_click(page, sign_sel)
                        try:
                            await page.wait_for_load_state("domcontentloaded", timeout=15000)
                        except Exception as e:
                            _LOGGER.warning(f"Stealth reauth: wait after sign-in: {e}")
                        break

                # Step 5: Wait and check result
                await self._human_delay(2000, 5000)
                current_url = page.url
                _LOGGER.info(f"Stealth reauth: post-login url={current_url}")

                # Check for 2FA/CAPTCHA
                if "ap/mfa" in current_url or "ap/challenge" in current_url:
                    _LOGGER.warning("Stealth reauth: 2FA/challenge detected - cannot proceed automatically")
                    return False

                captcha = page.locator("#auth-captcha-image")
                if await captcha.count() > 0:
                    _LOGGER.warning("Stealth reauth: CAPTCHA detected - cannot proceed automatically")
                    return False

                # Check if we reached the dashboard (use URL path, not query string)
                url_path = current_url.split("?")[0]
                if "/parentdashboard" not in url_path:
                    _LOGGER.warning(f"Stealth reauth: unexpected URL after login: {current_url}")
                    try:
                        title = await page.title()
                        _LOGGER.warning(f"Stealth reauth: page title='{title}'")
                    except Exception:
                        pass
                    return False

                _LOGGER.info("Stealth reauth: reached Parent Dashboard")

                # Step 6: Navigate to dashboard to get CSRF token
                try:
                    await page.goto(
                        "https://www.amazon.com/parentdashboard",
                        wait_until="domcontentloaded",
                        timeout=15000,
                    )
                except Exception as e:
                    _LOGGER.warning(f"Stealth reauth: dashboard navigation: {e}")

                # Wait for CSRF token cookie (up to 15s)
                _LOGGER.info("Stealth reauth: waiting for CSRF token cookie...")
                csrf_found = False
                for _ in range(15):
                    cookies_check = await context.cookies()
                    if any(c.get("name") == "ft-panda-csrf-token" for c in cookies_check):
                        csrf_found = True
                        break
                    await asyncio.sleep(1)

                if not csrf_found:
                    _LOGGER.warning("Stealth reauth: CSRF token not found after 15s, proceeding anyway")

                # Step 7: Extract and save cookies
                cookies = await context.cookies()
                amazon_cookies = [
                    c for c in cookies
                    if any(domain in c.get("domain", "") for domain in ["amazon.com", ".amazon.com"])
                ]

                if not amazon_cookies:
                    _LOGGER.error("Stealth reauth: no Amazon cookies found")
                    return False

                from storage.file_storage import SharedStorage
                storage = SharedStorage()
                await storage.save_cookies(amazon_cookies)

                csrf_token = None
                for c in amazon_cookies:
                    if c.get("name") == "ft-panda-csrf-token":
                        csrf_token = c.get("value")
                        break

                _LOGGER.info(
                    f"Stealth reauth: saved {len(amazon_cookies)} cookies "
                    f"(CSRF: {'found' if csrf_token else 'missing'})"
                )
                return True

            # Run with overall timeout
            result = await asyncio.wait_for(_do_reauth(), timeout=120)
            return result

        except asyncio.TimeoutError:
            _LOGGER.error("Stealth reauth: timed out after 120s")
            return False
        except Exception as e:
            _LOGGER.error(f"Stealth reauth failed: {e}")
            return False
        finally:
            if browser:
                try:
                    await browser.close()
                except Exception:
                    pass

    # --- Manual VNC auth session (unchanged) ---

    async def start_auth_session(self) -> str:
        """Start a new authentication session."""
        session_id = str(uuid.uuid4())
        _LOGGER.info(f"Starting authentication session: {session_id}")

        try:
            # Launch browser (non-headless so user can interact)
            browser = await self._playwright.chromium.launch(
                headless=False,
                args=[
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-features=IsolateOrigins,site-per-process',
                ]
            )

            # Create context with realistic user agent
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                viewport={'width': 1280, 'height': 800},
                locale='en-US',
                timezone_id='America/New_York'
            )

            # Create page
            page = await context.new_page()

            # Store session
            self._sessions[session_id] = {
                'browser': browser,
                'context': context,
                'page': page,
                'status': 'authenticating',
                'cookies': None,
                'csrf_token': None,
                'error': None
            }

            # Listen for new tabs/popups
            def on_page(new_page):
                _LOGGER.info("New tab detected, switching monitoring to new page")
                self._sessions[session_id]['page'] = new_page

            context.on("page", on_page)

            # Navigate to Amazon Parent Dashboard
            _LOGGER.info("Navigating to Amazon Parent Dashboard...")
            await page.goto('https://www.amazon.com/parentdashboard', wait_until='networkidle', timeout=30000)

            # Start monitoring in background
            asyncio.create_task(self._monitor_authentication(session_id))

            return session_id

        except Exception as e:
            _LOGGER.error(f"Failed to start auth session: {e}")
            raise

    async def _monitor_authentication(self, session_id: str):
        """Monitor authentication progress."""
        session = self._sessions.get(session_id)
        if not session:
            return

        context: BrowserContext = session['context']

        try:
            _LOGGER.info(f"Monitoring authentication for session {session_id}")

            # Wait for URL to contain "parentdashboard" and not be on login page
            await asyncio.sleep(5)  # Give initial page time to load

            # Poll for authentication completion
            start_time = asyncio.get_event_loop().time()
            authenticated = False

            while (asyncio.get_event_loop().time() - start_time) < self._auth_timeout:
                # Get the current page (might have changed if new tab opened)
                page: Page = session['page']
                current_url = page.url
                _LOGGER.info(f"Checking authentication - Current URL: {current_url}")

                # Check if we're past the login page and on the real dashboard
                # (exclude /intro which is the pre-login splash page)
                if 'ap/signin' not in current_url and 'ap/mfa' not in current_url and 'parentdashboard/intro' not in current_url:
                    if 'parentdashboard' in current_url:
                        _LOGGER.info(f"Authentication detected at: {current_url}")

                        # Navigate to the main dashboard to ensure CSRF token is set
                        _LOGGER.info("Navigating to main dashboard to obtain CSRF token...")
                        try:
                            await page.goto('https://www.amazon.com/parentdashboard', wait_until='networkidle', timeout=15000)
                            _LOGGER.info("Successfully navigated to main dashboard")
                        except Exception as e:
                            _LOGGER.warning(f"Failed to navigate to main dashboard: {e}")

                        # Wait for the CSRF token cookie to appear (up to 15s)
                        _LOGGER.info("Waiting for CSRF token cookie...")
                        csrf_wait_start = asyncio.get_event_loop().time()
                        csrf_found = False
                        while (asyncio.get_event_loop().time() - csrf_wait_start) < 15:
                            cookies_check = await context.cookies()
                            if any(c.get('name') == 'ft-panda-csrf-token' for c in cookies_check):
                                _LOGGER.info("CSRF token cookie found")
                                csrf_found = True
                                break
                            await asyncio.sleep(1)

                        if not csrf_found:
                            _LOGGER.warning("CSRF token not found after 15s, proceeding anyway")

                        authenticated = True
                        break

                await asyncio.sleep(2)

            if not authenticated:
                raise asyncio.TimeoutError("Authentication timeout")

            # Extract cookies
            _LOGGER.info("Authentication detected, extracting cookies...")
            cookies = await context.cookies()

            # Filter relevant Amazon cookies
            amazon_cookies = [
                c for c in cookies
                if any(domain in c.get('domain', '') for domain in [
                    'amazon.com', '.amazon.com'
                ])
            ]

            if not amazon_cookies:
                raise Exception("No valid Amazon cookies found")

            # Extract CSRF token from cookies
            csrf_token = None
            for cookie in amazon_cookies:
                if cookie.get('name') == 'ft-panda-csrf-token':
                    csrf_token = cookie.get('value')
                    _LOGGER.info("Extracted CSRF token")
                    break

            if not csrf_token:
                _LOGGER.warning("CSRF token not found in cookies - API calls may fail")

            _LOGGER.info(f"Extracted {len(amazon_cookies)} Amazon cookies")

            # Save to shared storage
            from storage.file_storage import SharedStorage
            storage = SharedStorage()
            await storage.save_cookies(amazon_cookies)

            # Update session
            session['status'] = 'completed'
            session['cookies'] = amazon_cookies
            session['csrf_token'] = csrf_token

            _LOGGER.info(f"Authentication completed successfully for session {session_id}")

            # Close browser after a short delay
            await asyncio.sleep(2)
            await self._cleanup_session(session_id)

        except asyncio.TimeoutError:
            session['status'] = 'timeout'
            session['error'] = 'Authentication timeout - user did not complete login in time'
            _LOGGER.error(f"Authentication timeout for session {session_id}")
            await self._cleanup_session(session_id)

        except Exception as e:
            session['status'] = 'error'
            session['error'] = str(e)
            _LOGGER.error(f"Authentication error for session {session_id}: {e}")
            await self._cleanup_session(session_id)

    async def get_session_status(self, session_id: str) -> Dict:
        """Get status of authentication session."""
        session = self._sessions.get(session_id)
        if not session:
            return {'status': 'not_found'}

        return {
            'status': session['status'],
            'has_cookies': session['cookies'] is not None,
            'has_csrf_token': session['csrf_token'] is not None,
            'error': session.get('error'),
            'cookie_count': len(session['cookies']) if session['cookies'] else 0
        }

    async def _cleanup_session(self, session_id: str):
        """Clean up session resources."""
        session = self._sessions.get(session_id)
        if session:
            try:
                if session.get('page'):
                    await session['page'].close()
                if session.get('context'):
                    await session['context'].close()
                if session.get('browser'):
                    await session['browser'].close()
                _LOGGER.info(f"Cleaned up session {session_id}")
            except Exception as e:
                _LOGGER.warning(f"Cleanup error for session {session_id}: {e}")
            finally:
                # Keep session info for status checks
                session['browser'] = None
                session['context'] = None
                session['page'] = None

    async def cleanup(self):
        """Cleanup all resources."""
        _LOGGER.info("Cleaning up all sessions...")
        for session_id in list(self._sessions.keys()):
            await self._cleanup_session(session_id)

        if self._playwright:
            await self._playwright.stop()
            _LOGGER.info("Playwright stopped")

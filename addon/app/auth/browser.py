"""Browser-based authentication manager using Playwright."""
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Optional

import aiohttp
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

_LOGGER = logging.getLogger(__name__)


class KeepAliveManager:
    """Manages periodic heartbeats to keep the Amazon session alive."""

    def __init__(
        self,
        storage,
        interval: int = 2700,
        amazon_email: str = "",
        amazon_password: str = "",
        browser_auth_manager: Optional["BrowserAuthManager"] = None,
    ):
        self._storage = storage
        self._interval = interval
        self._amazon_email = amazon_email
        self._amazon_password = amazon_password
        self._browser_auth_manager = browser_auth_manager
        self._task: Optional[asyncio.Task] = None
        self._last_heartbeat: Optional[datetime] = None
        self._next_heartbeat: Optional[datetime] = None
        self._session_healthy: bool = False
        self._running: bool = False
        self._consecutive_failures: int = 0

    @property
    def last_heartbeat(self) -> Optional[datetime]:
        return self._last_heartbeat

    @property
    def next_heartbeat(self) -> Optional[datetime]:
        return self._next_heartbeat

    @property
    def session_healthy(self) -> bool:
        return self._session_healthy

    @property
    def credentials_configured(self) -> bool:
        return bool(self._amazon_email and self._amazon_password)

    def start(self):
        """Start the keep-alive background loop."""
        if self._task is not None:
            return
        self._running = True
        self._task = asyncio.create_task(self._heartbeat_loop())
        _LOGGER.info(
            f"Keep-alive started (interval={self._interval}s, "
            f"credentials={'configured' if self.credentials_configured else 'not configured'})"
        )

    async def stop(self):
        """Stop the keep-alive background loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        _LOGGER.info("Keep-alive stopped")

    async def trigger(self) -> dict:
        """Manually trigger a heartbeat and return the result."""
        return await self._do_heartbeat()

    async def _heartbeat_loop(self):
        """Background loop that sends heartbeats at the configured interval."""
        # Wait a bit on startup before the first heartbeat
        await asyncio.sleep(30)

        while self._running:
            try:
                self._next_heartbeat = datetime.now(timezone.utc)
                await self._do_heartbeat()
            except Exception as e:
                _LOGGER.error(f"Heartbeat loop error: {e}")

            self._next_heartbeat = datetime.fromtimestamp(
                datetime.now(timezone.utc).timestamp() + self._interval,
                tz=timezone.utc,
            )
            await asyncio.sleep(self._interval)

    async def _do_heartbeat(self) -> dict:
        """Perform a single heartbeat: load cookies and hit Amazon API."""
        try:
            cookies_exist = await self._storage.check_exists()
            if not cookies_exist:
                _LOGGER.warning("Heartbeat: no cookies stored, skipping")
                self._session_healthy = False
                return {"status": "no_cookies"}

            cookies = await self._storage.load_cookies()

            # Build a cookie header string
            cookie_header = "; ".join(
                f"{c['name']}={c.get('value', '')}" for c in cookies
            )

            # Extract CSRF token
            csrf_token = ""
            for c in cookies:
                if c.get("name") == "ft-panda-csrf-token":
                    csrf_token = c.get("value", "")
                    break

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
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
                    self._last_heartbeat = datetime.now(timezone.utc)

                    if resp.status == 200:
                        self._session_healthy = True
                        self._consecutive_failures = 0

                        # Check for updated cookies in response headers
                        await self._update_cookies_from_response(resp, cookies)

                        _LOGGER.info("Heartbeat: session alive (HTTP 200)")
                        return {"status": "healthy", "http_status": 200}

                    elif resp.status in (401, 403):
                        self._session_healthy = False
                        self._consecutive_failures += 1
                        _LOGGER.warning(
                            f"Heartbeat: session expired (HTTP {resp.status})"
                        )

                        # Attempt auto re-login if credentials are available
                        if self.credentials_configured and self._browser_auth_manager:
                            _LOGGER.info("Attempting auto re-login...")
                            success = await self._browser_auth_manager.auto_login(
                                self._amazon_email, self._amazon_password
                            )
                            if success:
                                self._session_healthy = True
                                self._consecutive_failures = 0
                                return {"status": "re_authenticated"}
                            else:
                                return {"status": "re_login_failed"}
                        return {"status": "expired", "http_status": resp.status}

                    else:
                        self._consecutive_failures += 1
                        _LOGGER.warning(
                            f"Heartbeat: unexpected status {resp.status}"
                        )
                        return {"status": "error", "http_status": resp.status}

        except Exception as e:
            self._session_healthy = False
            self._consecutive_failures += 1
            _LOGGER.error(f"Heartbeat failed: {e}")
            return {"status": "error", "error": str(e)}

    async def _update_cookies_from_response(
        self, resp: aiohttp.ClientResponse, original_cookies: list
    ):
        """Check response for updated Set-Cookie headers and save if changed."""
        set_cookies = resp.headers.getall("Set-Cookie", [])
        if not set_cookies:
            return

        updated = False
        for set_cookie_header in set_cookies:
            # Parse the Set-Cookie header to get name=value
            parts = set_cookie_header.split(";")[0].strip()
            if "=" not in parts:
                continue
            name, value = parts.split("=", 1)
            name = name.strip()
            value = value.strip()

            # Update the matching cookie in our list
            for c in original_cookies:
                if c.get("name") == name:
                    if c.get("value") != value:
                        c["value"] = value
                        updated = True
                        _LOGGER.debug(f"Updated rotated cookie: {name}")
                    break

        if updated:
            await self._storage.save_cookies(original_cookies)
            _LOGGER.info("Saved updated cookies after rotation")

    def get_status(self) -> dict:
        """Return current keep-alive status."""
        return {
            "session_healthy": self._session_healthy,
            "last_heartbeat": (
                self._last_heartbeat.isoformat() if self._last_heartbeat else None
            ),
            "next_heartbeat": (
                self._next_heartbeat.isoformat() if self._next_heartbeat else None
            ),
            "interval_seconds": self._interval,
            "credentials_configured": self.credentials_configured,
            "consecutive_failures": self._consecutive_failures,
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
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
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

    async def auto_login(self, email: str, password: str) -> bool:
        """Attempt automated login with stored credentials.

        Returns True if login succeeded and cookies were saved.
        Falls back to manual VNC auth on 2FA/CAPTCHA.
        """
        if not email or not password:
            _LOGGER.warning("Auto-login called without credentials")
            return False

        _LOGGER.info("Starting auto re-login...")
        browser = None

        try:
            # Launch headless browser (no VNC needed)
            browser = await self._playwright.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-blink-features=AutomationControlled',
                ]
            )

            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1280, 'height': 800},
                locale='en-US',
                timezone_id='America/New_York'
            )

            page = await context.new_page()

            # Navigate to Amazon sign-in
            _LOGGER.info("Auto-login: navigating to Amazon sign-in...")
            await page.goto(
                'https://www.amazon.com/ap/signin?openid.pape.max_auth_age=0&openid.return_to=https%3A%2F%2Fwww.amazon.com%2Fparentdashboard&openid.identity=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&openid.assoc_handle=usflex&openid.mode=checkid_setup&openid.claimed_id=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&openid.ns=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0',
                wait_until='networkidle',
                timeout=30000,
            )

            # Fill email
            email_field = page.locator('#ap_email')
            if await email_field.count() > 0:
                await email_field.fill(email)
                _LOGGER.info("Auto-login: filled email")

                # Click continue if there's a separate continue button
                continue_btn = page.locator('#continue')
                if await continue_btn.count() > 0:
                    await continue_btn.click()
                    await page.wait_for_load_state('networkidle', timeout=10000)

            # Fill password
            password_field = page.locator('#ap_password')
            if await password_field.count() > 0:
                await password_field.fill(password)
                _LOGGER.info("Auto-login: filled password")

                # Click sign-in
                signin_btn = page.locator('#signInSubmit')
                if await signin_btn.count() > 0:
                    await signin_btn.click()
                    await page.wait_for_load_state('networkidle', timeout=15000)

            # Check where we landed
            await asyncio.sleep(3)
            current_url = page.url

            # Check for 2FA/MFA page
            if 'ap/mfa' in current_url or 'ap/challenge' in current_url:
                _LOGGER.warning(
                    "Auto-login: 2FA/CAPTCHA detected - manual VNC auth required"
                )
                await browser.close()
                return False

            # Check for CAPTCHA
            captcha = page.locator('#auth-captcha-image')
            if await captcha.count() > 0:
                _LOGGER.warning(
                    "Auto-login: CAPTCHA detected - manual VNC auth required"
                )
                await browser.close()
                return False

            # Check if we reached the dashboard
            if 'parentdashboard' in current_url:
                _LOGGER.info("Auto-login: successfully reached Parent Dashboard")

                # Navigate to dashboard to get CSRF token
                await page.goto(
                    'https://www.amazon.com/parentdashboard',
                    wait_until='networkidle',
                    timeout=15000,
                )
                await asyncio.sleep(3)

                # Extract cookies
                cookies = await context.cookies()
                amazon_cookies = [
                    c for c in cookies
                    if any(
                        domain in c.get('domain', '')
                        for domain in ['amazon.com', '.amazon.com']
                    )
                ]

                if not amazon_cookies:
                    _LOGGER.error("Auto-login: no Amazon cookies found after login")
                    await browser.close()
                    return False

                # Save cookies
                from storage.file_storage import SharedStorage
                storage = SharedStorage()
                await storage.save_cookies(amazon_cookies)

                csrf_token = None
                for c in amazon_cookies:
                    if c.get('name') == 'ft-panda-csrf-token':
                        csrf_token = c.get('value')
                        break

                _LOGGER.info(
                    f"Auto-login: saved {len(amazon_cookies)} cookies "
                    f"(CSRF: {'found' if csrf_token else 'missing'})"
                )

                await browser.close()
                return True

            else:
                _LOGGER.warning(
                    f"Auto-login: unexpected URL after login: {current_url}"
                )
                await browser.close()
                return False

        except Exception as e:
            _LOGGER.error(f"Auto-login failed: {e}")
            if browser:
                try:
                    await browser.close()
                except Exception:
                    pass
            return False

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

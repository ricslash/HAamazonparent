"""Client to read cookies from Amazon Parent Auth add-on via HTTP API."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant

from ..const import DEFAULT_ADDON_URL, LOGGER_NAME

_LOGGER = logging.getLogger(LOGGER_NAME)


class AddonCookieClient:
    """Client to read cookies from add-on via HTTP API."""

    def __init__(self, hass: HomeAssistant, auth_url: str | None = None):
        """Initialize addon cookie client.

        Args:
            hass: Home Assistant instance
            auth_url: URL for the auth server (e.g., http://localhost:8100)
        """
        self.hass = hass
        self.auth_url = auth_url or DEFAULT_ADDON_URL

    async def _fetch_cookies_from_url(self, url: str) -> list[dict[str, Any]] | None:
        """Fetch cookies from auth server API.

        Args:
            url: Base URL of the auth server (e.g., http://localhost:8100)

        Returns:
            List of cookies or None if failed
        """
        api_url = f"{url.rstrip('/')}/api/cookies"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        cookies = data.get("cookies", [])
                        _LOGGER.info(f"Loaded {len(cookies)} cookies from API ({url})")
                        return cookies
                    elif response.status == 404:
                        _LOGGER.debug(f"No cookies found at {api_url}")
                        return None
                    else:
                        _LOGGER.debug(f"API returned status {response.status} from {api_url}")
                        return None
        except aiohttp.ClientError as err:
            _LOGGER.debug(f"Failed to connect to {api_url}: {err}")
            return None
        except Exception as err:
            _LOGGER.debug(f"Error fetching cookies from {api_url}: {err}")
            return None

    async def _check_url_available(self, url: str) -> bool:
        """Check if auth server API is available at URL."""
        health_url = f"{url.rstrip('/')}/api/health"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(health_url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    return response.status == 200
        except Exception:
            return False

    async def detect_auth_source(self) -> tuple[str, str | None]:
        """Detect available authentication source.

        Returns:
            Tuple of (source_type, url_or_none):
            - ("api", "http://...") if API is available
            - ("none", None) if nothing is available
        """
        if self.auth_url:
            if await self._check_url_available(self.auth_url):
                return ("api", self.auth_url)

        if await self._check_url_available(DEFAULT_ADDON_URL):
            return ("api", DEFAULT_ADDON_URL)

        return ("none", None)

    async def load_cookies(self) -> list[dict[str, Any]] | None:
        """Load cookies from the auth server API.

        Priority:
        1. Custom URL (if configured)
        2. Default local API (localhost:8100)
        """
        if self.auth_url:
            cookies = await self._fetch_cookies_from_url(self.auth_url)
            if cookies is not None:
                return cookies
            _LOGGER.warning(f"Failed to load cookies from configured URL: {self.auth_url}")

        cookies = await self._fetch_cookies_from_url(DEFAULT_ADDON_URL)
        if cookies is not None:
            return cookies

        _LOGGER.error("Failed to load cookies from any source")
        return None

    async def cookies_available(self) -> bool:
        """Check if cookies are available from any source."""
        source_type, _ = await self.detect_auth_source()
        if source_type == "none":
            return False

        cookies = await self.load_cookies()
        return cookies is not None and len(cookies) > 0

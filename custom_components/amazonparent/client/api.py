"""Amazon Parent Dashboard API client."""
import logging
from typing import Any
from http.cookies import SimpleCookie
from datetime import datetime, timezone

import aiohttp

from ..const import (
    API_BASE_URL,
    API_GET_HOUSEHOLD,
    API_GET_CHILD_DEVICES,
    API_GET_TIME_LIMITS,
    API_SET_OFFSCREEN_TIME,
    API_SET_TIME_LIMIT,
)
from ..models import (
    HouseholdMember,
    Device,
    ChildSchedule,
    DaySchedule,
    CurfewConfig,
    TimeLimits,
    GoalsConfig,
)

_LOGGER = logging.getLogger(__name__)


class AmazonParentAPIClient:
    """Client for Amazon Parent Dashboard API."""

    def __init__(self, cookies: list[dict[str, Any]]) -> None:
        """Initialize the API client."""
        self._cookies = cookies
        self._csrf_token = self._extract_csrf_token()
        self._session: aiohttp.ClientSession | None = None

    def _extract_csrf_token(self) -> str:
        """Extract CSRF token from cookies."""
        for cookie in self._cookies:
            if cookie.get("name") == "ft-panda-csrf-token":
                return cookie.get("value", "")
        _LOGGER.warning("CSRF token not found in cookies")
        return ""

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session with cookies."""
        if self._session is None or self._session.closed:
            jar = aiohttp.CookieJar()
            simple_cookies = SimpleCookie()
            for c in self._cookies:
                simple_cookies[c["name"]] = str(c.get("value", ""))
                morsel = simple_cookies[c["name"]]
                morsel["domain"] = c["domain"]
                morsel["path"] = c.get("path", "/")
                expires = c.get("expires")
                if expires and expires != -1:
                    try:
                        morsel["expires"] = datetime.fromtimestamp(
                            expires, tz=timezone.utc
                        ).strftime("%a, %d-%b-%Y %H:%M:%S GMT")
                    except (ValueError, TypeError):
                        _LOGGER.warning("Could not process cookie expiration: %s", expires)
                if c.get("secure"):
                    morsel["secure"] = True
            jar.update_cookies(simple_cookies)
            self._session = aiohttp.ClientSession(cookie_jar=jar)
        return self._session

    def _get_headers(self, for_post: bool = False) -> dict[str, str]:
        """Get request headers."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.amazon.com/parentdashboard/",
            "x-amzn-csrf": self._csrf_token,
        }

        if for_post:
            headers.update({
                "Content-Type": "application/json;charset=UTF-8",
                "Origin": "https://www.amazon.com",
            })

        return headers

    async def async_get_household(self) -> list[HouseholdMember]:
        """Get household members."""
        session = await self._get_session()
        url = f"{API_BASE_URL}{API_GET_HOUSEHOLD}"

        async with session.get(url, headers=self._get_headers()) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to get household: {resp.status}")

            data = await resp.json()
            members = []

            for member_data in data.get("members", []):
                member = HouseholdMember(
                    directed_id=member_data["directedId"],
                    role=member_data["role"],
                    first_name=member_data.get("firstName"),
                    avatar_uri=member_data.get("avatarUri"),
                )
                members.append(member)

            _LOGGER.debug(f"Retrieved {len(members)} household members")
            return members

    async def async_get_devices(self) -> list[Device]:
        """Get child devices."""
        session = await self._get_session()
        url = f"{API_BASE_URL}{API_GET_CHILD_DEVICES}"

        async with session.get(url, headers=self._get_headers()) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to get devices: {resp.status}")

            data = await resp.json()
            devices = []

            for device_data in data.get("devices", []):
                device = Device(
                    device_id=device_data["deviceId"],
                    device_type_id=device_data["deviceTypeId"],
                    device_name=device_data["deviceName"],
                    child_directed_id=device_data["deviceSettings"]["childDirectedId"],
                    multi_modal=device_data.get("multiModal", False),
                )
                devices.append(device)

            _LOGGER.debug(f"Retrieved {len(devices)} devices")
            return devices

    async def async_get_time_limits(self, child_directed_id: str) -> ChildSchedule:
        """Get time limits for a child."""
        session = await self._get_session()
        url = f"{API_BASE_URL}{API_GET_TIME_LIMITS}"
        params = {"childDirectedId": child_directed_id}

        async with session.get(url, headers=self._get_headers(), params=params) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to get time limits: {resp.status}")

            data = await resp.json()
            period_configs = []

            for period_data in data.get("periodConfigurations", []):
                # Parse curfew configs
                curfews = []
                for curfew_data in period_data.get("curfewConfigList", []):
                    curfew = CurfewConfig(
                        start=curfew_data["start"],
                        end=curfew_data["end"],
                        enabled=curfew_data.get("enabled", False),
                        type=curfew_data.get("type"),
                    )
                    curfews.append(curfew)

                # Parse time limits
                time_limits_data = period_data.get("timeLimits", {})
                time_limits = TimeLimits(
                    content_time_limits_enabled=time_limits_data.get("contentTimeLimitsEnabled", False),
                    content_time_limits=time_limits_data.get("contentTimeLimits", {}),
                )

                # Parse goals
                goals_data = period_data.get("goalsConfig", {})
                goals = GoalsConfig(
                    content_goals=goals_data.get("contentGoals", {}),
                    learn_first_enabled=goals_data.get("learnFirstEnabled", False),
                )

                # Create day schedule
                day_schedule = DaySchedule(
                    type=period_data["type"],
                    name=period_data["name"],
                    enabled=period_data.get("enabled", False),
                    curfew_config_list=curfews,
                    time_limits=time_limits,
                    goals_config=goals,
                    time=period_data.get("time", 0),
                )
                period_configs.append(day_schedule)

            schedule = ChildSchedule(
                child_directed_id=child_directed_id,
                period_configurations=period_configs,
            )

            _LOGGER.debug(f"Retrieved schedule for child {child_directed_id[:20]}")
            return schedule

    async def async_pause_limits(
        self, directed_ids: list[str], duration_seconds: int
    ) -> None:
        """Pause time limits for children."""
        session = await self._get_session()
        url = f"{API_BASE_URL}{API_SET_OFFSCREEN_TIME}"

        payload = {
            "directedIds": directed_ids,
            "expirationTimeInSeconds": duration_seconds,
        }

        async with session.post(
            url, headers=self._get_headers(for_post=True), json=payload
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise Exception(f"Failed to pause limits: {resp.status} - {text}")

            _LOGGER.debug(f"Paused limits for {len(directed_ids)} children ({duration_seconds}s)")

    async def async_resume_limits(self, directed_ids: list[str]) -> None:
        """Resume (unpause) time limits for children."""
        await self.async_pause_limits(directed_ids, 0)

    async def close(self) -> None:
        """Close the API client session."""
        if self._session and not self._session.closed:
            await self._session.close()

"""Data update coordinator for Amazon Parent Dashboard."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .client.api import AmazonParentAPIClient
from .const import DEFAULT_UPDATE_INTERVAL, DOMAIN, LOGGER_NAME
from .exceptions import AmazonParentException, SessionExpiredError
from .models import HouseholdMember, Device, ChildSchedule, ChildActivityData

_LOGGER = logging.getLogger(LOGGER_NAME)


class AmazonParentDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Amazon Parent Dashboard data."""

    def __init__(
        self,
        hass: HomeAssistant,
        api_client: AmazonParentAPIClient,
        addon_url: str,
        entry_id: str = "",
    ) -> None:
        """Initialize the coordinator.

        Args:
            hass: Home Assistant instance
            api_client: API client for Amazon Parent Dashboard
            addon_url: URL of the auth add-on for cookie refresh
            entry_id: Config entry ID for triggering reload
        """
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_UPDATE_INTERVAL,
        )
        self.api_client = api_client
        self._addon_url = addon_url
        self._entry_id = entry_id
        self._is_retrying_auth = False  # Prevent infinite retry loops
        self._auth_notification_sent = False  # Only send auth notification once
        self._last_known_cookie_update: str | None = None  # Track addon cookie freshness

        # Data storage
        self.household_members: list[HouseholdMember] = []
        self.devices: list[Device] = []
        self.child_schedules: dict[str, ChildSchedule] = {}
        self.child_activities: dict[str, ChildActivityData] = {}
        self.child_bonus_allotted: dict[str, int] = {}
        self.child_bonus_given_today: dict[str, int] = {}
        self.child_bonus_expires_at: dict[str, datetime | None] = {}
        self._bonus_tracking_date: str | None = None
        self._saved_time_limits: dict[str, dict[str, dict]] = {}  # child_id -> day_name -> limits
        self._last_weekly_log_date: str | None = None

    async def _async_check_cookie_freshness(self) -> None:
        """Check if the addon has newer cookies and trigger a full reload if so."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self._addon_url}/api/cookies/info",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status != 200:
                        return
                    data = await resp.json()
                    last_updated = data.get("last_updated")
                    if not last_updated:
                        return
                    if self._last_known_cookie_update != last_updated:
                        if self._last_known_cookie_update is not None:
                            _LOGGER.info(
                                "Addon cookies updated (%s → %s), reloading integration",
                                self._last_known_cookie_update,
                                last_updated,
                            )
                            self._last_known_cookie_update = last_updated
                            # Schedule reload in background so this poll cycle exits cleanly
                            self.hass.async_create_task(
                                self.hass.config_entries.async_reload(self._entry_id)
                            )
                            return
                        self._last_known_cookie_update = last_updated
        except Exception as err:
            _LOGGER.debug("Cookie freshness check failed: %s", err)

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from API."""
        # Proactively pick up fresh cookies from addon before polling
        await self._async_check_cookie_freshness()

        try:
            result = await self._async_fetch_data()
            # Reset notification flag on successful fetch
            if self._auth_notification_sent:
                self._auth_notification_sent = False
                _LOGGER.debug("Auth notification flag reset after successful fetch")
            return result

        except SessionExpiredError as err:
            # Prevent infinite retry loops
            if self._is_retrying_auth:
                _LOGGER.error("Session still expired after refresh - cookies are invalid")
                await self._create_auth_notification()
                raise UpdateFailed(
                    "Session expired, please re-authenticate via Amazon Parent Auth add-on"
                ) from err

            _LOGGER.warning("Session expired, attempting to refresh authentication")
            self._is_retrying_auth = True

            try:
                await self._async_refresh_auth()

                # Retry ONCE after refreshing authentication
                _LOGGER.info("Retrying data fetch after authentication refresh...")
                result = await self._async_fetch_data()
                self._is_retrying_auth = False  # Reset flag on success
                return result

            except SessionExpiredError:
                # If it still fails after refresh, cookies are truly invalid
                _LOGGER.error(
                    "Session still expired after refresh - please re-authenticate via add-on"
                )
                await self._create_auth_notification()
                raise UpdateFailed(
                    "Session expired, please re-authenticate via Amazon Parent Auth add-on"
                ) from err
            except Exception as retry_err:
                _LOGGER.error(f"Retry after auth refresh failed: {retry_err}")
                raise UpdateFailed(f"Failed after auth refresh: {retry_err}") from retry_err
            finally:
                self._is_retrying_auth = False  # Always reset flag

        except AmazonParentException as err:
            _LOGGER.error("Error fetching Amazon Parent data: %s", err)
            raise UpdateFailed(f"Error communicating with Amazon: {err}") from err

        except Exception as err:
            _LOGGER.exception("Unexpected error fetching Amazon Parent data")
            raise UpdateFailed(f"Unexpected error: {err}") from err

    async def _async_fetch_data(self) -> dict[str, Any]:
        """Perform the actual data fetch from Amazon Parent API."""
        # Fetch household members
        self.household_members = await self.api_client.async_get_household()

        # Fetch devices
        self.devices = await self.api_client.async_get_devices()

        # Fetch schedules and activities for each child
        children = [m for m in self.household_members if m.is_child]
        now = dt_util.now()
        timezone_str = str(now.tzinfo) if now.tzinfo else "America/New_York"
        # Try to get the HA timezone string
        try:
            timezone_str = self.hass.config.time_zone
        except Exception:
            pass

        # Roll over daily bonus tracking counters at local midnight.
        today_str = now.strftime("%Y-%m-%d")
        if self._bonus_tracking_date is not None and self._bonus_tracking_date != today_str:
            self.child_bonus_given_today.clear()
            self.child_bonus_expires_at.clear()
            self.child_bonus_allotted.clear()
        self._bonus_tracking_date = today_str

        for child in children:
            try:
                schedule = await self.api_client.async_get_time_limits(
                    child.directed_id
                )
                self.child_schedules[child.directed_id] = schedule
            except SessionExpiredError:
                raise  # Re-raise to trigger auth refresh
            except Exception as err:
                _LOGGER.warning(
                    f"Failed to get schedule for child {child.display_name}: {err}"
                )

            # Fetch current allotted bonus minutes for today
            try:
                allotted = await self.api_client.async_get_bonus_time(child.directed_id)
                self._reconcile_bonus_state(child.directed_id, allotted, now)
            except SessionExpiredError:
                raise
            except Exception as err:
                _LOGGER.warning(
                    f"Failed to get bonus time for child {child.display_name}: {err}"
                )

            # Fetch activity data (last 7 days)
            try:
                end_time = int(now.timestamp())
                start_of_week = now.replace(
                    hour=0, minute=0, second=0, microsecond=0
                ) - timedelta(days=now.weekday())
                start_time = int(start_of_week.timestamp())

                activity = await self.api_client.async_get_weekly_activities(
                    child.directed_id, start_time, end_time, timezone_str
                )
                self.child_activities[child.directed_id] = activity
            except SessionExpiredError:
                raise
            except Exception as err:
                _LOGGER.warning(
                    f"Failed to get activities for child {child.display_name}: {err}"
                )

        # Log weekly summary on day change
        self._log_weekly_summary(children)

        _LOGGER.debug(
            f"Updated data: {len(self.household_members)} members, "
            f"{len(self.devices)} devices, {len(self.child_schedules)} schedules, "
            f"{len(self.child_activities)} activity records"
        )

        # Return summary data
        return {
            "household_members": self.household_members,
            "devices": self.devices,
            "child_schedules": self.child_schedules,
            "child_activities": self.child_activities,
            "last_update": now,
        }

    async def _async_refresh_auth(self) -> None:
        """Refresh authentication when session expires.

        Triggers a health check on the sidecar so it can detect the expired
        session and kick off a reauth before we re-fetch cookies.
        """
        try:
            # Step 1: Tell the sidecar to verify the session.  If the sidecar
            # also sees the session as expired it will trigger an automatic
            # reauth (when credentials are configured).
            await self._async_trigger_sidecar_health_check()

            # Step 2: Reload cookies (which may now be fresh after reauth)
            await self.api_client.async_refresh_session()
            _LOGGER.info("Successfully refreshed authentication")
        except Exception as err:
            _LOGGER.error("Failed to refresh authentication: %s", err)
            raise

    async def _async_trigger_sidecar_health_check(self) -> None:
        """Ask the sidecar to run a health check and wait for any reauth."""
        health_url = f"{self._addon_url}/api/reauth/health-check"
        reauth_url = f"{self._addon_url}/api/reauth/trigger"
        status_url = f"{self._addon_url}/api/reauth/status"

        try:
            async with aiohttp.ClientSession() as session:
                # Trigger health check
                async with session.post(
                    health_url, timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status != 200:
                        _LOGGER.warning(
                            "Sidecar health-check endpoint returned %s", resp.status
                        )
                        return
                    data = await resp.json()

                result = data.get("result", {})
                status = result.get("status")
                _LOGGER.info("Sidecar health check result: %s", status)

                if status == "healthy":
                    # Sidecar says healthy — cookies should be fine, just reload
                    return

                if status not in ("expired", "error"):
                    return

                # Session is expired on the sidecar side too — trigger reauth
                _LOGGER.warning(
                    "Sidecar confirmed session expired, triggering reauth"
                )
                async with session.post(
                    reauth_url, timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status != 200:
                        _LOGGER.warning(
                            "Sidecar reauth trigger returned %s", resp.status
                        )
                        return
                    trigger_data = await resp.json()

                trigger_status = trigger_data.get("status")
                if trigger_status == "error":
                    _LOGGER.warning(
                        "Sidecar cannot reauth: %s", trigger_data.get("error")
                    )
                    return

                # Snapshot the current last_reauth timestamp so we can detect
                # when a *new* reauth completes (not a stale previous one).
                async with session.get(
                    status_url, timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        pre = await resp.json()
                        prev_reauth = pre.get("last_reauth")
                    else:
                        prev_reauth = None

                # Poll for reauth completion (up to 150s)
                _LOGGER.info("Waiting for sidecar reauth to complete...")
                for _ in range(30):
                    await asyncio.sleep(5)
                    async with session.get(
                        status_url, timeout=aiohttp.ClientTimeout(total=10)
                    ) as resp:
                        if resp.status != 200:
                            continue
                        st = await resp.json()
                    cur_reauth = st.get("last_reauth")
                    if cur_reauth and cur_reauth != prev_reauth:
                        result_str = st.get("last_reauth_result", "unknown")
                        _LOGGER.info(
                            "Sidecar reauth finished: %s", result_str
                        )
                        return

                _LOGGER.warning("Timed out waiting for sidecar reauth")
        except Exception as err:
            _LOGGER.warning("Failed to communicate with sidecar: %s", err)

    async def _create_auth_notification(self) -> None:
        """Create a persistent notification when authentication fails (only once)."""
        if self._auth_notification_sent:
            _LOGGER.debug("Auth notification already sent, skipping")
            return

        await self.hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "title": "Amazon Parent Dashboard - Authentication Required",
                "message": (
                    "Your Amazon session has expired.\n\n"
                    "Please re-authenticate using the **Amazon Parent Auth** add-on:\n"
                    "1. Open the add-on in Supervisor\n"
                    "2. Click 'Open Web UI'\n"
                    "3. Log in with your Amazon account\n"
                    "4. The integration will automatically resume once authenticated."
                ),
                "notification_id": "amazonparent_auth_expired",
            },
        )
        self._auth_notification_sent = True
        _LOGGER.info("Created authentication notification for user")

    def get_child_by_id(self, child_id: str) -> HouseholdMember | None:
        """Get child by directed ID."""
        for member in self.household_members:
            if member.directed_id == child_id and member.is_child:
                return member
        return None

    def get_devices_for_child(self, child_id: str) -> list[Device]:
        """Get all devices for a specific child."""
        return [d for d in self.devices if d.child_directed_id == child_id]

    def get_schedule_for_child(self, child_id: str) -> ChildSchedule | None:
        """Get schedule for a specific child."""
        return self.child_schedules.get(child_id)

    def get_activity_for_child(self, child_id: str) -> ChildActivityData | None:
        """Get activity data for a specific child."""
        return self.child_activities.get(child_id)

    def _reconcile_bonus_state(
        self, child_id: str, allotted: int, now: datetime
    ) -> None:
        """Keep today's bonus counters and expiration synced with Amazon's value."""
        prev_allotted = self.child_bonus_allotted.get(child_id)
        self.child_bonus_allotted[child_id] = allotted
        cur_exp = self.child_bonus_expires_at.get(child_id)

        if allotted <= 0:
            if cur_exp is not None and cur_exp > now:
                unused = round((cur_exp - now).total_seconds() / 60)
                have = self.child_bonus_given_today.get(child_id, 0)
                self.child_bonus_given_today[child_id] = max(0, have - unused)
            if cur_exp is not None:
                self.child_bonus_expires_at[child_id] = None
            return

        if prev_allotted is not None and allotted > prev_allotted:
            delta = allotted - prev_allotted
            self.child_bonus_given_today[child_id] = (
                self.child_bonus_given_today.get(child_id, 0) + delta
            )
            base = cur_exp if (cur_exp is not None and cur_exp > now) else now
            self.child_bonus_expires_at[child_id] = base + timedelta(minutes=delta)
        elif self.child_bonus_given_today.get(child_id, 0) == 0:
            self.child_bonus_given_today[child_id] = allotted

    def get_bonus_remaining_minutes(self, child_id: str) -> float:
        """Return remaining minutes on the current active bonus window."""
        exp = self.child_bonus_expires_at.get(child_id)
        if exp is None:
            return 0.0
        now = dt_util.now()
        if exp <= now:
            return 0.0
        return round(max(0.0, (exp - now).total_seconds() / 60), 1)

    def resolve_child_id(self, child_id_or_name: str) -> str:
        """Resolve a child directedId or first name (case-insensitive) to directedId."""
        target = child_id_or_name.strip()
        target_lower = target.lower()
        for member in self.household_members:
            if not member.is_child:
                continue
            if member.directed_id == target:
                return member.directed_id
            if (member.first_name or "").strip().lower() == target_lower:
                return member.directed_id
        raise ValueError(f"Unknown Amazon Parent child '{child_id_or_name}'")

    def _log_weekly_summary(self, children: list[HouseholdMember]) -> None:
        """Log weekly activity summary once per day."""
        today_str = dt_util.now().strftime("%Y-%m-%d")
        if self._last_weekly_log_date == today_str:
            return
        self._last_weekly_log_date = today_str

        for child in children:
            activity = self.child_activities.get(child.directed_id)
            if not activity:
                continue

            _LOGGER.info(
                "Weekly activity for %s: %.1f min total",
                child.display_name,
                activity.weekly_total_minutes,
            )
            for day in activity.daily_activities:
                app_summary = ", ".join(
                    f"{a.title}: {a.duration_minutes}min"
                    for a in sorted(
                        day.app_activities,
                        key=lambda x: x.duration_seconds,
                        reverse=True,
                    )[:5]
                )
                _LOGGER.info(
                    "  %s: %.1f min — %s",
                    day.date,
                    day.total_minutes,
                    app_summary or "no activity",
                )

    async def async_pause_limits(
        self, child_id: str, duration_minutes: int
    ) -> None:
        """Pause limits for a child."""
        duration_seconds = duration_minutes * 60
        try:
            await self.api_client.async_pause_limits([child_id], duration_seconds)
        except SessionExpiredError:
            _LOGGER.warning("Session expired during pause, refreshing and retrying")
            await self._async_refresh_auth()
            await self.api_client.async_pause_limits([child_id], duration_seconds)
        # Refresh data after action
        await self.async_refresh()

    async def async_resume_limits(self, child_id: str) -> None:
        """Resume limits for a child."""
        try:
            await self.api_client.async_resume_limits([child_id])
        except SessionExpiredError:
            _LOGGER.warning("Session expired during resume, refreshing and retrying")
            await self._async_refresh_auth()
            await self.api_client.async_resume_limits([child_id])
        # Refresh data after action
        await self.async_refresh()

    async def async_set_time_limits_enabled(
        self, child_id: str, enabled: bool
    ) -> None:
        """Enable or disable time limits for a child (all days)."""
        schedule = self.child_schedules.get(child_id)
        if not schedule:
            raise ValueError(f"No schedule found for child {child_id}")

        now_ms = int(dt_util.now().timestamp() * 1000)
        period_configs = []
        for day in schedule.period_configurations:
            # Always preserve the existing limit values — just toggle the enabled flags.
            # If current limits are empty, restore from saved cache.
            limits = day.time_limits.content_time_limits
            if not limits:
                limits = self._saved_time_limits.get(child_id, {}).get(day.name, {})

            # Save non-empty limits so they survive disable/enable cycles
            if limits:
                if child_id not in self._saved_time_limits:
                    self._saved_time_limits[child_id] = {}
                self._saved_time_limits[child_id][day.name] = dict(limits)

            config = {
                "type": day.type,
                "name": day.name,
                "enabled": enabled,
                "curfewConfigList": [
                    {
                        "start": c.start,
                        "end": c.end,
                        "type": c.type,
                        "enabled": c.enabled,
                    }
                    for c in day.curfew_config_list
                ],
                "time": now_ms,
                "timeLimits": {
                    "contentTimeLimitsEnabled": enabled,
                    "contentTimeLimits": limits,
                },
                "goalsConfig": {
                    "contentGoals": day.goals_config.content_goals,
                    "learnFirstEnabled": day.goals_config.learn_first_enabled,
                },
                "dreamSleepEnabledDevices": None,
            }
            period_configs.append(config)

        try:
            await self.api_client.async_set_time_limits(child_id, period_configs)
        except SessionExpiredError:
            _LOGGER.warning("Session expired during set time limits, refreshing and retrying")
            await self._async_refresh_auth()
            await self.api_client.async_set_time_limits(child_id, period_configs)

        await self.async_refresh()

    async def _call_with_reauth(self, coro_factory) -> None:
        """Execute an API write call, refreshing cookies once if the session expired."""
        try:
            await coro_factory()
        except SessionExpiredError:
            _LOGGER.warning("Session expired during API call, refreshing and retrying")
            await self._async_refresh_auth()
            await coro_factory()

    async def async_add_bonus_time(self, child_id_or_name: str, minutes: int) -> None:
        """Grant additive bonus minutes (or clear if <= 0), preserving baseline schedule."""
        minutes_int = int(minutes)
        if minutes_int <= 0:
            await self.async_clear_bonus_time(child_id_or_name)
            return

        child_id = self.resolve_child_id(child_id_or_name)
        timezone_str = self.hass.config.time_zone or "America/Denver"
        await self._call_with_reauth(
            lambda: self.api_client.async_add_bonus_time(
                child_id, minutes_int, timezone_str
            )
        )

        now = dt_util.now()
        if self._bonus_tracking_date is None:
            self._bonus_tracking_date = now.strftime("%Y-%m-%d")
        cur_exp = self.child_bonus_expires_at.get(child_id)
        base = cur_exp if (cur_exp is not None and cur_exp > now) else now
        self.child_bonus_expires_at[child_id] = base + timedelta(minutes=minutes_int)
        self.child_bonus_given_today[child_id] = (
            self.child_bonus_given_today.get(child_id, 0) + minutes_int
        )
        # Update expected Amazon allotted count before refresh so poll doesn't double-count.
        self.child_bonus_allotted[child_id] = (
            self.child_bonus_allotted.get(child_id, 0) + minutes_int
        )
        await self.async_refresh()

    async def async_clear_bonus_time(self, child_id_or_name: str) -> None:
        """Clear today's allotted bonus time and remove the active bonus window."""
        child_id = self.resolve_child_id(child_id_or_name)
        await self._call_with_reauth(
            lambda: self.api_client.async_delete_bonus_time(child_id)
        )

        now = dt_util.now()
        cur_exp = self.child_bonus_expires_at.get(child_id)
        if cur_exp is not None and cur_exp > now:
            unused = round((cur_exp - now).total_seconds() / 60)
            have = self.child_bonus_given_today.get(child_id, 0)
            self.child_bonus_given_today[child_id] = max(0, have - unused)
        self.child_bonus_expires_at[child_id] = None
        self.child_bonus_allotted[child_id] = 0
        await self.async_refresh()

    async def async_cleanup(self) -> None:
        """Clean up coordinator resources."""
        if self.api_client is not None:
            await self.api_client.close()
        _LOGGER.debug("Coordinator cleanup completed")

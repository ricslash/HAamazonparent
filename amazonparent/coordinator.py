"""Data update coordinator for Amazon Parent Dashboard."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .client.api import AmazonParentAPIClient
from .const import DEFAULT_UPDATE_INTERVAL, DOMAIN, LOGGER_NAME
from .exceptions import AmazonParentException, SessionExpiredError
from .models import HouseholdMember, Device, ChildSchedule

_LOGGER = logging.getLogger(LOGGER_NAME)


class AmazonParentDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Amazon Parent Dashboard data."""

    def __init__(
        self,
        hass: HomeAssistant,
        api_client: AmazonParentAPIClient,
        addon_url: str,
    ) -> None:
        """Initialize the coordinator.

        Args:
            hass: Home Assistant instance
            api_client: API client for Amazon Parent Dashboard
            addon_url: URL of the auth add-on for cookie refresh
        """
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_UPDATE_INTERVAL,
        )
        self.api_client = api_client
        self._addon_url = addon_url
        self._is_retrying_auth = False  # Prevent infinite retry loops
        self._auth_notification_sent = False  # Only send auth notification once

        # Data storage
        self.household_members: list[HouseholdMember] = []
        self.devices: list[Device] = []
        self.child_schedules: dict[str, ChildSchedule] = {}

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from API."""
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

        # Fetch schedules for each child
        children = [m for m in self.household_members if m.is_child]
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

        _LOGGER.debug(
            f"Updated data: {len(self.household_members)} members, "
            f"{len(self.devices)} devices, {len(self.child_schedules)} schedules"
        )

        # Return summary data
        return {
            "household_members": self.household_members,
            "devices": self.devices,
            "child_schedules": self.child_schedules,
            "last_update": dt_util.now(),
        }

    async def _async_refresh_auth(self) -> None:
        """Refresh authentication when session expires."""
        try:
            await self.api_client.async_refresh_session()
            _LOGGER.info("Successfully refreshed authentication")
        except Exception as err:
            _LOGGER.error("Failed to refresh authentication: %s", err)
            raise

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

    async def async_pause_limits(
        self, child_id: str, duration_minutes: int
    ) -> None:
        """Pause limits for a child."""
        duration_seconds = duration_minutes * 60
        await self.api_client.async_pause_limits([child_id], duration_seconds)
        # Refresh data after action
        await self.async_request_refresh()

    async def async_resume_limits(self, child_id: str) -> None:
        """Resume limits for a child."""
        await self.api_client.async_resume_limits([child_id])
        # Refresh data after action
        await self.async_request_refresh()

    async def async_cleanup(self) -> None:
        """Clean up coordinator resources."""
        if self.api_client is not None:
            await self.api_client.close()
        _LOGGER.debug("Coordinator cleanup completed")

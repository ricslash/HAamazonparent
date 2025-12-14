"""Data update coordinator for Amazon Parent Dashboard."""
import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .client.api import AmazonParentAPIClient
from .const import DEFAULT_UPDATE_INTERVAL, DOMAIN
from .models import HouseholdMember, Device, ChildSchedule

_LOGGER = logging.getLogger(__name__)


class AmazonParentDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Amazon Parent Dashboard data."""

    def __init__(
        self,
        hass: HomeAssistant,
        api_client: AmazonParentAPIClient,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_UPDATE_INTERVAL,
        )
        self.api_client = api_client
        self.household_members: list[HouseholdMember] = []
        self.devices: list[Device] = []
        self.child_schedules: dict[str, ChildSchedule] = {}

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from API."""
        try:
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

        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}")

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

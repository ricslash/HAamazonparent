"""Switch platform for Amazon Parent Dashboard."""
import logging
from datetime import datetime

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, ATTR_CHILD_ID, ATTR_CHILD_NAME
from .coordinator import AmazonParentDataUpdateCoordinator
from .models import HouseholdMember

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switches from a config entry."""
    coordinator: AmazonParentDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []

    # Create switches for each child
    for member in coordinator.household_members:
        if member.is_child:
            entities.append(PauseLimitsSwitch(coordinator, member))
            entities.append(TimeLimitsEnabledSwitch(coordinator, member))

    async_add_entities(entities)


class PauseLimitsSwitch(CoordinatorEntity, SwitchEntity):
    """Switch to pause/resume time limits for a child."""

    def __init__(
        self,
        coordinator: AmazonParentDataUpdateCoordinator,
        child: HouseholdMember,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._child = child
        self._attr_unique_id = f"{child.directed_id}_pause_limits"
        self._attr_name = "Pause Limits"
        self._attr_icon = "mdi:pause-circle"
        self._attr_has_entity_name = True
        self._is_paused = False  # Track pause state locally

    @property
    def device_info(self):
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self._child.directed_id)},
            "name": f"{self._child.display_name}'s Account",
            "manufacturer": "Amazon",
            "model": "Parent Dashboard Child Account",
        }

    @property
    def is_on(self):
        """Return true if limits are paused."""
        return self._is_paused

    @property
    def extra_state_attributes(self):
        """Return extra state attributes."""
        return {
            ATTR_CHILD_ID: self._child.directed_id,
            ATTR_CHILD_NAME: self._child.display_name,
        }

    async def async_turn_on(self, **kwargs):
        """Pause limits (6 hours)."""
        try:
            await self.coordinator.async_pause_limits(self._child.directed_id, 360)
            self._is_paused = True
            self.async_write_ha_state()
            _LOGGER.info(f"Paused limits for {self._child.display_name} for 6 hours")
        except Exception as err:
            _LOGGER.error(f"Failed to pause limits: {err}")
            raise

    async def async_turn_off(self, **kwargs):
        """Resume limits."""
        try:
            await self.coordinator.async_resume_limits(self._child.directed_id)
            self._is_paused = False
            self.async_write_ha_state()
            _LOGGER.info(f"Resumed limits for {self._child.display_name}")
        except Exception as err:
            _LOGGER.error(f"Failed to resume limits: {err}")
            raise


class TimeLimitsEnabledSwitch(CoordinatorEntity, SwitchEntity):
    """Switch to enable/disable time limits for a child."""

    def __init__(
        self,
        coordinator: AmazonParentDataUpdateCoordinator,
        child: HouseholdMember,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._child = child
        self._attr_unique_id = f"{child.directed_id}_time_limits_enabled"
        self._attr_name = "Time Limits"
        self._attr_icon = "mdi:timer-lock-outline"
        self._attr_has_entity_name = True

    @property
    def device_info(self):
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self._child.directed_id)},
            "name": f"{self._child.display_name}'s Account",
            "manufacturer": "Amazon",
            "model": "Parent Dashboard Child Account",
        }

    @property
    def is_on(self):
        """Return true if time limits are enabled."""
        schedule = self.coordinator.get_schedule_for_child(self._child.directed_id)
        if not schedule:
            return None

        today = datetime.now().strftime("%A")
        day_schedule = schedule.get_day_schedule(today)
        if day_schedule:
            return day_schedule.time_limits.content_time_limits_enabled
        return None

    @property
    def extra_state_attributes(self):
        """Return extra state attributes."""
        attrs = {
            ATTR_CHILD_ID: self._child.directed_id,
            ATTR_CHILD_NAME: self._child.display_name,
        }
        schedule = self.coordinator.get_schedule_for_child(self._child.directed_id)
        if schedule:
            today = datetime.now().strftime("%A")
            day_schedule = schedule.get_day_schedule(today)
            if day_schedule:
                attrs["daily_limit_minutes"] = day_schedule.time_limits.total_minutes
                attrs["day"] = day_schedule.name
        return attrs

    async def async_turn_on(self, **kwargs):
        """Enable time limits."""
        try:
            await self.coordinator.async_set_time_limits_enabled(
                self._child.directed_id, True
            )
            self.async_write_ha_state()
            _LOGGER.info(f"Enabled time limits for {self._child.display_name}")
        except Exception as err:
            _LOGGER.error(f"Failed to enable time limits: {err}")
            raise

    async def async_turn_off(self, **kwargs):
        """Disable time limits."""
        try:
            await self.coordinator.async_set_time_limits_enabled(
                self._child.directed_id, False
            )
            self.async_write_ha_state()
            _LOGGER.info(f"Disabled time limits for {self._child.display_name}")
        except Exception as err:
            _LOGGER.error(f"Failed to disable time limits: {err}")
            raise

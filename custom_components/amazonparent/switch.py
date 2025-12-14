"""Switch platform for Amazon Parent Dashboard."""
import logging

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

    # Create pause switch for each child
    for member in coordinator.household_members:
        if member.is_child:
            entities.append(PauseLimitsSwitch(coordinator, member))

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
        """Pause limits (1 hour)."""
        try:
            await self.coordinator.async_pause_limits(self._child.directed_id, 60)
            self._is_paused = True
            self.async_write_ha_state()
            _LOGGER.info(f"Paused limits for {self._child.display_name} for 60 minutes")
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

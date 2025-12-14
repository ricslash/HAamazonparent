"""Button platform for Amazon Parent Dashboard."""
import logging

from homeassistant.components.button import ButtonEntity
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
    """Set up buttons from a config entry."""
    coordinator: AmazonParentDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []

    # Create pause buttons for each child
    for member in coordinator.household_members:
        if member.is_child:
            # 15 minute pause
            entities.append(PauseButton(coordinator, member, 15, "Pause 15min"))

            # 30 minute pause
            entities.append(PauseButton(coordinator, member, 30, "Pause 30min"))

            # 1 hour pause
            entities.append(PauseButton(coordinator, member, 60, "Pause 1 hour"))

    async_add_entities(entities)


class PauseButton(CoordinatorEntity, ButtonEntity):
    """Button to pause limits for a specific duration."""

    def __init__(
        self,
        coordinator: AmazonParentDataUpdateCoordinator,
        child: HouseholdMember,
        duration_minutes: int,
        name: str,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._child = child
        self._duration_minutes = duration_minutes
        self._attr_unique_id = f"{child.directed_id}_pause_{duration_minutes}min"
        self._attr_name = name
        self._attr_icon = "mdi:timer-pause"
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
    def extra_state_attributes(self):
        """Return extra state attributes."""
        return {
            ATTR_CHILD_ID: self._child.directed_id,
            ATTR_CHILD_NAME: self._child.display_name,
            "duration_minutes": self._duration_minutes,
        }

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            await self.coordinator.async_pause_limits(
                self._child.directed_id, self._duration_minutes
            )
            _LOGGER.info(
                f"Paused limits for {self._child.display_name} "
                f"for {self._duration_minutes} minutes"
            )
        except Exception as err:
            _LOGGER.error(f"Failed to pause limits: {err}")
            raise

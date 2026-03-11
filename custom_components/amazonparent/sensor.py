"""Sensor platform for Amazon Parent Dashboard."""
import logging
from datetime import datetime

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN, ATTR_CHILD_ID, ATTR_CHILD_NAME
from .coordinator import AmazonParentDataUpdateCoordinator
from .models import HouseholdMember

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors from a config entry."""
    coordinator: AmazonParentDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []

    # Create sensors for each child
    for member in coordinator.household_members:
        if member.is_child:
            # Daily time limit sensor
            entities.append(ChildTimeLimitSensor(coordinator, member))

            # Device count sensor
            entities.append(ChildDeviceCountSensor(coordinator, member))

            # Screen time today sensor
            entities.append(ChildScreenTimeTodaySensor(coordinator, member))

            # Weekly screen time sensor
            entities.append(ChildWeeklyScreenTimeSensor(coordinator, member))

            # Time remaining sensor
            entities.append(ChildTimeRemainingSensor(coordinator, member))

    async_add_entities(entities)


class AmazonParentSensorBase(CoordinatorEntity, SensorEntity):
    """Base class for Amazon Parent Dashboard sensors."""

    def __init__(
        self,
        coordinator: AmazonParentDataUpdateCoordinator,
        child: HouseholdMember,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._child = child
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
        }


class ChildTimeLimitSensor(AmazonParentSensorBase):
    """Sensor showing daily time limit for a child."""

    def __init__(
        self,
        coordinator: AmazonParentDataUpdateCoordinator,
        child: HouseholdMember,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, child)
        self._attr_unique_id = f"{child.directed_id}_daily_time_limit"
        self._attr_name = "Daily Time Limit"
        self._attr_icon = "mdi:clock-outline"
        self._attr_native_unit_of_measurement = "min"

    @property
    def native_value(self):
        """Return the state of the sensor."""
        schedule = self.coordinator.get_schedule_for_child(self._child.directed_id)
        if not schedule:
            return None

        # Get today's schedule
        today = datetime.now().strftime("%A")
        day_schedule = schedule.get_day_schedule(today)

        if day_schedule and day_schedule.time_limits.content_time_limits_enabled:
            return day_schedule.time_limits.total_minutes

        return None

    @property
    def extra_state_attributes(self):
        """Return extra state attributes."""
        attrs = super().extra_state_attributes

        schedule = self.coordinator.get_schedule_for_child(self._child.directed_id)
        if schedule:
            today = datetime.now().strftime("%A")
            day_schedule = schedule.get_day_schedule(today)

            if day_schedule:
                attrs["enabled"] = day_schedule.time_limits.content_time_limits_enabled
                attrs["day"] = day_schedule.name

                # Add curfew info
                if day_schedule.has_curfew:
                    curfew = day_schedule.first_curfew
                    attrs["curfew_start"] = curfew.start
                    attrs["curfew_end"] = curfew.end
                    attrs["curfew_enabled"] = curfew.enabled

                # Add reading goal
                if day_schedule.goals_config:
                    attrs["reading_goal_minutes"] = day_schedule.goals_config.reading_minutes

        return attrs


class ChildDeviceCountSensor(AmazonParentSensorBase):
    """Sensor showing number of devices for a child."""

    def __init__(
        self,
        coordinator: AmazonParentDataUpdateCoordinator,
        child: HouseholdMember,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, child)
        self._attr_unique_id = f"{child.directed_id}_device_count"
        self._attr_name = "Device Count"
        self._attr_icon = "mdi:devices"

    @property
    def native_value(self):
        """Return the state of the sensor."""
        devices = self.coordinator.get_devices_for_child(self._child.directed_id)
        return len(devices)

    @property
    def extra_state_attributes(self):
        """Return extra state attributes."""
        attrs = super().extra_state_attributes

        devices = self.coordinator.get_devices_for_child(self._child.directed_id)
        if devices:
            attrs["devices"] = [
                {
                    "name": d.device_name,
                    "id": d.device_id,
                    "type": "Fire Tablet" if d.is_fire_tablet else "Echo Device",
                }
                for d in devices
            ]

        return attrs


class ChildScreenTimeTodaySensor(AmazonParentSensorBase):
    """Sensor showing today's screen time for a child."""

    def __init__(
        self,
        coordinator: AmazonParentDataUpdateCoordinator,
        child: HouseholdMember,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, child)
        self._attr_unique_id = f"{child.directed_id}_screen_time_today"
        self._attr_name = "Screen Time Today"
        self._attr_icon = "mdi:cellphone-screen-time"
        self._attr_native_unit_of_measurement = "min"
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        """Return today's screen time in minutes."""
        activity = self.coordinator.get_activity_for_child(self._child.directed_id)
        if not activity:
            return 0

        today_str = dt_util.now().strftime("%Y-%m-%d")
        today = activity.get_today_activity(today_str)
        if not today:
            return 0

        return today.total_minutes

    @property
    def extra_state_attributes(self):
        """Return extra state attributes with per-app breakdown."""
        attrs = super().extra_state_attributes
        activity = self.coordinator.get_activity_for_child(self._child.directed_id)
        if not activity:
            return attrs

        today_str = dt_util.now().strftime("%Y-%m-%d")
        today = activity.get_today_activity(today_str)
        if not today:
            return attrs

        # Per-app breakdown sorted by duration
        app_breakdown = sorted(
            today.app_activities,
            key=lambda a: a.duration_seconds,
            reverse=True,
        )
        attrs["apps"] = [
            {
                "name": a.title,
                "minutes": a.duration_minutes,
                "category": a.category,
            }
            for a in app_breakdown
        ]
        attrs["total_seconds"] = today.total_duration_seconds

        return attrs


class ChildWeeklyScreenTimeSensor(AmazonParentSensorBase):
    """Sensor showing weekly screen time for a child."""

    def __init__(
        self,
        coordinator: AmazonParentDataUpdateCoordinator,
        child: HouseholdMember,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, child)
        self._attr_unique_id = f"{child.directed_id}_screen_time_weekly"
        self._attr_name = "Screen Time This Week"
        self._attr_icon = "mdi:calendar-week"
        self._attr_native_unit_of_measurement = "min"
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        """Return this week's total screen time in minutes."""
        activity = self.coordinator.get_activity_for_child(self._child.directed_id)
        if not activity:
            return 0

        return activity.weekly_total_minutes

    @property
    def extra_state_attributes(self):
        """Return extra state attributes with daily breakdown."""
        attrs = super().extra_state_attributes
        activity = self.coordinator.get_activity_for_child(self._child.directed_id)
        if not activity:
            return attrs

        attrs["daily_breakdown"] = [
            {
                "date": day.date,
                "minutes": day.total_minutes,
            }
            for day in activity.daily_activities
        ]

        return attrs


class ChildTimeRemainingSensor(AmazonParentSensorBase):
    """Sensor showing remaining screen time for a child (limit - used)."""

    def __init__(
        self,
        coordinator: AmazonParentDataUpdateCoordinator,
        child: HouseholdMember,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, child)
        self._attr_unique_id = f"{child.directed_id}_screen_time_remaining"
        self._attr_name = "Screen Time Remaining"
        self._attr_icon = "mdi:timer-sand"
        self._attr_native_unit_of_measurement = "min"
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        """Return remaining screen time in minutes."""
        # Get today's limit
        schedule = self.coordinator.get_schedule_for_child(self._child.directed_id)
        if not schedule:
            return None

        today = datetime.now().strftime("%A")
        day_schedule = schedule.get_day_schedule(today)
        if not day_schedule or not day_schedule.time_limits.content_time_limits_enabled:
            return None

        limit_minutes = day_schedule.time_limits.total_minutes

        # Get today's usage
        activity = self.coordinator.get_activity_for_child(self._child.directed_id)
        used_minutes = 0.0
        if activity:
            today_str = dt_util.now().strftime("%Y-%m-%d")
            today_activity = activity.get_today_activity(today_str)
            if today_activity:
                used_minutes = today_activity.total_minutes

        remaining = round(limit_minutes - used_minutes, 1)
        return max(0, remaining)

    @property
    def extra_state_attributes(self):
        """Return extra state attributes."""
        attrs = super().extra_state_attributes

        schedule = self.coordinator.get_schedule_for_child(self._child.directed_id)
        if schedule:
            today = datetime.now().strftime("%A")
            day_schedule = schedule.get_day_schedule(today)
            if day_schedule:
                attrs["daily_limit_minutes"] = day_schedule.time_limits.total_minutes
                attrs["limits_enabled"] = day_schedule.time_limits.content_time_limits_enabled

        activity = self.coordinator.get_activity_for_child(self._child.directed_id)
        if activity:
            today_str = dt_util.now().strftime("%Y-%m-%d")
            today_activity = activity.get_today_activity(today_str)
            attrs["used_minutes"] = today_activity.total_minutes if today_activity else 0

        return attrs

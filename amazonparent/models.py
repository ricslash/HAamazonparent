"""Data models for Amazon Parent Dashboard."""
from dataclasses import dataclass
from typing import Optional


@dataclass
class HouseholdMember:
    """Represents a household member."""

    directed_id: str
    role: str  # "ADULT" or "CHILD"
    first_name: Optional[str] = None
    avatar_uri: Optional[str] = None

    @property
    def is_child(self) -> bool:
        """Return True if member is a child."""
        return self.role == "CHILD"

    @property
    def display_name(self) -> str:
        """Return display name for the member."""
        return self.first_name or self.directed_id[:10]


@dataclass
class Device:
    """Represents a child's device."""

    device_id: str
    device_type_id: str
    device_name: str
    child_directed_id: str
    multi_modal: bool = False

    @property
    def is_echo(self) -> bool:
        """Return True if device is an Echo."""
        return not self.multi_modal

    @property
    def is_fire_tablet(self) -> bool:
        """Return True if device is a Fire tablet."""
        return self.multi_modal


@dataclass
class CurfewConfig:
    """Represents a curfew time window."""

    start: str  # Format: "HH:MM"
    end: str  # Format: "HH:MM"
    enabled: bool
    type: Optional[str] = None


@dataclass
class TimeLimits:
    """Represents content time limits."""

    content_time_limits_enabled: bool
    content_time_limits: dict[str, int]  # e.g., {"ALL": 90}

    @property
    def total_minutes(self) -> int:
        """Return total daily limit in minutes."""
        return self.content_time_limits.get("ALL", 0)


@dataclass
class GoalsConfig:
    """Represents learning goals."""

    content_goals: dict[str, int]  # e.g., {"category_BOOK": 15}
    learn_first_enabled: bool

    @property
    def reading_minutes(self) -> int:
        """Return reading goal in minutes."""
        return self.content_goals.get("category_BOOK", 0)


@dataclass
class DaySchedule:
    """Represents a day's schedule configuration."""

    type: str  # "DayOfWeek"
    name: str  # "Monday", "Tuesday", etc.
    enabled: bool
    curfew_config_list: list[CurfewConfig]
    time_limits: TimeLimits
    goals_config: GoalsConfig
    time: int  # Timestamp

    @property
    def has_curfew(self) -> bool:
        """Return True if any curfew is enabled."""
        return any(c.enabled for c in self.curfew_config_list)

    @property
    def first_curfew(self) -> Optional[CurfewConfig]:
        """Return the first enabled curfew."""
        for curfew in self.curfew_config_list:
            if curfew.enabled:
                return curfew
        return None


@dataclass
class ChildSchedule:
    """Represents a child's complete weekly schedule."""

    child_directed_id: str
    period_configurations: list[DaySchedule]

    def get_day_schedule(self, day_name: str) -> Optional[DaySchedule]:
        """Get schedule for a specific day."""
        for day in self.period_configurations:
            if day.name.lower() == day_name.lower():
                return day
        return None


@dataclass
class AppActivity:
    """Represents usage for a single app in a time interval."""

    key: str
    title: str
    category: str
    duration_seconds: int
    activity_count: int
    thumbnail_url: Optional[str] = None

    @property
    def duration_minutes(self) -> float:
        """Return duration in minutes."""
        return round(self.duration_seconds / 60, 1)


@dataclass
class DailyActivity:
    """Represents a single day's activity data."""

    date: str  # ISO date string (YYYY-MM-DD)
    start_time: int  # Epoch seconds
    end_time: int  # Epoch seconds
    total_duration_seconds: int
    app_activities: list[AppActivity]

    @property
    def total_minutes(self) -> float:
        """Return total duration in minutes."""
        return round(self.total_duration_seconds / 60, 1)


@dataclass
class ChildActivityData:
    """Represents a child's weekly activity data."""

    child_directed_id: str
    daily_activities: list[DailyActivity]

    def get_today_activity(self, today_str: str) -> Optional[DailyActivity]:
        """Get activity for today by ISO date string."""
        for day in self.daily_activities:
            if day.date == today_str:
                return day
        return None

    @property
    def weekly_total_seconds(self) -> int:
        """Return total seconds for the week."""
        return sum(d.total_duration_seconds for d in self.daily_activities)

    @property
    def weekly_total_minutes(self) -> float:
        """Return total minutes for the week."""
        return round(self.weekly_total_seconds / 60, 1)

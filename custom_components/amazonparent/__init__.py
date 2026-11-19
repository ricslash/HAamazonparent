"""The Amazon Parent Dashboard integration."""
from __future__ import annotations

import logging
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .auth.addon_client import AddonCookieClient
from .client.api import AmazonParentAPIClient
from .const import (
    ATTR_CHILD,
    ATTR_MINUTES,
    CONF_ADDON_URL,
    DOMAIN,
    LOGGER_NAME,
    SERVICE_ADD_BONUS_TIME,
    SERVICE_CLEAR_BONUS_TIME,
)
from .coordinator import AmazonParentDataUpdateCoordinator
from .exceptions import AmazonParentException, AuthenticationError

_LOGGER = logging.getLogger(LOGGER_NAME)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.SWITCH, Platform.BUTTON]

ADD_BONUS_TIME_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CHILD): cv.string,
        vol.Required(ATTR_MINUTES): vol.All(vol.Coerce(int), vol.Range(min=0, max=1440)),
    }
)

CLEAR_BONUS_TIME_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CHILD): cv.string,
    }
)


def _get_coordinator(hass: HomeAssistant) -> AmazonParentDataUpdateCoordinator:
    """Return the first active Amazon Parent coordinator."""
    coordinators = hass.data.get(DOMAIN, {})
    if not coordinators:
        raise HomeAssistantError("Amazon Parent Dashboard integration is not loaded")
    return next(iter(coordinators.values()))


def _register_services(hass: HomeAssistant) -> None:
    """Register Amazon Parent bonus-time services if not already registered."""

    async def handle_add_bonus_time(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass)
        try:
            await coordinator.async_add_bonus_time(
                call.data[ATTR_CHILD], call.data[ATTR_MINUTES]
            )
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err

    async def handle_clear_bonus_time(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass)
        try:
            await coordinator.async_clear_bonus_time(call.data[ATTR_CHILD])
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err

    if not hass.services.has_service(DOMAIN, SERVICE_ADD_BONUS_TIME):
        hass.services.async_register(
            DOMAIN,
            SERVICE_ADD_BONUS_TIME,
            handle_add_bonus_time,
            schema=ADD_BONUS_TIME_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_CLEAR_BONUS_TIME):
        hass.services.async_register(
            DOMAIN,
            SERVICE_CLEAR_BONUS_TIME,
            handle_clear_bonus_time,
            schema=CLEAR_BONUS_TIME_SCHEMA,
        )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Amazon Parent Dashboard from a config entry."""
    addon_url = entry.data[CONF_ADDON_URL]

    try:
        # Create addon cookie client for retrieving cookies
        addon_client = AddonCookieClient(hass, auth_url=addon_url)

        # Check if cookies are available
        if not await addon_client.cookies_available():
            raise ConfigEntryNotReady(
                "No cookies found. Please use the Amazon Parent Auth add-on to authenticate first."
            )

        # Load initial cookies
        cookies = await addon_client.load_cookies()
        if not cookies:
            raise ConfigEntryNotReady("Failed to load cookies from add-on")

        _LOGGER.debug(f"Loaded {len(cookies)} cookies from add-on at {addon_url}")

        # Create API client with addon_client for future cookie refreshes
        api_client = AmazonParentAPIClient(
            hass=hass,
            addon_client=addon_client,
            initial_cookies=cookies,
        )

        # Verify CSRF token is available
        if not api_client.is_authenticated():
            raise ConfigEntryNotReady(
                "CSRF token not found in cookies. Please re-authenticate via add-on."
            )

        # Create coordinator with addon_url for refresh capability
        coordinator = AmazonParentDataUpdateCoordinator(
            hass=hass,
            api_client=api_client,
            addon_url=addon_url,
            entry_id=entry.entry_id,
        )

        # Fetch initial data
        await coordinator.async_config_entry_first_refresh()

        # Store coordinator
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][entry.entry_id] = coordinator

        # Set up platforms
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        _register_services(hass)

        _LOGGER.info(
            f"Amazon Parent Dashboard integration loaded: "
            f"{len(coordinator.household_members)} members, "
            f"{len(coordinator.devices)} devices"
        )

        return True

    except AuthenticationError as err:
        raise ConfigEntryNotReady(f"Authentication failed: {err}") from err
    except AmazonParentException as err:
        raise ConfigEntryNotReady(f"Setup failed: {err}") from err
    except Exception as err:
        _LOGGER.exception("Error setting up Amazon Parent Dashboard")
        raise ConfigEntryNotReady(f"Setup failed: {err}") from err


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        # Clean up coordinator
        coordinator: AmazonParentDataUpdateCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_cleanup()
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, SERVICE_ADD_BONUS_TIME)
            hass.services.async_remove(DOMAIN, SERVICE_CLEAR_BONUS_TIME)

    return unload_ok

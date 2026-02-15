"""The Amazon Parent Dashboard integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .auth.addon_client import AddonCookieClient
from .client.api import AmazonParentAPIClient
from .const import CONF_ADDON_URL, DOMAIN, LOGGER_NAME
from .coordinator import AmazonParentDataUpdateCoordinator
from .exceptions import AmazonParentException, AuthenticationError

_LOGGER = logging.getLogger(LOGGER_NAME)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.SWITCH, Platform.BUTTON]


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
        )

        # Fetch initial data
        await coordinator.async_config_entry_first_refresh()

        # Store coordinator
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][entry.entry_id] = coordinator

        # Set up platforms
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

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

    return unload_ok

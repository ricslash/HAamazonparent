"""The Amazon Parent Dashboard integration."""
import logging

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .client.api import AmazonParentAPIClient
from .const import CONF_ADDON_URL, DOMAIN
from .coordinator import AmazonParentDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.SWITCH, Platform.BUTTON]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Amazon Parent Dashboard from a config entry."""
    addon_url = entry.data[CONF_ADDON_URL]

    try:
        # Fetch cookies from add-on
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{addon_url}/api/cookies",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status != 200:
                    raise ConfigEntryNotReady(
                        f"Failed to fetch cookies from add-on: {resp.status}"
                    )

                data = await resp.json()
                cookies = data.get("cookies", [])

                if not cookies:
                    raise ConfigEntryNotReady("No cookies found in add-on")

        # Create API client
        api_client = AmazonParentAPIClient(cookies)

        # Create coordinator
        coordinator = AmazonParentDataUpdateCoordinator(hass, api_client)

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

    except aiohttp.ClientError as err:
        raise ConfigEntryNotReady(f"Cannot connect to add-on: {err}")
    except Exception as err:
        _LOGGER.exception("Error setting up Amazon Parent Dashboard")
        raise ConfigEntryNotReady(f"Setup failed: {err}")


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        # Clean up coordinator
        coordinator: AmazonParentDataUpdateCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.api_client.close()

    return unload_ok

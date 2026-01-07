"""Config flow for Amazon Parent Dashboard integration."""
import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .const import (
    DOMAIN,
    CONF_ADDON_URL,
    CONF_USE_ADDON_API,
    DEFAULT_ADDON_URL,
)
from .client.api import AmazonParentAPIClient

_LOGGER = logging.getLogger(__name__)


async def validate_cookies(hass: HomeAssistant, addon_url: str) -> dict[str, Any]:
    """Validate cookies from add-on."""
    try:
        # Try to fetch cookies from add-on
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{addon_url}/api/cookies", timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    raise CannotConnect("Failed to connect to authentication add-on")

                data = await resp.json()
                cookies = data.get("cookies", [])

                if not cookies:
                    raise InvalidAuth("No cookies found - please authenticate via add-on first")

                # Verify CSRF token is present
                csrf_token = next(
                    (c["value"] for c in cookies if c.get("name") == "ft-panda-csrf-token"),
                    None
                )
                if not csrf_token:
                    raise InvalidAuth("CSRF token missing - please re-authenticate via add-on")

                # Try to use cookies to fetch household (validates authentication)
                client = AmazonParentAPIClient(cookies)
                try:
                    members = await client.async_get_household()
                    children = [m for m in members if m.is_child]

                    return {
                        "title": f"Amazon Parent Dashboard ({len(children)} children)",
                        "cookies": cookies,
                    }
                finally:
                    await client.close()

    except aiohttp.ClientError as err:
        raise CannotConnect(f"Cannot connect to add-on: {err}")
    except Exception as err:
        _LOGGER.exception("Unexpected error validating cookies")
        raise InvalidAuth(f"Authentication failed: {err}")


class ConfigFlow(config_entries.ConfigFlow, domain = DOMAIN):
    """Handle a config flow for Amazon Parent Dashboard."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await validate_cookies(self.hass, user_input[CONF_ADDON_URL])

                # Check if already configured
                await self.async_set_unique_id("amazonparent")
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=info["title"],
                    data={
                        CONF_ADDON_URL: user_input[CONF_ADDON_URL],
                        CONF_USE_ADDON_API: True,
                    },
                )

            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDON_URL, default=DEFAULT_ADDON_URL): str,
                }
            ),
            errors=errors,
            description_placeholders={
                "addon_url": DEFAULT_ADDON_URL,
            },
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""

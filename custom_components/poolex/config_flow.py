"""Config flow for the Poolex local solar inverter."""

from __future__ import annotations

import ipaddress

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult

from .const import (
    CONF_DEVICE_ID,
    CONF_DEVICE_IP,
    CONF_LOCAL_KEY,
    CONF_POLL_INTERVAL,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    MAX_POLL_INTERVAL,
    MIN_POLL_INTERVAL,
)


def _valid_ip(value: str) -> str:
    """Validate an IPv4 or IPv6 device address."""
    try:
        ipaddress.ip_address(value)
    except ValueError as err:
        raise vol.Invalid("Enter a valid IP address") from err
    return value


DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_DEVICE_IP): str,
        vol.Required(CONF_DEVICE_ID): vol.All(str, vol.Length(min=1)),
        vol.Required(CONF_LOCAL_KEY): vol.All(str, vol.Length(min=16, max=16)),
        vol.Optional(
            CONF_POLL_INTERVAL, default=DEFAULT_POLL_INTERVAL
        ): vol.All(
            vol.Coerce(int),
            vol.Range(min=MIN_POLL_INTERVAL, max=MAX_POLL_INTERVAL),
        ),
    }
)


class PoolexConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle configuration of a Poolex inverter."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        """Handle the user setup form."""
        if user_input is not None:
            errors: dict[str, str] = {}
            try:
                _valid_ip(user_input[CONF_DEVICE_IP])
            except vol.Invalid:
                errors[CONF_DEVICE_IP] = "invalid_ip"

            if not errors:
                await self.async_set_unique_id(user_input[CONF_DEVICE_ID])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="Poolex TSOL-MX800 Balcony",
                    data=user_input,
                )

            return self.async_show_form(
                step_id="user",
                data_schema=DATA_SCHEMA,
                errors=errors,
            )

        return self.async_show_form(step_id="user", data_schema=DATA_SCHEMA)

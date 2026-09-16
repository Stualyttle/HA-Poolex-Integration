"""Poolex local solar inverter integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant


async def _async_update_listener(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Reload the coordinator after options change."""
    await hass.config_entries.async_reload(entry.entry_id)


def _remove_stale_poll_entities(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove health entities replaced by the immediate idle fallback."""
    from homeassistant.helpers import entity_registry as er

    from .const import CONF_DEVICE_ID

    registry = er.async_get(hass)
    stale_unique_ids = {
        f"{entry.data[CONF_DEVICE_ID]}_failed_polls",
        f"{entry.data[CONF_DEVICE_ID]}_polls_until_idle_fallback",
    }
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity.unique_id in stale_unique_ids:
            registry.async_remove(entity.entity_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a Poolex inverter from a config entry."""
    from .const import DOMAIN, PLATFORMS
    from .coordinator import PoolexCoordinator

    hass.data.setdefault(DOMAIN, {})
    _remove_stale_poll_entities(hass, entry)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    coordinator = PoolexCoordinator(hass, entry)
    coordinator.async_set_updated_data(coordinator.initial_data())

    hass.data[DOMAIN][entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    hass.async_create_task(
        coordinator.async_refresh(),
        name=f"{DOMAIN}_{entry.entry_id}_initial_refresh",
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Poolex inverter."""
    from .const import DOMAIN, PLATFORMS
    from .coordinator import PoolexCoordinator

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False

    coordinator: PoolexCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
    await coordinator.async_shutdown()
    return True

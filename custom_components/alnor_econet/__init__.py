"""The Alnor ecoNet HRU integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import AlnorEconetCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.SELECT, Platform.SWITCH]

type AlnorConfigEntry = ConfigEntry[AlnorEconetCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: AlnorConfigEntry) -> bool:
    """Set up Alnor ecoNet from a config entry."""
    coordinator = AlnorEconetCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: AlnorConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

from datetime import timedelta
import aiohttp
from homeassistant.const import Platform
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .api import RemoteGuard, RemoteGuardError
from .parser import ParseError

DOMAIN = "heatguard"
PLATFORMS = [Platform.CLIMATE, Platform.SENSOR]

class HeatGuardCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, api):
        import logging
        super().__init__(hass, logging.getLogger(__name__), name=DOMAIN,
                         config_entry=entry, update_interval=timedelta(seconds=60))
        self.api = api
    async def _async_update_data(self):
        try:
            return await self.api.read()
        except (aiohttp.ClientError, TimeoutError, RemoteGuardError, ParseError, ValueError) as err:
            raise UpdateFailed("Cannot read RemoteGuard account") from err
    async def write(self, changes):
        from homeassistant.exceptions import HomeAssistantError
        try:
            data = await self.api.write(changes)
        except (aiohttp.ClientError, TimeoutError, RemoteGuardError, ValueError) as err:
            raise HomeAssistantError(f"RemoteGuard command failed or outcome is unconfirmed: {err}") from err
        self.async_set_updated_data(data)

async def async_setup_entry(hass, entry):
    settings = dict(entry.data)
    settings["allow_control"] = entry.options.get("allow_control", settings.get("allow_control", False))
    api = RemoteGuard(**settings)
    coordinator = HeatGuardCoordinator(hass, entry, api)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        await api.close()
        raise
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:
        await api.close()
        hass.data[DOMAIN].pop(entry.entry_id, None)
        raise
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True

async def async_reload_entry(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass, entry):
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.api.close()
        return True
    return False

"""Google Home face names on demand from Home Assistant's Nest events."""
from aiohttp import ClientError
from homeassistant.const import Platform
from homeassistant.exceptions import ConfigEntryNotReady

from .const import NEST_EVENT
from .runtime import FaceLookup


async def async_setup_entry(hass, entry):
    lookup = FaceLookup(hass, entry)
    try:
        await lookup.start()
        await lookup.client.access_token()
    except (OSError, ValueError, KeyError, TypeError, ClientError, TimeoutError) as error:
        raise ConfigEntryNotReady('Cannot initialize Google Home face lookup') from error
    entry.runtime_data = lookup
    await hass.config_entries.async_forward_entry_setups(entry, [Platform.SENSOR])
    entry.async_on_unload(hass.bus.async_listen(NEST_EVENT, lookup.accept))
    return True


async def async_unload_entry(hass, entry):
    await entry.runtime_data.stop()
    return await hass.config_entries.async_unload_platforms(entry, [Platform.SENSOR])

"""Config flow for Sonos Alarm."""
import pysonos

from homeassistant import config_entries
from homeassistant.helpers import config_entry_flow

from .const import DOMAIN


async def _async_has_devices(hass):
    """Return if there are devices that can be discovered."""
    return await hass.async_add_executor_job(pysonos.discover)


config_entry_flow.register_discovery_flow(
    DOMAIN, "Sonos Alarm", _async_has_devices, config_entries.CONN_CLASS_LOCAL_PUSH
)

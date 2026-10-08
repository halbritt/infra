"""Last recognized name and diagnostic status; never polls Google."""
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.dispatcher import async_dispatcher_connect


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([FaceSensor(entry)])


class FaceSensor(SensorEntity):
    _attr_should_poll = False
    _attr_name = 'Front door familiar face'
    _attr_icon = 'mdi:face-recognition'

    def __init__(self, entry):
        self.lookup = entry.runtime_data
        self._attr_unique_id = entry.entry_id + '_last_face'

    @property
    def native_value(self):
        return self.lookup.last_name

    @property
    def extra_state_attributes(self):
        return self.lookup.status

    async def async_added_to_hass(self):
        self.async_on_remove(async_dispatcher_connect(
            self.hass, self.lookup.signal, self.async_write_ha_state))

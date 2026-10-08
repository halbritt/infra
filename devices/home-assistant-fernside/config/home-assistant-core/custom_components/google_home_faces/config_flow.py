"""Configure the existing Home OAuth grant and one Nest camera mapping."""
import voluptuous as vol
from homeassistant.config_entries import ConfigFlow
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType

from .const import DOMAIN

SECRET = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
FIELDS = vol.Schema({
    vol.Required('device_id'): str,
    vol.Required('structure_id'): str,
    vol.Required('resource_id'): str,
    vol.Required('client_id'): str,
    vol.Required('client_secret'): SECRET,
    vol.Required('refresh_token'): SECRET,
})


class FaceConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            device = dr.async_get(self.hass).async_get(user_input['device_id'])
            if device is None or not any(domain == 'nest' for domain, _ in device.identifiers):
                errors['base'] = 'invalid_device'
            elif not user_input['resource_id'].startswith('device@'):
                errors['base'] = 'invalid_resource'
            else:
                await self.async_set_unique_id(user_input['resource_id'])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title='Front door familiar faces', data=user_input)
        return self.async_show_form(step_id='user', data_schema=FIELDS, errors=errors)

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        if user_input is not None:
            return self.async_update_reload_and_abort(
                self._get_reauth_entry(), data_updates=user_input)
        return self.async_show_form(step_id='reauth_confirm', data_schema=vol.Schema({
            vol.Required('client_id'): str,
            vol.Required('client_secret'): SECRET,
            vol.Required('refresh_token'): SECRET,
        }))

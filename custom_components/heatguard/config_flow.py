import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from . import DOMAIN
from .api import RemoteGuard, RemoteGuardError

class HeatGuardConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return HeatGuardOptionsFlow()
    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            await self.async_set_unique_id(user_input["uid"])
            self._abort_if_unique_id_configured()
            api = RemoteGuard(**user_input)
            try:
                await api.read()
            except RemoteGuardError:
                errors["base"] = "invalid_auth"
            except (aiohttp.ClientError, TimeoutError):
                errors["base"] = "cannot_connect"
            except ValueError:
                errors["base"] = "invalid_device"
            finally:
                await api.close()
            if not errors:
                return self.async_create_entry(title="IVIK HeatGuard", data=user_input)
        return self.async_show_form(step_id="user", data_schema=vol.Schema({
            vol.Required("email"): str,
            vol.Required("password"): str,
            vol.Required("uid"): str,
            vol.Optional("allow_control", default=False): bool,
        }), errors=errors)

class HeatGuardOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        enabled = self.config_entry.options.get("allow_control", self.config_entry.data.get("allow_control", False))
        return self.async_show_form(step_id="init", data_schema=vol.Schema({
            vol.Required("allow_control", default=enabled): bool,
        }))

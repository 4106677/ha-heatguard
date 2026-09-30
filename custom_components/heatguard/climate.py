from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACMode
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from . import DOMAIN

async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([HeatGuardClimate(hass.data[DOMAIN][entry.entry_id])])

class HeatGuardClimate(CoordinatorEntity, ClimateEntity):
    _attr_has_entity_name = True
    _attr_name = "Теплоноситель"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 1
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL]
    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_unique_id = coordinator.api.uid + "_climate"
        self._attr_device_info = {"identifiers": {(DOMAIN, coordinator.api.uid)}, "name": "IVIK HeatGuard", "manufacturer": "IVIK"}
        self._attr_supported_features = (ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF) if coordinator.api.allow_control else ClimateEntityFeature(0)
    @property
    def settings(self):
        return self.coordinator.data["settings"]
    @property
    def hvac_mode(self):
        if self.settings["id_59"] == "0":
            return HVACMode.OFF
        return HVACMode.HEAT if self.settings["id_60"] == "1" else HVACMode.COOL
    @property
    def current_temperature(self):
        return self.coordinator.data["values"].get("температура поточна", {}).get("value")
    @property
    def target_temperature(self):
        return float(self.settings["id_62" if self.settings["id_60"] == "1" else "id_61"])
    @property
    def min_temp(self):
        return 25 if self.settings["id_60"] == "1" else 6
    @property
    def max_temp(self):
        return 55 if self.settings["id_60"] == "1" else 20
    @property
    def extra_state_attributes(self):
        return {"control_enabled": self.coordinator.api.allow_control, "device_time": self.coordinator.data["device_time"], "temperature_context": "controller current temperature; not confirmed room temperature",
                "command_pending": self.coordinator.data.get("command_pending", False),
                "command_confirmation_failed": self.coordinator.data.get("command_confirmation_failed", False)}
    async def async_set_hvac_mode(self, hvac_mode):
        if hvac_mode not in self._attr_hvac_modes:
            raise ValueError("Unsupported HVAC mode")
        changes = {"id_59": "0"} if hvac_mode == HVACMode.OFF else {"id_59": "1", "id_60": "1" if hvac_mode == HVACMode.HEAT else "0"}
        await self.coordinator.write(changes)
    async def async_set_temperature(self, **kwargs):
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        # Select the register from a fresh form inside the write transaction.
        # Reject combined mode+temperature calls rather than using the wrong range.
        if kwargs.get("hvac_mode") is not None:
            raise ValueError("Set HVAC mode separately, then set temperature")
        await self.coordinator.write({"target_temperature": str(temperature)})
    async def async_turn_off(self):
        await self.coordinator.write({"id_59": "0"})
    async def async_turn_on(self):
        await self.coordinator.write({"id_59": "1"})

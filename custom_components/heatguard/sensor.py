from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from . import DOMAIN

SENSORS = [
    ("температура поточна", "Current temperature", "°C", SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),
    ("температура зовнішня", "Outdoor temperature", "°C", SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),
    ("температура гвп", "DHW temperature (raw)", "°C", SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),
    ("енергоефективність", "Efficiency (reported)", None, None, SensorStateClass.MEASUREMENT),
    ("потужність", "Power", "kW", SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT),
    ("енергія нагріву", "Heating energy", "kWh", SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING),
    ("спожита енергія нагріву", "Heating electricity", "kWh", SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING),
    ("енергія охолодження", "Cooling energy", "kWh", SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING),
    ("спожита енергія охолодження", "Cooling electricity", "kWh", SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING),
    ("залишок до сервісу", "Hours until service", "h", SensorDeviceClass.DURATION, None),
]
async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([HeatGuardSensor(coordinator, i, spec) for i, spec in enumerate(SENSORS)])

class HeatGuardSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    def __init__(self, coordinator, index, spec):
        super().__init__(coordinator)
        self.label, self._attr_name, self._attr_native_unit_of_measurement, self._attr_device_class, self._attr_state_class = spec
        self._attr_unique_id = coordinator.api.uid + f"_sensor_{index}"
        self._attr_device_info = {"identifiers": {(DOMAIN, coordinator.api.uid)}}
        self._attr_entity_registry_enabled_default = self.label != "температура гвп"
    @property
    def native_value(self):
        return self.coordinator.data["values"].get(self.label, {}).get("value")
    @property
    def extra_state_attributes(self):
        return {"device_time": self.coordinator.data["device_time"]}

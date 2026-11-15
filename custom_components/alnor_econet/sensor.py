"""Sensor entities for Alnor ecoNet HRU."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import AlnorConfigEntry
from .const import DOMAIN, REGISTER_MAP, STATE_CLASS_MEASUREMENT
from .coordinator import AlnorEconetCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AlnorConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors from a config entry."""
    coordinator = entry.runtime_data
    # Create an entity for every register in the map (keeps order stable even
    # if a register is briefly absent from one poll).
    entities = [AlnorRegisterSensor(coordinator, key) for key in REGISTER_MAP if key not in ["u81", "u7074", "u7073", "u6630", "u6240", "u84"]]
    async_add_entities(entities)



from homeassistant.components.sensor import SensorDeviceClass

class AlnorUIXMixin:
    @property
    def _reg_info(self):
        from .const import REGISTER_MAP
        rmap = REGISTER_MAP[0] if isinstance(REGISTER_MAP, tuple) else REGISTER_MAP
        key = getattr(self, "_key", getattr(self, "key", None))
        info = rmap.get(key, {})
        return info[0] if isinstance(info, tuple) else info

    @property
    def name(self):
        key = getattr(self, "_key", getattr(self, "key", None))
        return self._reg_info.get("name", f"Register {key}")

    @property
    def unique_id(self):
        key = getattr(self, "_key", getattr(self, "key", None))
        base = getattr(self, "_attr_unique_id", getattr(self, "id", None))
        if not base:
            base = f"alnor_{key}"
        if not base.endswith("_v2"):
            return f"{base}_v2"
        return base

    @property
    def native_value(self):
        key = getattr(self, "_key", getattr(self, "key", None))
        val = self.coordinator.data.get(key)
        
        if val is None or val == "Unavailable":
            return None
            
        reg_info = self._reg_info
        
        if "options" in reg_info:
            try:
                return reg_info["options"].get(int(float(val)), val)
            except (ValueError, TypeError):
                return str(val)
                
        try:
            float_val = float(val)
            if reg_info.get("device_class") == "temperature":
                return round(float_val, 1)
            return int(round(float_val))
        except (ValueError, TypeError):
            return val

    @property
    def native_unit_of_measurement(self):
        return self._reg_info.get("unit")
        
    @property
    def device_class(self):
        dc = self._reg_info.get("device_class")
        if dc == "enum":
            return SensorDeviceClass.ENUM
        return dc

    @property
    def options(self):
        if self.device_class == SensorDeviceClass.ENUM:
            opts = self._reg_info.get("options", {})
            return list(opts.values()) if opts else None
        return getattr(self, "_attr_options", None)

    @property
    def icon(self):
        return self._reg_info.get("icon")


class AlnorRegisterSensor(AlnorUIXMixin, CoordinatorEntity[AlnorEconetCoordinator], SensorEntity):
    """A single Plum u#### register exposed as a sensor."""

    _attr_has_entity_name = True
    _attr_state_class = STATE_CLASS_MEASUREMENT

    def __init__(self, coordinator: AlnorEconetCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._key = key
        _reg_info = REGISTER_MAP.get(key, {})

        name = _reg_info.get("name", key)

        unit = _reg_info.get("unit")

        device_class = _reg_info.get("device_class")
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_unique_id = f"{coordinator.factory_number}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.factory_number)},
            name="Alnor HRU",
            manufacturer="Alnor",
            model=f"ecoNet {coordinator.factory_number}",
        )

    @property
    def available(self) -> bool:
        return super().available and self._key in self.coordinator.data

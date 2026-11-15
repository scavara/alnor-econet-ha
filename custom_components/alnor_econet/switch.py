import time
from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN

SWITCH_TYPES = {
    "u7074": {"name": "Unit State", "icon": "mdi:power", "on_cmd": "H1L0", "off_cmd": "H0L1", "on_val": "1", "off_val": "0"},
    "u7073": {"name": "Auto Mode", "icon": "mdi:refresh-auto", "on_cmd": "H1L0", "off_cmd": "H0L1", "on_val": "1", "off_val": "0"},
    "u6630": {"name": "Schedule Mode", "icon": "mdi:calendar-clock", "on_cmd": "H1L0", "off_cmd": "H0L1", "on_val": "1", "off_val": "0"},
    "u6240": {"name": "Fireplace Mode", "icon": "mdi:fireplace", "on_cmd": "H0L4", "off_cmd": "H0L1", "on_val": "4", "off_val": "0"},
}

async def async_setup_entry(hass, config_entry, async_add_entities):
    if hasattr(config_entry, "runtime_data") and config_entry.runtime_data:
        coordinator = config_entry.runtime_data
    else:
        coordinator = hass.data[DOMAIN][config_entry.entry_id]
        
    installation_id = config_entry.data.get("installation_id")
    factory_number = config_entry.data.get("factory_number")
    
    entities = [AlnorSwitch(coordinator, key, conf, installation_id, factory_number) for key, conf in SWITCH_TYPES.items()]
    async_add_entities(entities)


class AlnorSwitch(CoordinatorEntity, SwitchEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, key, conf, installation_id, factory_number):
        super().__init__(coordinator)
        self._key = key
        self._conf = conf
        self._installation_id = installation_id
        self._factory_number = factory_number
        self._attr_unique_id = f"{installation_id}_{key}_switch"
        self._attr_name = conf["name"]
        self._attr_icon = conf["icon"]
        self._attr_device_info = {
            "identifiers": {(DOMAIN, factory_number)},
            "name": "Alnor HRU",
            "manufacturer": "Alnor",
            "model": f"ecoNet {factory_number}",
        }

    @property
    def is_on(self):
        # Live value of the register, or the optimistic value right after a write.
        write_val = self.coordinator.data.get(self._key)
        if write_val is not None:
            if isinstance(write_val, str) and write_val.startswith("H"):
                return write_val == self._conf["on_cmd"]
            try:
                num = int(float(write_val))
                if self._key == "u6240":
                    return num == 4
                return num > 0
            except (ValueError, TypeError):
                return str(write_val) == str(self._conf["on_val"])
                
        # State unknown (register is only readable over the live channel).
        return None

    async def async_turn_on(self, **kwargs):
        if not hasattr(self.coordinator, "optimistic_overrides"): 
            self.coordinator.optimistic_overrides = {}
        
        self.coordinator.optimistic_overrides[self._key] = {"value": self._conf["on_val"], "timestamp": time.time()}
        
        if self.coordinator.data is not None:
            self.coordinator.data[self._key] = self._conf["on_val"]
            
        self.async_write_ha_state()
        
        await self.coordinator.async_set_parameter(
            self._key, self._conf["on_cmd"], self._installation_id, self._factory_number
        )

    async def async_turn_off(self, **kwargs):
        if not hasattr(self.coordinator, "optimistic_overrides"): 
            self.coordinator.optimistic_overrides = {}
            
        self.coordinator.optimistic_overrides[self._key] = {"value": self._conf["off_val"], "timestamp": time.time()}
        
        if self.coordinator.data is not None:
            self.coordinator.data[self._key] = self._conf["off_val"]
            
        self.async_write_ha_state()
        
        await self.coordinator.async_set_parameter(
            self._key, self._conf["off_cmd"], self._installation_id, self._factory_number
        )

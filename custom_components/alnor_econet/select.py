from homeassistant.components.select import SelectEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN, REGISTER_MAP

async def async_setup_entry(hass, config_entry, async_add_entities):
    if hasattr(config_entry, "runtime_data") and config_entry.runtime_data:
        coordinator = config_entry.runtime_data
    else:
        coordinator = hass.data[DOMAIN][config_entry.entry_id]
        
    installation_id = config_entry.data.get("installation_id")
    factory_number = config_entry.data.get("factory_number")
    
    entities = [
        AlnorModeSelect(coordinator, "u81", installation_id, factory_number),
        AlnorTimeModeSelect(coordinator, installation_id, factory_number)
    ]
    async_add_entities(entities)


class AlnorModeSelect(CoordinatorEntity, SelectEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, key, installation_id, factory_number):
        super().__init__(coordinator)
        self._key = key
        self._installation_id = installation_id
        self._factory_number = factory_number
        self._attr_unique_id = f"{installation_id}_{key}_select_v2"
        
        rmap = REGISTER_MAP[0] if isinstance(REGISTER_MAP, tuple) else REGISTER_MAP
        reg_info = rmap.get(key, {})
        self._attr_name = reg_info.get("name", f"Register {key}")
        self._attr_icon = reg_info.get("icon", "mdi:hvac")
        
        self._options_map = reg_info.get("options", {})
        self._attr_options = list(self._options_map.values())
        
        self._attr_device_info = {
            "identifiers": {(DOMAIN, factory_number)},
            "name": "Alnor HRU",
            "manufacturer": "Alnor",
            "model": f"ecoNet {factory_number}",
        }

    @property
    def icon(self):
        return self._attr_icon or "mdi:hvac"

    @property
    def current_option(self):
        val = self.coordinator.data.get(self._key)
        if val is None:
            return None
        try:
            return self._options_map.get(int(float(val)))
        except (ValueError, TypeError):
            return None

    async def async_select_option(self, option: str) -> None:
        for key, val in self._options_map.items():
            if val == option:
                if self.coordinator.data is not None:
                    if not hasattr(self.coordinator, "optimistic_overrides"): self.coordinator.optimistic_overrides = {}
                import time
                self.coordinator.optimistic_overrides[self._key] = {"value": key, "timestamp": time.time()}
                self.coordinator.data[self._key] = key
                self.async_write_ha_state()
                
                await self.coordinator.async_set_parameter(
                    self._key, key, self._installation_id, self._factory_number
                )
                break


class AlnorTimeModeSelect(CoordinatorEntity, SelectEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, installation_id, factory_number):
        super().__init__(coordinator)
        self._key = "u84"
        self._installation_id = installation_id
        self._factory_number = factory_number
        self._attr_unique_id = f"{installation_id}_u84_select"
        self._attr_name = "Time Mode"
        self._attr_icon = "mdi:clock-fast"
        
        self._cmd_map = {
            "Off": "H0L255",
            "Out": "H1L254",
            "Party": "H2L253",
            "Airing": "H4L251"
        }
        self._val_map = {
            "Off": 0,
            "Out": 1,
            "Party": 2,
            "Airing": 4
        }
        self._attr_options = ["Off", "Out", "Party", "Airing"]
        
        self._attr_device_info = {
            "identifiers": {(DOMAIN, factory_number)},
            "name": "Alnor HRU",
            "manufacturer": "Alnor",
            "model": f"ecoNet {factory_number}",
        }

    @property
    def icon(self):
        return self._attr_icon

    @property
    def current_option(self):
        val = self.coordinator.data.get(self._key)
        if val is None:
            return "Off"
        try:
            num_val = int(float(val))
            for opt, v in self._val_map.items():
                if v == num_val:
                    return opt
        except (ValueError, TypeError):
            pass
        return "Off"

    async def async_select_option(self, option: str) -> None:
        cmd = self._cmd_map.get(option)
        val = self._val_map.get(option)
        if cmd:
            if self.coordinator.data is not None:
                if not hasattr(self.coordinator, "optimistic_overrides"): self.coordinator.optimistic_overrides = {}
                import time
                self.coordinator.optimistic_overrides[self._key] = {"value": val, "timestamp": time.time()}
                self.coordinator.data[self._key] = val
            self.async_write_ha_state()
            
            await self.coordinator.async_set_parameter(
                self._key, cmd, self._installation_id, self._factory_number
            )

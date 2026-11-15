"""Constants for the Alnor ecoNet HRU integration."""
from __future__ import annotations

from homeassistant.const import (
    PERCENTAGE,
    UnitOfTemperature,
    UnitOfVolumeFlowRate,
)
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass

DOMAIN = "alnor_econet"

# --- Cognito / API config (read from the air.alnor.com.pl Amplify frontend) ---
REGION = "eu-central-1"
USER_POOL_ID = "eu-central-1_que8JCEVH"
CLIENT_ID = "3qga0ntgrj7fblcgau24plp2h4"
ARCHIVES_API = "https://api.econetcloud.eu/api"

# --- Config entry keys ---
CONF_EMAIL = "email"
CONF_PASSWORD = "password"  # noqa: S105
CONF_INSTALLATION_ID = "installation_id"
CONF_FACTORY_NUMBER = "factory_number"

DEFAULT_SCAN_INTERVAL = 60  # seconds

# How far back to query so the latest sample is guaranteed present.
LOOKBACK_MINUTES = 30

# ---------------------------------------------------------------------------
# PROVISIONAL register map. The Plum "u####" registers are device-specific and
# their authoritative names/units live in the device profile.json. Values below
# are inferred from a live sample and WILL be finalized from profile.json.
# key -> (friendly name, unit or None, SensorDeviceClass or None)
# ---------------------------------------------------------------------------
REGISTER_MAP: dict[str, tuple[str, str | None, SensorDeviceClass | None]] = {
    # Temperatures (°C) — clustered 12–22 °C, exact roles pending profile.json
    "u6205": ("Temperature u6205", UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE),
    "u6206": ("Temperature u6206", UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE),
    "u6207": ("Temperature u6207", UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE),
    "u6208": ("Temperature u6208", UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE),
    "u6209": ("Temperature u6209", UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE),
    # Fan output (%)
    "u6202": ("Supply fan u6202", PERCENTAGE, None),
    "u6203": ("Exhaust fan u6203", PERCENTAGE, None),
    # Airflow (m³/h)
    "u6812": ("Airflow setpoint u6812", UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR, None),
    "u6813": ("Airflow setpoint u6813", UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR, None),
    "u6828": ("Airflow u6828", UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR, None),
    "u6829": ("Airflow u6829", None, None),
    # Unclassified — pending profile.json (no unit to avoid mislabeling)
    "u6265": ("Register u6265", None, None),
    "u6273": ("Register u6273", None, None),
    "u6322": ("Register u6322", None, None),
    "u6350": ("Register u6350", None, None),
    "u7151": ("Register u7151", None, None),
    "u81": ("Mode u81", None, None),
}

# All register keys we request from the API.
ALL_REGISTERS = list(REGISTER_MAP)

# Numeric-measurement state class applied to all (they are instantaneous reads).
STATE_CLASS_MEASUREMENT = SensorStateClass.MEASUREMENT

# --- UIX OVERRIDES ---
REGISTER_MAP = {
    "u6209": {"name": "Intake Air Temperature", "unit": "°C", "device_class": "temperature"},
    "u6208": {"name": "Exhaust Air Temperature", "unit": "°C", "device_class": "temperature"},
    "u6205": {"name": "Supply Air Temperature", "unit": "°C", "device_class": "temperature"},
    "u6207": {"name": "Extract Air Temperature", "unit": "°C", "device_class": "temperature"},
    "u6206": {"name": "Heat Exchanger Temp", "unit": "°C", "device_class": "temperature"},
    "u6350": {"name": "GHE Temperature", "unit": "°C", "device_class": "temperature"},
    "u6202": {"name": "Supply Fan", "unit": "%", "icon": "mdi:fan"},
    "u6203": {"name": "Exhaust Fan", "unit": "%", "icon": "mdi:fan"},
    "u6265": {"name": "CO2 Level", "unit": "ppm", "device_class": "carbon_dioxide"},
    "u6273": {"name": "Humidity", "unit": "%", "device_class": "humidity"},
    "u6812": {"name": "Target Supply Airflow", "unit": "m³/h", "icon": "mdi:weather-windy"},
    "u6813": {"name": "Target Exhaust Airflow", "unit": "m³/h", "icon": "mdi:weather-windy"},
    "u6828": {"name": "Current Supply Airflow", "unit": "m³/h", "icon": "mdi:weather-windy"},
    "u6829": {"name": "Current Exhaust Airflow", "unit": "m³/h", "icon": "mdi:weather-windy"},
    "u6322": {
        "name": "Bypass State", 
        "device_class": "enum", 
        "options": {0: "Off", 1: "On"}, 
        "icon": "mdi:valve"
    },
    "u81": {
        "name": "Operating Mode", 
        "device_class": "enum", 
        "options": {3: "Mode 1", 4: "Mode 2", 5: "Mode 3", 6: "Pause"}, 
        "icon": "mdi:hvac"
    },
    "u7151": {
        "name": "Work Status", 
        "device_class": "enum", 
        "options": {
            0: "No Status", 1: "Off", 2: "Idle", 3: "Normal", 4: "Heating",
            5: "Cooling", 6: "Dewatering Exchanger", 7: "Cleaning Exchanger",
            8: "Airing/Alarm", 9: "Cooling Heater", 10: "Filter Test",
            11: "Boost", 12: "Defrosting", 13: "Start Delay", 14: "Heat Recovery",
            15: "Cold Recovery", 16: "Service Stop", 17: "Hybrid Cycle 1", 18: "Hybrid Cycle 2"
        }, 
        "icon": "mdi:information"
    }
}

ALL_REGISTERS = list(REGISTER_MAP.keys())

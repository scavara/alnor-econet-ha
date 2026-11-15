# Home Assistant Dashboard Setup Guide

To replicate the official Alnor web portal UI, you can configure a custom "Sidebar" view in Home Assistant using a mix of native cards and the community-developed ApexCharts card.

## 1. Prerequisites
You must install the **ApexCharts Card** to render the multi-axis historical data chart.
1. Go to **HACS** > **Frontend**.
2. Search for **ApexCharts Card** and click **Download**.
3. Reload your browser window.

## 2. Configure the Dashboard View
For the best wide-screen experience, change your dashboard tab to a Sidebar layout.
1. Edit your dashboard and add a new View (Tab) or edit an existing one.
2. Set the **View type** to **Sidebar**.
3. This creates a wide "Main" column for your charts and a narrow "Sidebar" column for your controls and current sensor readings.

> **Important Entity ID Note:** Home Assistant automatically prepends room or device names to entity IDs (e.g., `sensor.technical_room_alnor_hru_...`). You must replace the generic `sensor.alnor_hru_...` entity IDs in the YAML snippets below with your actual entity IDs. You can find your exact IDs by pressing `c` anywhere in Home Assistant and searching for the sensor name.

## 3. Main Area: Charts & History
Add two **Manual** cards to the wide section of your dashboard.

### Card 1: Multi-Axis ApexChart
```yaml
type: custom:apexcharts-card
header:
  show: true
  title: Alnor ecoNet Chart 2.0
  show_states: false
graph_span: 24h
all_series_config:
  stroke_width: 1.5
  curve: smooth
  type: line
apex_config:
  chart:
    height: "450px"
    zoom:
      type: x
      enabled: true
    toolbar:
      show: true
  legend:
    position: bottom
    fontSize: 11px
yaxis:
  - id: temp
    min: 0
    max: 30
    decimals: 1
  - id: airflow
    opposite: true
    min: 0
    max: 300
    decimals: 0
  - id: percent
    show: false
    min: 0
    max: 100
series:
  - entity: sensor.alnor_hru_intake_air_temperature
    name: Inlet Temp
    yaxis_id: temp
    color: "#8B1A1A"
  - entity: sensor.alnor_hru_exhaust_air_temperature
    name: Exhaust Temp
    yaxis_id: temp
    color: "#2E8B57"
  - entity: sensor.alnor_hru_supply_air_temperature
    name: Supply Temp
    yaxis_id: temp
    color: "#DAA520"
  - entity: sensor.alnor_hru_extract_air_temperature
    name: Extract Temp
    yaxis_id: temp
    color: "#483D8B"
  - entity: sensor.alnor_hru_current_supply_airflow
    name: Supply m³/h
    yaxis_id: airflow
    color: "#8B7355"
  - entity: sensor.alnor_hru_current_exhaust_airflow
    name: Exhaust m³/h
    yaxis_id: airflow
    color: "#BDB76B"
  - entity: sensor.alnor_hru_supply_fan
    name: Supply Fan %
    yaxis_id: percent
    color: "#4682B4"
    type: area
    opacity: 0.15
  - entity: sensor.alnor_hru_exhaust_fan
    name: Exhaust Fan %
    yaxis_id: percent
    color: "#C71585"
    type: area
    opacity: 0.15
```

### Card 2: Operating States History
```yaml
type: history-graph
title: Operating States
hours_to_show: 24
entities:
  - entity: switch.alnor_hru_unit_state
    name: Unit state
  - entity: select.alnor_hru_u81_select_v2
    name: Operating Mode
  - entity: sensor.alnor_hru_bypass_state
    name: Bypass status
```

## 4. Sidebar Area: Controls & Current Sensors
Add two **Manual** cards to the narrow sidebar section.

### Card 3: HRU Controls
```yaml
type: entities
title: Alnor HRU
show_header_toggle: false
entities:
  - entity: switch.alnor_hru_auto_mode
  - entity: switch.alnor_hru_fireplace_mode
  - entity: select.alnor_hru_u81_select_v2
    name: Operating Mode
  - entity: switch.alnor_hru_schedule_mode
  - entity: select.alnor_hru_u84_select
    name: Time Mode
  - entity: switch.alnor_hru_unit_state
```

### Card 4: System Status & Readings (Vertical Stack)
```yaml
type: vertical-stack
cards:
  - type: glance
    title: System Status
    entities:
      - entity: sensor.alnor_hru_work_status
        name: Mode
      - entity: sensor.alnor_hru_bypass_state
        name: Bypass
      - entity: sensor.alnor_hru_co2_level
        name: CO2
      - entity: sensor.alnor_hru_humidity
        name: Humidity
  - type: grid
    columns: 2
    square: false
    cards:
      - type: tile
        entity: sensor.alnor_hru_intake_air_temperature
        name: Intake Temp
        icon: mdi:thermometer
        color: light-blue
      - type: tile
        entity: sensor.alnor_hru_supply_air_temperature
        name: Supply Temp
        icon: mdi:thermometer-chevron-up
        color: orange
      - type: tile
        entity: sensor.alnor_hru_extract_air_temperature
        name: Extract Temp
        icon: mdi:thermometer-chevron-down
        color: deep-purple
      - type: tile
        entity: sensor.alnor_hru_exhaust_air_temperature
        name: Exhaust Temp
        icon: mdi:thermometer-lines
        color: green
  - type: entities
    title: Airflow & Fans
    entities:
      - entity: sensor.alnor_hru_supply_fan
        name: Supply Fan
      - entity: sensor.alnor_hru_current_supply_airflow
        name: Supply Airflow
      - entity: sensor.alnor_hru_exhaust_fan
        name: Exhaust Fan
      - entity: sensor.alnor_hru_current_exhaust_airflow
        name: Exhaust Airflow
```

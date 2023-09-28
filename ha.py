# MIT License (MIT)
# Copyright (c) 2023 Stephen Carey
# https://opensource.org/licenses/MIT

# OTA:file:ha.py
# OTA:reboot:true
import binascii
import json
import uos
from machine import unique_id
from tub_config import TubConfig


async def setup_ha_discovery(config_data: TubConfig, version):
    identifier = binascii.hexlify(unique_id()).decode()
    device = {
        "identifiers": identifier,
        "name": "DIY Hot Tub Monitor",
        "sw_version": f"{uos.uname().version}_{version}",
        "model": uos.uname().machine,
        "manufacturer": identifier
    }

    topic = "homeassistant/sensor/hottub/airtemp/config"
    message = {
        "name": "Local Temperature",
        "availability_topic": config_data.available_topic,
        "qos": 0,
        "device_class": "temperature",
        "device": device,
        "state_topic": "esp32/hottub/readings",
        "value_template": "{{ value_json.air_temp }}",
        "unit_of_measurement": f"°{config_data.temp_unit}",
        "unique_id": "local-air-temperature",
        'force_update': True
    }
    await config_data.client.publish(topic, json.dumps(message).encode("UTF-8"), True)

    topic = "homeassistant/sensor/hottub/temp/config"
    message = {
        "name": "Hot Tub Temperature",
        "availability_topic": config_data.available_topic,
        "qos": 0,
        "device_class": "temperature",
        "device": device,
        "state_topic": "esp32/hottub/readings",
        "value_template": "{{ value_json.water_temp }}",
        "unit_of_measurement": f"°{config_data.temp_unit}",
        "unique_id": "hottub-water-temperature",
        'force_update': True
    }
    await config_data.client.publish(topic, json.dumps(message).encode("UTF-8"), True)

    topic = "homeassistant/sensor/hottub/ph/config"
    message = {
        "name": "Hot Tub pH",
        "availability_topic": config_data.available_topic,
        "qos": 0,
        "icon": "mdi:ph",
        "device": device,
        "state_topic": "esp32/hottub/readings",
        "value_template": "{{ value_json.ph }}",
        "unit_of_measurement": "pH",
        "unique_id": "hottub-water-ph",
        'force_update': True
    }
    await config_data.client.publish(topic, json.dumps(message).encode("UTF-8"), True)

    topic = "homeassistant/sensor/hottub/orp/config"
    message = {
        "name": "Hot Tub ORP",
        "availability_topic": config_data.available_topic,
        "qos": 0,
        "icon": "mdi:react",
        "device": device,
        "state_topic": "esp32/hottub/readings",
        "value_template": "{{ value_json.orp }}",
        "unit_of_measurement": "mV",
        "unique_id": "hottub-water-orp",
        'force_update': True
    }
    await config_data.client.publish(topic, json.dumps(message).encode("UTF-8"), True)

    topic = "homeassistant/button/hottub/command/config"
    message = {
        "name": "Hot Tub calibrate",
        "availability_topic": config_data.available_topic,
        "qos": 0,
        "icon": "mdi:ruler-square-compass",
        "device": device,
        "command_topic": "esp32/hottub/command",
        "command_template": "{\"command\": \"calibrate\",\"timestamp\": \"{{ this.last_changed }}\"}",
        "unique_id": "hottub-calibrate",
    }
    await config_data.client.publish(topic, json.dumps(message).encode("UTF-8"), True)

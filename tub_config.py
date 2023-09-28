# MIT License (MIT)
# Copyright (c) 2023 Stephen Carey
# https://opensource.org/licenses/MIT

# OTA:file:tub_config.py
# OTA:reboot:true
import binascii
import json
import sys
import uasyncio as asyncio
from mqtt_local import config
from mqtt_as import MQTTClient


class TubConfig:
    def __init__(self, base_topic, ds):
        self.base_topic = base_topic
        self.ds = ds
        self.version_topic = f'{base_topic}/version'
        self.ota_topic = f'{base_topic}/ota'
        self.command_topic = f'{base_topic}/command'
        self.config_topic = f'{base_topic}/config'
        self.readings_topic = f'{base_topic}/readings'
        self.available_topic = f'{base_topic}/availability'

        config['subs_cb'] = self.handle_incoming_message
        config['connect_coro'] = self.conn_han
        config['wifi_coro'] = self.wifi_han
        config['will'] = [self.available_topic, 'offline', True, 0]

        MQTTClient.DEBUG = False
        self.client = MQTTClient(config)
        self.command = None
        self.config_done = False
        self.temp_unit = None
        self.config = {}
        self.expected_roms = []
        self.air_rom = None
        self.water_rom = None
        self.roms = []

    async def backup_config(self):
        json_data = json.dumps(self.config)
        print(f'Publishing config backup: {json_data}')
        await self.client.publish(f'{self.config_topic}bak', json_data, True)

    async def publish_config(self):
        json_data = json.dumps(self.config)
        print(f'Publishing updated config: {json_data}')
        await self.client.publish(self.config_topic, json_data, True)

    def handle_incoming_message(self, topic, msg, retained):
        topic_string = str(topic, 'UTF-8')
        msg_string = str(msg, 'UTF-8')
        if len(msg_string) < 500:
            print(f'{topic_string}: {msg_string}')
        else:
            print(f'Got a big message on {topic_string}...')
        if topic == self.config_topic:
            try:
                self.config = json.loads(msg_string)
                if 'ph_neutral_calibration' not in self.config or 'ph_acid_calibration' not in self.config:
                    print(
                        'Values for "ph_neutral_calibration" and "ph_acid_calibration" must be specified.  Good defaults are 1500.0 and 2032.44 respectively')
                elif 'air_rom_reg_num' not in self.config or 'water_rom_reg_num' not in self.config:
                    print(
                        'Values for "air_rom_reg_num" and "water_rom_reg_num" must be specified.  The hex values should be printed during startup.')
                else:
                    self.temp_unit = 'F' if self.config.get('temp_unit', 'F') == 'F' else 'C'
                    self.expected_roms.clear()
                    self.air_rom = self.config['air_rom_reg_num']
                    self.expected_roms.append(self.air_rom)
                    self.water_rom = self.config['water_rom_reg_num']
                    self.expected_roms.append(self.water_rom)
                    self.init_roms()
                    self.config_done = True
            except Exception as e:
                print(f'Problem with tub config: {e}')
                sys.print_exception(e)
        elif topic == self.command_topic:
            self.command = msg_string
        elif topic == self.ota_topic:
            import ota
            ota.process_ota_msg(msg_string)

    def init_roms(self):
        self.roms = [binascii.hexlify(x).decode() for x in self.ds.scan()]
        print("Scan found these ROMS:")
        for rom in self.roms:
            print(f'ROM registration number hex: {rom}')

    async def wifi_han(self, state):
        print('Wifi is ', 'up' if state else 'down')
        await asyncio.sleep(1)

    # If you connect with clean_session True, must re-subscribe (MQTT spec 3.1.2.4)
    async def conn_han(self, client):
        await client.subscribe(self.ota_topic, 0)
        await client.subscribe(self.command_topic, 0)
        await client.subscribe(self.config_topic, 0)
        await self.online()

    async def online(self):
        await self.client.publish(self.available_topic, 'online', retain=True, qos=0)

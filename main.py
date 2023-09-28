# MIT License (MIT)
# Copyright (c) 2023 Stephen Carey
# https://opensource.org/licenses/MIT

# OTA:file:main.py
# OTA:reboot:true
import binascii
import ds18x20
import json
import onewire
import sys
import uasyncio as asyncio

from machine import ADC, Pin
from display_handler import DisplayHandler
from tub_config import TubConfig

BASE_TOPIC = 'esp32/hottub'
COMMAND_TOPIC = f'{BASE_TOPIC}/command'
AVAILABLE_TOPIC = f'{BASE_TOPIC}/availability'

NUM_CALIBRATION_READINGS = 42
VERSION = 3

air_temp = 0
water_temp = 0
ph_val = 0
orp_val = 0
new_neutral_voltages = []
new_acid_voltages = []

# ph is 0V to 3.0V in
ph_pin = ADC(Pin(35))
ph_pin.atten(ADC.ATTN_11DB)
# orp is -2V to +2V in though we should never see anything negative for this use
orp_pin = ADC(Pin(34))
orp_pin.atten(ADC.ATTN_11DB)

temp_pin = Pin(4, Pin.IN, pull=Pin.PULL_UP)
cover_state_pin = Pin(5, Pin.IN, pull=Pin.PULL_UP)

ds = ds18x20.DS18X20(onewire.OneWire(temp_pin))
tc = TubConfig(BASE_TOPIC, ds)
display_handler = DisplayHandler(sda_pin_num=21, scl_pin_num=22, on_off_pin_num=26,
                                 num_calibration_readings=NUM_CALIBRATION_READINGS)


def read_ph_mv():
    return ph_pin.read_uv() / 1000


def read_average(num_readings, read_func):
    total = 0
    for _ in range(num_readings):
        total += read_func()
    return total / num_readings


def read_ph():
    milli_voltage = read_ph_mv()
    calibrated_neutral_v = tc.config['ph_neutral_calibration']
    calibrated_acid_v = tc.config['ph_acid_calibration']

    # https://github.com/DFRobot/DFRobot_PH/blob/master/DFRobot_PH.cpp
    # can't find any temp adjustment data but things seem to work well w/o it at hot tub temps
    slope = (7.0 - 4.0) / ((calibrated_neutral_v - 1500.0) / 3.0 - (calibrated_acid_v - 1500.0) / 3.0)
    intercept = 7.0 - slope * (calibrated_neutral_v - 1500.0) / 3.0

    ph_value = slope * (milli_voltage - 1500.0) / 3.0 + intercept  # y = k*x + b

    print(f'Adjusted PH: {ph_value}, raw V: {milli_voltage / 1000}')
    return ph_value


def read_orp():
    voltage = orp_pin.read_uv() / 1_000_000
    orp_mv = (2.5 - voltage) / 1.037 * 1000.0  # * 1000 to get mV
    print(f'ORP mV: {orp_mv}, raw V: {voltage}')
    return orp_mv


async def read_temps():
    global water_temp, air_temp
    temp_error = ''

    if len(tc.roms) != 2:
        tc.init_roms()
    if len(tc.roms) > 0:
        ds.convert_temp()
        await asyncio.sleep_ms(750)
        for rom in tc.expected_roms:
            try:
                if rom in tc.roms:
                    current_temp = ds.read_temp(binascii.unhexlify(rom))
                    if tc.temp_unit == 'F':
                        current_temp = current_temp * 1.8 + 32

                    rounded_temp = round(current_temp, 1)
                    if rom == tc.air_rom:
                        air_temp = rounded_temp
                    else:
                        water_temp = rounded_temp
                else:
                    temp_error = f'Missing expected rom: {rom}, these were detected: {tc.roms}'
                await asyncio.sleep(1)
            except Exception as e:
                temp_error = str(e)
                print(f'Problem reading temp: {e}')
    return water_temp, air_temp, temp_error


# The calibration process takes PH readings every second until it has multiple readings for PH 4
# and PH 7.  It then takes the average of the last few readings of each PH and updates the config
# with those calibration values.
async def calibrate():
    print("Calibration starting...")
    new_acid_voltages.clear()
    new_neutral_voltages.clear()
    while len(new_neutral_voltages) != NUM_CALIBRATION_READINGS or len(new_acid_voltages) != NUM_CALIBRATION_READINGS:
        # let's get 42 readings in each range, average the last 12 and send the new calibration data
        read_voltage = read_ph_mv()

        if 1322 < read_voltage < 1678:
            if len(new_neutral_voltages) < NUM_CALIBRATION_READINGS:
                new_neutral_voltages.append(read_voltage)
        elif 1854 < read_voltage < 2210:
            if len(new_acid_voltages) < NUM_CALIBRATION_READINGS:
                new_acid_voltages.append(read_voltage)

        display_handler.update_values(tc.command, {}, new_neutral_voltages,
                                      new_acid_voltages, tc.temp_unit)
        await asyncio.sleep(1)
        print(f'New neutral readings: {len(new_neutral_voltages)}, new acid readings: {len(new_acid_voltages)}')

    # don't include first 30 readings in average
    average_neutral_voltage = sum(new_neutral_voltages[30:]) / (NUM_CALIBRATION_READINGS - 30)
    average_acid_voltage = sum(new_acid_voltages[30:]) / (NUM_CALIBRATION_READINGS - 30)

    # backup existing config
    await tc.backup_config()
    # write new config
    tc.config['ph_neutral_calibration'] = average_neutral_voltage
    tc.config['ph_acid_calibration'] = average_acid_voltage
    try:
        command_dict = json.loads(tc.command)
        tc.config['last_calibration'] = command_dict.get('timestamp', 'Unknown')
    except Exception as e:
        print(f"Problem parsing command json: {tc.command}")
        sys.print_exception(e)
    await tc.publish_config()
    print("Calibration complete!")


async def main():
    await tc.client.connect()
    await asyncio.sleep(2)  # Give broker time
    await tc.online()
    await display_handler.init()
    try:
        import ha
        print("ha module found, configuring HA discovery.")
        await ha.setup_ha_discovery(tc, VERSION)
    except ImportError:
        print("ha module not found, not configuring HA discovery.")
    await tc.client.publish(tc.version_topic, str(VERSION), retain=True)
    global air_temp, water_temp, ph_val, orp_val
    while True:
        try:
            while not tc.config_done:
                print("Config not found, will check again in a few secs...")
                await asyncio.sleep(5)
            if tc.command:
                await calibrate()
                tc.command = None
            else:
                ph_val = read_average(5, read_ph)
                orp_val = read_average(5, read_orp)
                air_temp, water_temp, temp_error = await read_temps()
                new_data = {}
                new_data['ph'] = ph_val
                new_data['orp'] = orp_val
                new_data['water_temp'] = water_temp
                new_data['air_temp'] = air_temp
                new_data['temp_unit'] = tc.temp_unit
                new_data['temp_error'] = temp_error
                new_data['cover_state'] = cover_state_pin.value()
                display_handler.update_values(tc.command, new_data, [], [], tc.temp_unit)
                print(f"Publishing updated data: {new_data}")
                await tc.client.publish(tc.readings_topic, json.dumps(new_data), True)
                await asyncio.sleep(60)
        except Exception as e:
            print("Problem in main loop: ", e)
            await asyncio.sleep(5)


try:
    loop = asyncio.get_event_loop()
    loop.create_task(main())
    loop.create_task(display_handler.show_display())
    loop.run_forever()
finally:
    tc.client.close()
    asyncio.stop()

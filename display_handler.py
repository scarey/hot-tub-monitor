# MIT License (MIT)
# Copyright (c) 2023 Stephen Carey
# https://opensource.org/licenses/MIT

# OTA:file:display_handler.py
# OTA:reboot:false
import ssd1306

from machine import Pin, SoftI2C
import uasyncio as asyncio

TEXT_ROW_HEIGHT = 9


class DisplayHandler:
    def __init__(self, sda_pin_num, scl_pin_num, on_off_pin_num, num_calibration_readings, row_height=TEXT_ROW_HEIGHT):
        self.on_off_pin = Pin(on_off_pin_num, Pin.IN, pull=Pin.PULL_UP)
        self.row_height = row_height
        self.oled = None
        self.i2c = SoftI2C(sda=Pin(sda_pin_num), scl=Pin(scl_pin_num), freq=100000)

        self.command = None
        self.data = None
        self.temp_unit = 'F'
        self.new_neutral_voltages = None
        self.new_acid_voltages = None
        self.num_calibration_readings = num_calibration_readings

    async def init(self):
        print(f'I2C scan results: {self.i2c.scan()}')
        try:
            self.oled = ssd1306.SSD1306_I2C(128, 64, self.i2c)

            # startup tests
            self.oled.fill(1)
            self.oled.show()
            await asyncio.sleep(1)
            print("OLED init success")
        except Exception as e:
            print("OLED init failed: {}".format(e))

    def is_display_on(self):
        return self.on_off_pin.value() == 0

    def update_values(self, command, data, new_neutral_voltages, new_acid_voltages,
                      temp_unit):
        self.command = command
        self.data = data
        self.temp_unit = temp_unit
        self.new_neutral_voltages = new_neutral_voltages
        self.new_acid_voltages = new_acid_voltages

    def show_rows(self, rows):
        self.oled.fill(0)
        for i in range(len(rows)):
            self.oled.text(rows[i], 0, self.row_height * i, 1)
        self.oled.show()

    async def show_display(self):
        while True:
            if self.oled:
                self.oled.fill(0)
                if not self.command:
                    if self.is_display_on() and self.data.get('air_temp', None):
                        rows = [
                            f'Air temp: {round(self.data["air_temp"], 1)}{self.temp_unit}',
                            f'pH:       {round(self.data["ph"], 1)}',
                            f'ORP:      {round(self.data["orp"])}mV',
                            f'H2O temp: {round(self.data["water_temp"], 1)}{self.temp_unit}'
                        ]
                        self.show_rows(rows)
                    await asyncio.sleep(5)
                else:  # calibrate
                    if self.is_display_on():
                        num_acid_readings = len(self.new_acid_voltages)
                        num_neutral_readings = len(self.new_neutral_voltages)
                        rows = [
                            "Calibrating...",
                            f'ph4 count: {num_acid_readings}/{self.num_calibration_readings}',
                            f'ph4 avg: {"N/A" if num_acid_readings == 0 else sum(self.new_acid_voltages) / num_acid_readings}mV',
                            f'ph7 count: {len(self.new_neutral_voltages)}/{self.num_calibration_readings}',
                            f'ph7 avg: {"N/A" if num_neutral_readings == 0 else sum(self.new_neutral_voltages) / num_neutral_readings}mV'
                        ]
                        self.show_rows(rows)
                    await asyncio.sleep(1)
                self.oled.show()
            else:
                await asyncio.sleep(1)

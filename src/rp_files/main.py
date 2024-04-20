# this works for only single packet sends (170 LEDs or less) due to the max send of 512 bytes

import sys
import machine
import os
import time

sys.path.append("")
from custom_neopixel import C_Neopixel


from micropython import const

import uasyncio as asyncio
import aioble
import bluetooth

import random
import struct

led = machine.Pin("LED", machine.Pin.OUT)

MAX_LEN = 512

# To match with UUIDs in ArduinoBLE side,
# they are re-assigned following ArduinoBLE.
_ENV_LED_UUID = bluetooth.UUID('6E400001-B5A3-F393-E0A9-E50E24DCCA9E')
_ENV_LED_CONTROL_UUID = bluetooth.UUID('6E400002-B5A3-F393-E0A9-E50E24DCCA9E')

# I don't what appearance should be used, so I choice unknown
# key="0" value="Unknown" description="None"
_ADV_APPEARANCE_UNKNOWN = const(0)

# How frequently to send advertising beacons.
_ADV_INTERVAL_MS = 250_000

# Register GATT server.
service = aioble.Service(_ENV_LED_UUID)
characteristic = aioble.BufferedCharacteristic(
    service, _ENV_LED_CONTROL_UUID, write=True, read=True, notify=True, capture=True, max_len=MAX_LEN)
aioble.register_services(service)

numpix = 170
strip = C_Neopixel(numpix, 1, 18, delay=0)
pix_arr = [(0, 0, 0)] * numpix
max_iter = min((MAX_LEN-1)//3, numpix)

# Serially wait for connections. Don't advertise while a central is
# connected.
async def connection_manager():
    blink_task = asyncio.create_task(blink())

    while True:
        async with await aioble.advertise(
            _ADV_INTERVAL_MS,
            name="ASLight",
            services=[_ENV_LED_UUID],
            appearance=_ADV_APPEARANCE_UNKNOWN,
        ) as connection:
            print("Connection from", connection.device)
            blink_task.cancel()
            led.on()
            while connection.is_connected():
                await asyncio.sleep_ms(500)
            print("Disconnected")
            blink_task = asyncio.create_task(blink())



async def read_task():
    while True:
        await characteristic.written()
        data = characteristic.read()
        strip.show(data, 1)

async def blink():
    while True:
        await asyncio.sleep_ms(1000)
        led.toggle()

# Run the tasks.
async def main():
    t1 = asyncio.create_task(connection_manager())
    t2 = asyncio.create_task(read_task())
    await asyncio.gather(t1, t2)


asyncio.run(main())




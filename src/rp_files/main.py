"""
MicroPython v1.21 exercise run on Espressif ESP32-C3-DevKitM-1 using aioble lib.
Play the role as BLE Peripheral of LED.

As the role in ArduinoBLE examples>Peripheral>LED

- Setup as BLE Peripheral of LED, wait connection from Central device.
- Turn ON/OFF onboard LED according to received command:
  0 - Turn OFF LED
  1 - Turn ON LED
"""
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
import array

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

NUM_PIX = 300


MAX_PIX_PER_PACKET = 170

NUM_PACKETS_REQUIRED = (NUM_PIX // MAX_PIX_PER_PACKET) + 1 # each 512 byte packet can send 170 RGB values


FINAL_TRANSCRIPTION_LEN = NUM_PIX % MAX_PIX_PER_PACKET # how many rgb values does the final nth of n packets need to contain?
FIRST_TRANSCRIPTION_LEN = FINAL_TRANSCRIPTION_LEN if NUM_PACKETS_REQUIRED == 1 else MAX_PIX_PER_PACKET

strip = C_Neopixel(NUM_PIX, 1, 18, delay=0)
max_iter = min((MAX_LEN-2)//3, NUM_PIX)

class IntWrapper:
        i = 0
        def set_val(self, i):
            self.i = 0

        def get_val(self):
            return self.i

        def increment(self):
            self.i += 1


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
            strip.off()

async def to_lights(to_lights_arr, to_light_evt, to_light_lock, is_altering_lights):
    while True:
        async with to_light_lock: # set to_lights to accepting
            is_altering_lights.set_val(0)
        #print("WAITING")
        await to_light_evt.wait() # wait until we have a new array to send out
        to_light_evt.clear()
        strip.show(to_lights_arr) # write to the LEDS


async def transcribe(b_data, t_arr, to_lights_arr, num_processed, npr_lock, offset, length, to_light_evt, to_light_lock, is_altering_lights):
    # transcribe the byte data into the current array, and if this is the last thread for this frame, flush to the light!

    for i in range(length):
        t_arr[i + offset] = int(b_data[3 * i + 2] << 16) + int(b_data[3 * i + 3] << 8) + int(b_data[3 * i + 4]) # skip first 2 header bits
    #print(t_arr)
    async with npr_lock:
        num_processed.increment()
        if num_processed.get_val() == NUM_PACKETS_REQUIRED: #this transcription is finished! flush to lights
            async with to_light_lock:
                #print(f"CHECKING TO ADJUST LIGHTS? {not is_altering_lights.get_val()}")
                if not is_altering_lights.get_val(): # if lights writer is free, send data to it and then flip
                    #print("ADJUSTING LIGHTS!")
                    t_arr[:], to_lights_arr[:] = to_lights_arr[:], t_arr[:]
                    is_altering_lights.set_val(1) # set transcribing state to true
                    to_light_evt.set() # let to_lights know it can begin adjusting
                else:
                    pass
                    #print("NOT READY TO ADJUST LIGHTS! SKIPPING :(")
        else:
            pass
            #print(f"INCREMENTING TRANSCRIBE TO {num_processed.get_val()}!")


async def read_task(t_arr, to_lights_arr, to_light_evt, to_light_lock, is_altering_lights):
    num_processed = IntWrapper()
    npr_lock = asyncio.Lock() # lock for num processed
    transcribe_threads = [None] * NUM_PACKETS_REQUIRED
    num_started = 0
    cur_idx = 0

    while True:
        await characteristic.written()
        data = characteristic.read()
        #print("GOT DATA!")
        frame_idx = data[0] # a cycling index from 0 to 255 to keep track of succession of frames
        packet_idx = data[1] # which packet (first 170, 2nd 170 etc) the data comes from
        packet_start = packet_idx * MAX_PIX_PER_PACKET
        #print(f"FRAME {frame_idx}, PACKET {packet_start}")
        if (packet_start == 0): #new frame 0-packet!
            start_new_frame = False
            if num_started < NUM_PACKETS_REQUIRED: # we just got a new starting packet, and we missed one of our old ones! bad previous frame :(
                #print("BAD PREVIOUS FRAME, killing!")
                start_new_frame = True

                for thread in transcribe_threads: # kill any still-existing old processes and start again.
                    if thread is not None:
                        thread.cancel()
            async with npr_lock:
                start_new_frame = (num_processed.get_val() == NUM_PACKETS_REQUIRED) or start_new_frame # start a new frame if the previous one has finished, or if we missed out on a packet
                #print(f"STARTING NEW FRAME? {start_new_frame}")
                if (start_new_frame):
                    num_processed.set_val(0)
                transcribe_threads[0] = asyncio.create_task(transcribe(data, t_arr, to_lights_arr,
                                                                       num_processed, npr_lock, 0, FIRST_TRANSCRIPTION_LEN,
                                                                       to_light_evt, to_light_lock, is_altering_lights))
            num_started = 1
            cur_idx = frame_idx

        else: # this is a follow-up packet
            if frame_idx == cur_idx: # this is a follow-up packet to the current frame
                #print("FOLLOW UP PACKET IS CURRENT!")
                n_pix_in_packet = (FINAL_TRANSCRIPTION_LEN) if (packet_idx == NUM_PACKETS_REQUIRED - 1) else MAX_PIX_PER_PACKET
                #print(f"{n_pix_in_packet} PIX IN PACKET")
                transcribe_threads[packet_idx] = asyncio.create_task(transcribe(data,
                                                                                t_arr,
                                                                                to_lights_arr,
                                                                                num_processed,
                                                                                npr_lock,
                                                                                packet_start,
                                                                                n_pix_in_packet,
                                                                                to_light_evt,
                                                                                to_light_lock,
                                                                                is_altering_lights))
                num_started += 1
            else: # this is not a follow-up packet to the current frame, so current frame is invalid, we'll let it get wiped once a new 0-packet gets sent
                pass

#        strip.show(data, 1)

async def blink():
    while True:
        await asyncio.sleep_ms(1000)
        led.toggle()

# Run the tasks.
async def main():
    is_altering_lights = IntWrapper() # is an int, we use it as a boolean 1 to signify lights are being modified, 0 otherwise
    to_light_evt = asyncio.Event() # listener to tell to_lights to start altering lights
    to_light_lock = asyncio.Lock() # lock for is_altering_lights
    t_arr = array.array("I", [0] * NUM_PIX) # transcription array
    to_lights_arr = array.array("I", [0] * NUM_PIX) # flush to lights array
    t1 = asyncio.create_task(connection_manager())
    t2 = asyncio.create_task(read_task(t_arr, to_lights_arr, to_light_evt, to_light_lock, is_altering_lights))
    t3 = asyncio.create_task(to_lights(to_lights_arr, to_light_evt, to_light_lock, is_altering_lights))
    await asyncio.gather(t1, t2)


asyncio.run(main())




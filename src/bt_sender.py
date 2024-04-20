import asyncio
from bleak import BleakScanner, BleakClient, BleakGATTCharacteristic
import struct
import random

# these are standard, also defined in the micropython files
UART_SERVICE_UUID = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
UART_RX_CHAR_UUID = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
UART_TX_CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"


DEVICE_NAME = "ASLight"
MAX_BYTES_ACCEPTED = 512
NUM_LEDS = 300

NUM_CONNECTION_ATTEMPTS = 10
# COLORS = [(69, 227, 255), (235, 64, 52), (255, 212, 41), (132, 199, 44), (80, 199, 44), (44, 199, 109), (69, 255, 215), (69, 116, 255), (140, 69, 255), (230, 69, 255), (255, 69, 150)]
# COLORS = [(x[0] // 3, x[1] // 3, x[2] // 3) for x in COLORS]
# COLORS = [(0, 0, 0), (255, 0, 0), (0, 255, 0), (0, 0, 255)]
COLORS = [(50, 50, 50)]


async def repeated_data_send():
    def match_name(d, adv):
        return d.name == DEVICE_NAME

    async def send_arr(arr, frame_id):
        assert len(arr) == NUM_LEDS
        start_index = 0
        packet_num = 0
        max_len = (MAX_BYTES_ACCEPTED - 1) // 3
        frame_id %= 255
        while start_index < NUM_LEDS:
            sent_arr_len = min(max_len, NUM_LEDS - start_index)
            outarr = [frame_id, packet_num] + [x for tup in arr[start_index:start_index + sent_arr_len] for x in tup]
            byte_arr = struct.pack('B' * len(outarr), *outarr)
            await client.write_gatt_char(rx_char, byte_arr, response=True)
            start_index += max_len
            packet_num += 1


    device = None
    for i in range(NUM_CONNECTION_ATTEMPTS):
        device = await BleakScanner.find_device_by_filter(match_name)
        if device is None:
            print(f"Device not found ({i+1})")
        else:
            break
    if device is None:
        print("Failed to find device!")
        return
    print("Found device!")
    async with BleakClient(device, disconnected_callback=handle_disconnect) as client:
        await client.connect()
        nus = client.services.get_service(UART_SERVICE_UUID)
        rx_char = nus.get_characteristic(UART_RX_CHAR_UUID)
        # data = chr(3) + "\0a\0" * 100
        # hex_representation = " ".join(["{:02x}".format(byte) for byte in data.encode("utf-8")])
        # print("hex:", hex_representation)
        # await client.write_gatt_char(rx_char, data.encode("utf-8"), response=True)
        # print("sent:", data)
        frame = 0
        while True:
            await send_arr([random.choice(COLORS)] * NUM_LEDS, frame)
            # await send_arr(random.choices(COLORS, k=NUM_LEDS), frame)
            frame += 1


def handle_disconnect(_: BleakClient):
    print("Disconnected!")
    # cancelling all tasks effectively ends the program
    for task in asyncio.all_tasks():
        task.cancel()


if __name__ == "__main__":
    asyncio.run(repeated_data_send())




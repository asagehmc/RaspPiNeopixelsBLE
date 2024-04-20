import array, time
from machine import Pin
import rp2


# PIO state machine for RGB. Pulls 24 bits (rgb -> 3 * 8bit) automatically
@rp2.asm_pio(sideset_init=rp2.PIO.OUT_LOW, out_shiftdir=rp2.PIO.SHIFT_LEFT, autopull=True, pull_thresh=24)
def ws2812():
    T1 = 2
    T2 = 5
    T3 = 3
    wrap_target()
    label("bitloop")
    out(x, 1).side(0)[T3 - 1]
    jmp(not_x, "do_zero").side(1)[T1 - 1]
    jmp("bitloop").side(1)[T2 - 1]
    label("do_zero")
    nop().side(0)[T2 - 1]
    wrap()


# we need this because Micropython can't construct slice objects directly, only by
# way of supporting slice notation.
# So, e.g. slice_maker[1::4] gives a slice(1,None,4) object.
class slice_maker_class:
    def __getitem__(self, slc):
        return slc


slice_maker = slice_maker_class()


# Delay here is the reset time. You need a pause to reset the LED strip back to the initial LED
# however, if you have quite a bit of processing to do before the next time you update the strip
# you could put in delay=0 (or a lower delay)
#
# Class supports different order of individual colors (GRB, RGB, WRGB, GWRB ...). In order to achieve
# this, we need to flip the indexes: in 'RGBW', 'R' is on index 0, but we need to shift it left by 3 * 8bits,
# so in it's inverse, 'WBGR', it has exactly right index. Since micropython doesn't have [::-1] and recursive rev()
# isn't too efficient we simply do that by XORing (operator ^) each index with 3 (0b11) to make this flip.
# When dealing with just 'RGB' (3 letter string), this means same but reduced by 1 after XOR!.
# Example: in 'GRBW' we want final form of 0bGGRRBBWW, meaning G with index 0 needs to be shifted 3 * 8bit ->
# 'G' on index 0: 0b00 ^ 0b11 -> 0b11 (3), just as we wanted.
# Same hold for every other index (and - 1 at the end for 3 letter strings).

class C_Neopixel:
    # Micropython doesn't implement __slots__, but it's good to have a place
    # to describe the data members...
    # __slots__ = [
    #    'num_leds',   # number of LEDs
    #    'pixels',     # array.array('I') of raw data for LEDs
    #    'mode',       # mode 'RGB' etc
    #    'W_in_mode',  # bool: is 'W' in mode
    #    'sm',         # state machine
    #    'shift',      # shift amount for each component, in a tuple for (R,B,G,W)
    #    'delay',      # delay amount
    #    'brightnessvalue', # brightness scale factor 1..255
    # ]

    def __init__(self, num_leds, state_machine, pin, delay=0.0001):
        self.pixels = array.array("I", [0] * num_leds)
        self.sm = rp2.StateMachine(state_machine, ws2812, freq=8000000, sideset_base=Pin(pin))
        self.sm.active(1)
        self.num_leds = num_leds
        self.brightnessvalue = 255

    def __len__(self):
        return self.num_leds

    def __getitem__(self, idx):
        return self.get_pixel(idx)

    def show(self, byte_arr, offset):
        for i in range(self.num_leds):
            self.pixels[i] = int(byte_arr[3 * i + offset] << 16) + int(byte_arr[3 * i + 1 + offset] << 8) + int(
                byte_arr[3 * i + 2 + offset])
        self.sm.put(self.pixels, 8)




#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Urwid LCD display module
#    Copyright (C) 2010  Ian Ward
#
#    This library is free software; you can redistribute it and/or
#    modify it under the terms of the GNU Lesser General Public
#    License as published by the Free Software Foundation; either
#    version 2.1 of the License, or (at your option) any later version.
#
#    This library is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#    Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public
#    License along with this library; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#
# Urwid web site: http://excess.org/urwid/


from display_common import BaseScreen
from escape import utf8decode


class LCDScreen(BaseScreen):
    def set_terminal_properties(self, colors=None, bright_is_bold=None,
        has_underline=None):
        pass

    def set_mouse_tracking(self):
        pass

    def start(self):
        pass

    def stop(self):
        pass

    def set_input_timeouts(self, *args):
        pass

    def reset_default_terminal_palette(self, *args):
        pass

    def run_wrapper(self,fn):
        return fn()
    
    def draw_screen(self, (cols, rows), r ):
        pass

    def clear(self):
        pass

    def get_cols_rows(self):
        return self.DISPLAY_SIZE



class CFLCDScreen(LCDScreen):
    """
    Common methods for Crystal Fontz LCD displays
    """
    KEYS = [None, # no key with code 0
        'up_press', 'down_press', 'left_press',
        'right_press', 'enter_press', 'exit_press',
        'up_release', 'down_release', 'left_release',
        'right_release', 'enter_release', 'exit_release',
        'ul_press', 'ur_press', 'll_press', 'lr_press', 
        'ul_release', 'ur_release', 'll_release', 'lr_release']
    CMD_PING = 0
    CMD_VERSION = 1
    CMD_CLEAR = 6
    CMD_CURSOR_POSITION = 11 # data = [col, row]
    CMD_CURSOR_STYLE = 12 # data = [style (0-4)]
    CMD_LCD_CONTRAST = 13 # data = [contrast (0-255)]
    CMD_BACKLIGHT = 14 # data = [power (0-100)]
    CMD_LCD_DATA = 31 # data = [col, row] + text
    CMD_GPO = 34 # data = [pin(0-12), value(0-100)]

    CURSOR_NONE = 0
    CURSOR_BLINKING_BLOCK = 1
    CURSOR_UNDERSCORE = 2
    CURSOR_BLINKING_BLOCK_UNDERSCORE = 3
    CURSOR_INVERTING_BLINKING_BLOCK = 4

    colors = 1
    has_underline = False

    def __init__(self, device_path, baud):
        """
        device_path -- eg. '/dev/ttyUSB0'
        baud -- baud rate
        """
        self.device_path = device_path
        from serial import Serial
        self._device = Serial(device_path, baud, timeout=0)


    @classmethod
    def get_crc(cls, buf):
        # This seed makes the output of this shift based algorithm match
        # the table based algorithm. The center 16 bits of the 32-bit
        # "newCRC" are used for the CRC. The MSB of the lower byte is used
        # to see what bit was shifted out of the center 16 bit CRC
        # accumulator ("carry flag analog");
        newCRC = 0x00F32100
        for byte in buf:
            # Push this byte’s bits through a software
            # implementation of a hardware shift & xor.
            for bit_count in range(8):
                # Shift the CRC accumulator
                newCRC >>= 1
                # The new MSB of the CRC accumulator comes
                # from the LSB of the current data byte.
                if byte & 0x01:
                    newCRC |= 0x00800000
                # If the low bit of the current CRC accumulator was set
                # before the shift, then we need to XOR the accumulator
                # with the polynomial (center 16 bits of 0x00840800)
                if newCRC & 0x00000080:
                    newCRC ^= 0x00840800
                # Shift the data byte to put the next bit of the stream
                # into position 0.
                byte >>= 1
        # All the data has been done. Do 16 more bits of 0 data.
        for bit_count in range(16):
            # Shift the CRC accumulator
            newCRC >>= 1
            # If the low bit of the current CRC accumulator was set
            # before the shift we need to XOR the accumulator with
            # 0x00840800.
            if newCRC & 0x00000080:
                newCRC ^= 0x00840800
        # Return the center 16 bits, making this CRC match the one’s
        # complement that is sent in the packet.
        return ((~newCRC)>>8) & 0xffff

    def _send_packet(command, data):
        """
        low-level packet sending.  
        Following the protocol requires waiting for ack packet between 
        sending each packet to the device.
        """


class CF635Screen(CFLCDScreen):
    u"""
    Crystal Fontz 635 display

    20x4 character display + cursor
    no foreground/background colors or settings supported

    see CGROM for list of close unicode matches to characters available
     * ① through ⑧ are programmable CGRAM (chars 0-7, repeated at 8-15)
     * double arrows (⇑⇓) appear as double arrowheads (chars 18, 19)
     * ⑴ resembles a bell
     * ⑵ resembles a filled-in "Y"
     * ⑶ is the letters "Pt" together
     * partial blocks (▇▆▄▃▁) are actually shorter versions of (▉▋▌▍▏)
       both groups are intended to draw horizontal bars with pixel
       precision, use ▇*[▆▄▃▁]? for a thin bar or ▉*[▋▌▍▏]? for a thick bar

    6 button input
    up, down, left, right, enter (check mark), exit (cross)
    """
    DISPLAY_SIZE = (20, 4)

    CGROM = utf8decode(
        "①②③④⑤⑥⑦⑧①②③④⑤⑥⑦⑧"
        "►◄⇑⇓«»↖↗↙↘▲▼↲^ˇ█"
        " !\"#¤%&'()*+,-./"  
        "0123456789:;<=>?"
        "¡ABCDEFGHIJKLMNO"
        "PQRSTUVWXYZÄÖÑÜ§"
        "¿abcdefghijklmno"
        "pqrstuvwxyzäöñüà"
        "⁰¹²³⁴⁵⁶⁷⁸⁹½¼±≥≤μ"
        "♪♫⑴♥♦⑵⌜⌟“”()αɛδ∞"
        "@£$¥èéùìòÇᴾØøʳÅå"
        "⌂¢ΦτλΩπΨΣθΞ♈ÆæßÉ"
        "ΓΛΠϒ_ÈÊêçğŞşİι~◊"
        "▇▆▄▃▁ƒ▉▋▌▍▏⑶◽▪↑→"
        "↓←ÁÍÓÚÝáíóúýÔôŮů"
        "ČĔŘŠŽčĕřšž[\]{|}")

    cursor_style = CFLCDScreen.CURSOR_UNDERSCORE

    def __init__(self, device_path, baud=115200, repeat_delay=0.5, 
            repeat_next=0.125, 
            key_map=['up', 'down', 'left', 'right', 'enter', 'esc']):
        """
        device_path -- eg. '/dev/ttyUSB0'
        baud -- baud rate
        repeat_delay -- seconds to wait before starting to repeat keys
        repeat_next -- time between each repeated key
        key_map -- the keys to send for this device's buttons
        """
        super(CF635Screen, self).__init__(device_path, baud)

        self.repeat_delay = repeat_delay
        self.repeat_next = repeat_next
        self.key_map = key_map


    def get_input_descriptors(self):
        """
        return the fd from our serial device so we get called
        on input and responses
        """
        return [self._device.fd]

    def get_input_nonblocking(self):
        """
        Return a (next_input_timeout, keys_pressed, raw_keycodes)
        tuple.

        The protocol for our device requires waiting for acks between
        each command, so this method responds to those as well as key
        press and release events.

        Key repeat events are simulated here as the device doesn't send
        any for us.

        raw_keycodes are the bytes of messages we received, which might
        not seem to have any correspondence to keys_pressed.
        """


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
# Urwid web site: https://urwid.org/


"""Display modules for character LCD panels, including the Crystalfontz CF635."""

from __future__ import annotations

import abc
import time
import typing

from .common import BaseScreen

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Collection, Iterable, Sequence
    from typing import Literal, SupportsIndex

    from urwid import Canvas, EventLoop

# Bytes read from the serial device at once; the port is non-blocking, so a read returns what is waiting.
_READ_SIZE: typing.Final = 4096


class LCDScreen(BaseScreen, abc.ABC):
    """Base class for LCD-based screens."""

    DISPLAY_SIZE: tuple[int, int]

    def set_terminal_properties(
        self,
        colors: Literal[1, 16, 88, 256, 16777216] | None = None,
        bright_is_bold: bool | None = None,
        has_underline: bool | None = None,
    ) -> None:
        """Set terminal attributes. A no-op here; an LCD screen has no colors, bold, or underline to configure."""

    def set_input_timeouts(self, *args: typing.Any) -> None:
        """Set the maximum time in seconds to wait for input characters. A no-op here."""

    def reset_default_terminal_palette(self, *args: typing.Any) -> None:
        """Reset the terminal's default palette. A no-op here; an LCD screen has no palette to reset."""

    def get_cols_rows(self) -> tuple[int, int]:
        """Return the size of the LCD display as ``(cols, rows)``."""
        return self.DISPLAY_SIZE


class CFLCDScreen(LCDScreen, abc.ABC):
    """Common methods for Crystal Fonts LCD displays."""

    KEYS: typing.ClassVar[list[str | None]] = [
        None,  # no key with code 0
        "up_press",
        "down_press",
        "left_press",
        "right_press",
        "enter_press",
        "exit_press",
        "up_release",
        "down_release",
        "left_release",
        "right_release",
        "enter_release",
        "exit_release",
        "ul_press",
        "ur_press",
        "ll_press",
        "lr_press",
        "ul_release",
        "ur_release",
        "ll_release",
        "lr_release",
    ]
    CMD_PING = 0
    CMD_VERSION = 1
    CMD_CLEAR = 6
    CMD_CGRAM = 9
    CMD_CURSOR_POSITION = 11  # data = [col, row]
    CMD_CURSOR_STYLE = 12  # data = [style (0-4)]
    CMD_LCD_CONTRAST = 13  # data = [contrast (0-255)]
    CMD_BACKLIGHT = 14  # data = [power (0-100)]
    CMD_LCD_DATA = 31  # data = [col, row] + text
    CMD_GPO = 34  # data = [pin(0-12), value(0-100)]

    # sent from device
    CMD_KEY_ACTIVITY = 0x80
    CMD_ACK = 0x40  # in high two bits ie. & 0xc0

    CURSOR_NONE = 0
    CURSOR_BLINKING_BLOCK = 1
    CURSOR_UNDERSCORE = 2
    CURSOR_BLINKING_BLOCK_UNDERSCORE = 3
    CURSOR_INVERTING_BLINKING_BLOCK = 4

    MAX_PACKET_DATA_LENGTH = 22

    colors = 1
    has_underline = False

    def __init__(self, device_path: str, baud: int) -> None:
        """Open the serial connection.

        :param device_path: serial device to talk to, e.g. :file:`/dev/ttyUSB0`
        :param baud: baud rate
        """
        super().__init__()
        self.device_path = device_path
        from serial import Serial

        self._device = Serial(device_path, baud, timeout=0)
        self._unprocessed = bytearray()

    @classmethod
    def get_crc(cls, buf: Iterable[int]) -> bytes:
        """Return the 16-bit CRC of *buf*, as the two bytes sent in a packet's checksum field."""
        # This seed makes the output of this shift-based algorithm match
        # the table-based algorithm. The center 16 bits of the 32-bit
        # "newCRC" are used for the CRC. The MSB of the lower byte is used
        # to see what bit was shifted out of the center 16 bit CRC
        # accumulator ("carry flag analog");
        new_crc = 0x00F32100
        for byte in buf:
            # Push this byte's bits through a software
            # implementation of a hardware shift & xor.
            for bit_count in range(8):
                # Shift the CRC accumulator
                new_crc >>= 1
                # The new MSB of the CRC accumulator comes
                # from the LSB of the current data byte.
                if byte & (0x01 << bit_count):
                    new_crc |= 0x00800000
                # If the low bit of the current CRC accumulator was set
                # before the shift, then we need to XOR the accumulator
                # with the polynomial (center 16 bits of 0x00840800)
                if new_crc & 0x00000080:
                    new_crc ^= 0x00840800
        # All the data has been done. Do 16 more bits of 0 data.
        for _bit_count in range(16):
            # Shift the CRC accumulator
            new_crc >>= 1
            # If the low bit of the current CRC accumulator was set
            # before the shift we need to XOR the accumulator with
            # 0x00840800.
            if new_crc & 0x00000080:
                new_crc ^= 0x00840800
        # Return the center 16 bits, making this CRC match the one's
        # complement that is sent in the packet.
        return (((~new_crc) >> 8) & 0xFFFF).to_bytes(2, "little")

    def _send_packet(self, command: int, data: Collection[SupportsIndex]) -> None:
        """Send a low-level packet.

        Following the protocol requires waiting for ack packet between
        sending each packet to the device.
        """
        buf = bytearray([command, len(data)])
        buf.extend(data)
        buf.extend(self.get_crc(buf))
        self._device.write(buf)

    def _read_packet(self) -> tuple[int, bytearray] | None:
        """Read a low-level packet.

        This method stores data read and tries to resync when bad data
        is received.

        :returns: ``(command/report code, data)`` or ``None``.
        """
        # pull in any new data available
        self._unprocessed += self._device.read(_READ_SIZE)
        while True:
            try:
                command, data, unprocessed = self._parse_data(self._unprocessed)
                self._unprocessed = unprocessed
            except self.MoreDataRequired:
                return None
            except self.InvalidPacket:
                # throw out a byte and try to parse again
                self._unprocessed = self._unprocessed[1:]
            else:
                return command, data

    class InvalidPacket(Exception):
        """Raised when a packet is longer than the protocol allows, or its CRC does not match."""

    class MoreDataRequired(Exception):
        """Raised when the buffered data does not yet hold a complete packet."""

    @classmethod
    def _parse_data(cls, data: bytearray) -> tuple[int, bytearray, bytearray]:
        """Try to read a packet from the start of *data*.

        :returns: ``(command/report code, packet_data, remaining_data)``.
        :raises MoreDataRequired: *data* does not yet hold a complete packet.
        :raises InvalidPacket: the packet is longer than the protocol allows, or its CRC does not match.
        """
        if len(data) < 2:
            raise cls.MoreDataRequired

        command: int = data[0]
        packet_len: int = data[1]

        if packet_len > cls.MAX_PACKET_DATA_LENGTH:
            raise cls.InvalidPacket("length value too large")

        if len(data) < packet_len + 4:
            raise cls.MoreDataRequired

        data_end = 2 + packet_len
        if (crc := cls.get_crc(data[:data_end])) != (packet_crc := data[data_end : data_end + 2]):
            raise cls.InvalidPacket(f"CRC doesn't match ({crc=}, {packet_crc=})")

        return command, data[2:data_end], data[data_end + 2 :]


class KeyRepeatSimulator:
    """Provide simulated repeat key events when given press and release events.

    If two or more keys are pressed, disable repeating until all
    keys are released.
    """

    def __init__(self, repeat_delay: float, repeat_next: float) -> None:
        """Set up the repeat timing.

        :param repeat_delay: seconds to wait before starting to repeat keys
        :param repeat_next: time between each repeated key
        """
        self.repeat_delay = repeat_delay
        self.repeat_next = repeat_next
        self.pressed: dict[str, float] = {}
        self.multiple_pressed = False

    def press(self, key: str) -> None:
        """Record that *key* was pressed, disabling repeat if another key is already held down."""
        if self.pressed:
            self.multiple_pressed = True
        self.pressed[key] = time.time()

    def release(self, key: str) -> None:
        """Record that *key* was released, re-enabling repeat once no key is held down."""
        if key not in self.pressed:
            return  # ignore extra release events
        del self.pressed[key]
        if not self.pressed:
            self.multiple_pressed = False

    def next_event(self) -> tuple[float, str] | None:
        """Return ``(remaining, key)``, or ``None`` if no events are pending.

        *remaining* is the number of seconds (float) until the key repeat event should be sent.
        """
        if len(self.pressed) != 1 or self.multiple_pressed:
            return None
        for key, val in self.pressed.items():
            return max(0.0, val + self.repeat_delay - time.time()), key
        return None

    def sent_event(self) -> None:
        """Call this method when a key repeat event was sent.

        The timer will be reset for the next event.
        """
        if len(self.pressed) != 1:
            return  # ignore event that shouldn't have been sent
        for key in self.pressed:
            self.pressed[key] = time.time() - self.repeat_delay + self.repeat_next
            return


class CF635Screen(CFLCDScreen):
    """
    Crystal Fontz 635 display.

    20x4 character display + cursor
    no foreground/background colors or settings supported

    see CGROM for a list of close Unicode matches to characters available

    6 button input
    up, down, left, right, enter (check mark), exit (cross)
    """

    DISPLAY_SIZE = (20, 4)

    # ① through ⑧ are programmable CGRAM (chars 0-7, repeated at 8-15)
    # double arrows (⇑⇓) appear as double arrowheads (chars 18, 19)
    # ⑴ resembles a bell
    # ⑵ resembles a filled-in "Y"
    # ⑶ is the letters "Pt" together
    # partial blocks (▇▆▄▃▁) are actually shorter versions of (▉▋▌▍▏)
    #   both groups are intended to draw horizontal bars with pixel
    #   precision, use ▇*[▆▄▃▁]? for a thin bar or ▉*[▋▌▍▏]? for a thick bar
    CGROM = (
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
        r"ČĔŘŠŽčĕřšž[\]{|}"
    )

    cursor_style = CFLCDScreen.CURSOR_INVERTING_BLINKING_BLOCK

    #: Seconds to wait for a command's ACK before sending the command again.
    ACK_TIMEOUT: float = 0.25
    #: How many times a command is sent again before it is dropped.
    ACK_RESENDS: int = 3
    # Commands a later draw_screen() sends again once the screen buffer is cleared.
    _DRAW_COMMANDS: typing.Final = frozenset(
        {CFLCDScreen.CMD_LCD_DATA, CFLCDScreen.CMD_CURSOR_POSITION, CFLCDScreen.CMD_CURSOR_STYLE},
    )

    def __init__(
        self,
        device_path: str,
        baud: int = 115200,
        repeat_delay: float = 0.5,
        repeat_next: float = 0.125,
        key_map: Iterable[str] = ("up", "down", "left", "right", "enter", "esc"),
    ) -> None:
        """Open the serial connection and set up key repeat handling.

        :param device_path: serial device to talk to, e.g. :file:`/dev/ttyUSB0`
        :param baud: baud rate
        :param repeat_delay: seconds to wait before starting to repeat keys
        :param repeat_next: time between each repeated key
        :param key_map: the keys to send for this device's buttons
        """
        super().__init__(device_path, baud)

        self.repeat_delay = repeat_delay
        self.repeat_next = repeat_next
        self.key_repeat = KeyRepeatSimulator(repeat_delay, repeat_next)
        self.key_map = tuple(key_map)

        self._last_command: int | None = None
        self._last_data = bytearray()  # the data of the command awaiting its ACK, sent again when it is late
        self._resends = 0  # how often that command was sent again
        # A command answered while copies of it may still be answered: the device answers in order,
        # so that many further answers with this code belong to those copies and are ignored.
        self._stray_code: int | None = None
        self._strays = 0
        self._took_stray = False  # an answer was ignored as a stray while the current command waited
        self._answering = True  # False from a dropped command until the device answers again
        self._refused: set[int] = set()  # codes of the commands the device refused, each logged once
        self._command_queue: list[tuple[int, bytearray]] = []
        self._screen_buf: list[list[bytes]] = []
        self._previous_canvas: Canvas | None = None
        self._update_cursor = False
        # set while hooked into an event loop: the loop, the watch of the serial device,
        # the alarm of the next key repeat, and the alarm, set for each command sent,
        # that sends the command awaiting its ACK again
        self._event_loop: EventLoop | None = None
        self._watch_handle: typing.Any = None
        self._repeat_alarm: typing.Any = None
        self._ack_alarm: typing.Any = None

    def hook_event_loop(
        self,
        event_loop: EventLoop,
        callback: Callable[[list[str], list[int]], typing.Any],
    ) -> None:
        """Watch the serial device on *event_loop* and pass what :meth:`get_input_nonblocking` returns to *callback*.

        The device's answers, an ACK or an error response, are answered with the next queued command as they arrive,
        and a held key is repeated from an alarm, since the device sends no repeats.
        A command whose ACK does not arrive within :attr:`ACK_TIMEOUT` seconds is sent again,
        up to :attr:`ACK_RESENDS` times, and then dropped, so the queue never stops.

        Logged:

        - a warning when the device stops answering, and an info message when it answers again;
        - an error the first time the device refuses a command with a given code.
        """

        def read_device() -> None:
            if self._repeat_alarm is not None:
                event_loop.remove_alarm(self._repeat_alarm)
                self._repeat_alarm = None
            timeout, keys, raw = self.get_input_nonblocking()
            if timeout is not None:
                self._repeat_alarm = event_loop.alarm(timeout, read_device)
            callback(keys, raw)

        self._remove_ack_alarm()  # left by an earlier hook that was not undone
        self._event_loop = event_loop
        self._watch_handle = event_loop.watch_file(self._device.fileno(), read_device)
        if self._last_command is not None:  # sent before the hook, with nothing timing its ACK
            self._set_ack_alarm()

    def unhook_event_loop(self, event_loop: EventLoop) -> None:
        """Remove the watch and the alarms that :meth:`hook_event_loop` and the commands sent since added."""
        self._remove_ack_alarm()
        self._event_loop = None
        if self._repeat_alarm is not None:
            event_loop.remove_alarm(self._repeat_alarm)
            self._repeat_alarm = None
        if self._watch_handle is not None:
            event_loop.remove_watch_file(self._watch_handle)
            self._watch_handle = None

    def get_input_descriptors(self) -> list[int]:
        """Return the descriptor of the serial device."""
        return [self._device.fileno()]

    def get_input_nonblocking(self) -> tuple[float | None, list[str], list[int]]:
        """Return a ``(next_input_timeout, keys_pressed, raw_keycodes)`` tuple.

        The protocol for our device requires waiting for acks between
        each command, so this method responds to those as well as key
        press and release events.

        Key repeat events are simulated here as the device doesn't send
        any for us.

        raw_keycodes are the bytes of messages we received, which might
        not seem to have any correspondence to keys_pressed.
        """
        data_input: list[str] = []
        raw_data_input: list[int] = []
        timeout = None

        packet = self._read_packet()
        while packet:
            command, data = packet

            if command == self.CMD_KEY_ACTIVITY and data:
                d0 = data[0]
                if 1 <= d0 <= 12:
                    release = d0 > 6
                    keycode = d0 - (release * 6) - 1
                    key = self.key_map[keycode]
                    if release:
                        self.key_repeat.release(key)
                    else:
                        data_input.append(key)
                        self.key_repeat.press(key)
                    raw_data_input.append(d0)

            elif command & 0x40:  # an ACK (0x40 | code) or an error response (0xC0 | code)
                code = command & 0x3F
                if code == self._stray_code and self._strays:
                    self._strays -= 1  # the answer to a copy of a command already answered
                    self._took_stray = True
                elif code == self._last_command:
                    if not self._answering:
                        self.logger.info("The LCD answers again")
                        self._answering = True
                    if command & 0x80 and code not in self._refused:
                        # Sending it again cannot help; logged once per code, so repeated refusals do not flood the log.
                        self.logger.error(f"The LCD refused command {code}; later refusals of it are not logged")
                        self._refused.add(code)
                    self._finish_command(self._resends)

            packet = self._read_packet()

        if next_repeat := self.key_repeat.next_event():
            timeout, key = next_repeat
            if not timeout:
                data_input.append(key)
                self.key_repeat.sent_event()
                timeout = self.key_repeat.repeat_next  # the key is still held: the next repeat is due then

        return timeout, data_input, raw_data_input

    def _finish_command(self, unanswered: int) -> None:
        """Send the next command, ignoring *unanswered* later answers to copies of the one sent last."""
        self._stray_code = self._last_command
        self._strays = unanswered
        self._send_next_command()

    def _clear_screen_buf(self) -> None:
        """Make the next :meth:`draw_screen` send every row and the cursor again."""
        self._screen_buf = []
        self._previous_canvas = None

    def _send_next_command(self) -> None:
        """Send out the next command in the queue."""
        self._remove_ack_alarm()
        if not self._command_queue:
            self._last_command = None
            return
        self._last_command, self._last_data = self._command_queue.pop(0)  # record command for ACK
        self._resends = 0
        self._took_stray = False
        self._send_packet(self._last_command, self._last_data)
        self._set_ack_alarm()

    def _set_ack_alarm(self) -> None:
        """Time the ACK of the command just sent, when an event loop is hooked."""
        if self._event_loop is not None:
            self._ack_alarm = self._event_loop.alarm(self.ACK_TIMEOUT, self._ack_timed_out)

    def _remove_ack_alarm(self) -> None:
        """Stop timing the ACK of the command sent last."""
        if self._ack_alarm is not None:
            typing.cast("EventLoop", self._event_loop).remove_alarm(self._ack_alarm)
            self._ack_alarm = None

    def _ack_timed_out(self) -> None:
        """Send the command awaiting its ACK again, or drop it once it was sent again :attr:`ACK_RESENDS` times.

        Nothing arrived in order for :attr:`ACK_TIMEOUT` seconds,
        so answers to copies of earlier commands count as lost.
        The outcomes, the first that applies:

        - An answer was ignored as such a stray while this command waited, so it was most likely its own.
          The command counts as answered, and the next :meth:`draw_screen` sends everything again in case it was not.
        - The command was sent again fewer than :attr:`ACK_RESENDS` times: it is sent again.
        - Otherwise it is dropped, with the queued draw commands, which the next :meth:`draw_screen` sends again.

        :raises RuntimeError: no command awaits an ACK, which every path that ends one prevents by removing this alarm.
        """
        self._ack_alarm = None
        if (command := self._last_command) is None:
            msg = "an ACK alarm fired with no command awaiting its ACK"
            raise RuntimeError(msg)
        self._strays = 0
        if self._took_stray:
            self._clear_screen_buf()
            self._finish_command(0)
            return
        if self._resends < self.ACK_RESENDS:
            self._resends += 1
            self._send_packet(command, self._last_data)
            self._set_ack_alarm()
            return
        if self._answering:
            self.logger.warning("The LCD does not answer: commands are dropped until it does")
            self._answering = False
        self.logger.debug(f"Dropped LCD command {command}")
        self._clear_screen_buf()
        self._command_queue = [entry for entry in self._command_queue if entry[0] not in self._DRAW_COMMANDS]
        self._finish_command(0)

    def queue_command(self, command: int, data: bytearray) -> None:
        """Queue *command* with *data* for sending, sending it immediately if no command is awaiting an ACK."""
        self._command_queue.append((command, data))
        # not waiting? send away!
        if self._last_command is None:
            self._send_next_command()

    def draw_screen(self, size: tuple[int, int], canvas: Canvas) -> None:
        """
        Send *canvas* to the display.

        :raises ValueError: *size* is not the fixed size of this display.
        """
        if size != self.DISPLAY_SIZE:
            raise ValueError(size)

        osb: list[list[bytes]]
        if self._screen_buf:
            osb = self._screen_buf
        else:
            osb = []
        sb: list[list[bytes]] = []

        for y, row in enumerate(canvas.content()):
            text: list[bytes] = [run for _a, _cs, run in row]

            if not osb or osb[y] != text:
                data = bytearray([0, y])
                for elem in text:
                    data.extend(elem)
                self.queue_command(self.CMD_LCD_DATA, data)
            sb.append(text)

        if (
            self._previous_canvas
            and self._previous_canvas.cursor == canvas.cursor
            and (not self._update_cursor or not canvas.cursor)
        ):
            pass
        elif canvas.cursor is None:
            self.queue_command(self.CMD_CURSOR_STYLE, bytearray([self.CURSOR_NONE]))
        else:
            x, y = canvas.cursor
            self.queue_command(self.CMD_CURSOR_POSITION, bytearray([x, y]))
            self.queue_command(self.CMD_CURSOR_STYLE, bytearray([self.cursor_style]))

        self._update_cursor = False
        self._screen_buf = sb
        self._previous_canvas = canvas

    def program_cgram(self, index: int, data: Sequence[int]) -> None:
        """
        Program character data.

        Characters available as chr(0) through chr(7), and repeated as chr(8) through chr(15).

        :param index: 0 to 7 index of character to program

        :param data: list of 8, 6-bit integer values top to bottom with MSB on the left side of the character.
        :raises ValueError: *index* is outside 0-7, or *data* is not 8 rows.
        """
        if not 0 <= index <= 7:
            raise ValueError(index)
        if len(data) != 8:
            raise ValueError(data)
        self.queue_command(self.CMD_CGRAM, bytearray([index]) + bytearray(data))

    def set_cursor_style(self, style: Literal[1, 2, 3, 4]) -> None:
        """Set the cursor style.

        :param style: CURSOR_BLINKING_BLOCK, CURSOR_UNDERSCORE, CURSOR_BLINKING_BLOCK_UNDERSCORE or
            CURSOR_INVERTING_BLINKING_BLOCK
        :raises ValueError: *style* is not one of the four cursor styles.
        """
        if not 1 <= style <= 4:
            raise ValueError(style)
        self.cursor_style = style
        self._update_cursor = True

    def set_backlight(self, value: int) -> None:
        """
        Set backlight brightness.

        :param value: 0 to 100
        :raises ValueError: *value* is outside 0-100.
        """
        if not 0 <= value <= 100:
            raise ValueError(value)
        self.queue_command(self.CMD_BACKLIGHT, bytearray([value]))

    def set_lcd_contrast(self, value: int) -> None:
        """Set the LCD contrast.

        :param value: 0 to 255
        :raises ValueError: *value* is outside 0-255.
        """
        if not 0 <= value <= 255:
            raise ValueError(value)
        self.queue_command(self.CMD_LCD_CONTRAST, bytearray([value]))

    def set_led_pin(self, led: Literal[0, 1, 2, 3], rg: Literal[0, 1], value: int) -> None:
        """Set an LED pin's brightness.

        :param led: 0 to 3
        :param rg: 0 for red, 1 for green
        :param value: 0 to 100
        :raises ValueError: *led* is outside 0-3, *rg* is not ``0`` or ``1``, or *value* is outside 0-100.
        """
        if not 0 <= led <= 3:
            raise ValueError(led)
        if rg not in {0, 1}:
            raise ValueError(rg)
        if not 0 <= value <= 100:
            raise ValueError(value)
        self.queue_command(self.CMD_GPO, bytearray([12 - 2 * led - rg, value]))

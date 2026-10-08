from __future__ import annotations

import unittest
from unittest import mock

from urwid.display import lcd

try:
    import serial
except ImportError:
    serial = None


@unittest.skipIf(serial is None, "pyserial is only installed with the serial extra")
class CF635ScreenTest(unittest.TestCase):
    def test_input_descriptor_is_the_open_port_fileno(self) -> None:
        """Watch the descriptor the open serial port reports through fileno()."""
        with mock.patch.object(serial, "Serial") as serial_cls:
            serial_cls.return_value.fileno.return_value = 7
            screen = lcd.CF635Screen("/dev/ttyUSB0")

        self.assertEqual([7], screen.get_input_descriptors())

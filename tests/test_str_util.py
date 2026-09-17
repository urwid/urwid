from __future__ import annotations

import unittest

from urwid.display.escape import str_util


class DecodeOneTest(unittest.TestCase):
    def gwt(self, ch, exp_ord, exp_pos):
        ch = ch.encode("iso8859-1")
        o, pos = str_util.decode_one(ch, 0)
        assert o == exp_ord, f" got:{o!r} expected:{exp_ord!r}"
        assert pos == exp_pos, f" got:{pos!r} expected:{exp_pos!r}"

    def test1byte(self):
        self.gwt("ab", ord("a"), 1)
        self.gwt("\xc0a", ord("?"), 1)  # error

    def test2byte(self):
        self.gwt("\xc2", ord("?"), 1)  # error
        self.gwt("\xc0\x80", ord("?"), 1)  # error
        self.gwt("\xc2\x80", 0x80, 2)
        self.gwt("\xdf\xbf", 0x7FF, 2)

    def test3byte(self):
        self.gwt("\xe0", ord("?"), 1)  # error
        self.gwt("\xe0\xa0", ord("?"), 1)  # error
        self.gwt("\xe0\x90\x80", ord("?"), 1)  # error
        self.gwt("\xe0\xa0\x80", 0x800, 3)
        self.gwt("\xef\xbf\xbf", 0xFFFF, 3)

    def test4byte(self):
        self.gwt("\xf0", ord("?"), 1)  # error
        self.gwt("\xf0\x90", ord("?"), 1)  # error
        self.gwt("\xf0\x90\x80", ord("?"), 1)  # error
        self.gwt("\xf0\x80\x80\x80", ord("?"), 1)  # error
        self.gwt("\xf0\x90\x80\x80", 0x10000, 4)
        self.gwt("\xf3\xbf\xbf\xbf", 0xFFFFF, 4)

    def test_str_input(self):
        """decode_one's str branch treats each character as one raw byte value (via ord()), the
        same way gwt()'s bytes are built from a str via .encode("iso8859-1"); passing the str
        literal directly (instead of encoding it first) exercises that branch with the same
        byte-equivalent inputs used in test1byte..test4byte.
        """
        self.assertEqual((ord("a"), 1), str_util.decode_one("ab", 0))
        self.assertEqual((0x7FF, 2), str_util.decode_one("\xdf\xbf", 0))
        self.assertEqual((0x800, 3), str_util.decode_one("\xe0\xa0\x80", 0))
        self.assertEqual((0x10000, 4), str_util.decode_one("\xf0\x90\x80\x80", 0))

    def test_invalid_continuation_byte(self):
        """A malformed (non-0x80-0xBF) continuation byte is an error, distinct from a short
        sequence or an overlong encoding -- regression coverage for the lazily-read b2/b3/b4
        refactor, since each continuation check now lives in its own guarded block.
        """
        self.gwt("\xc2A", ord("?"), 1)  # 2-byte: bad b2
        self.gwt("\xe0\xa0A", ord("?"), 1)  # 3-byte: bad b3 (b2 valid)
        self.gwt("\xe0AA", ord("?"), 1)  # 3-byte: bad b2
        self.gwt("\xf0\x90\x80A", ord("?"), 1)  # 4-byte: bad b4 (b2, b3 valid)
        self.gwt("\xf0\x90AA", ord("?"), 1)  # 4-byte: bad b3
        self.gwt("\xf0AAA", ord("?"), 1)  # 4-byte: bad b2

    def test_invalid_leading_byte(self):
        """A leading byte matching none of the 1/2/3/4-byte patterns (e.g. a stray continuation
        byte, or 0xF8-0xFF) falls through to the final error case.
        """
        self.gwt("\xff\x80\x80\x80", ord("?"), 1)
        self.gwt("\xf8\x80\x80\x80", ord("?"), 1)

    def test_out_of_range_pos_raises_value_error(self):
        with self.assertRaises(ValueError):
            str_util.decode_one(b"ab", 5)
        with self.assertRaises(ValueError):
            str_util.decode_one("ab", 5)

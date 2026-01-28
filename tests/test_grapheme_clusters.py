from __future__ import annotations

import unittest

from urwid import str_util

# 🇨🇦 regional indicator Canada flag
FLAG_CA = "\U0001F1E8\U0001F1E6"
# 👨‍👩‍👧 family (man + ZWJ + woman + ZWJ + girl)
FAMILY = "\U0001F468\u200D\U0001F469\u200D\U0001F467"
# 👩🏻‍💻 woman technologist with light skin tone
TECHNOLOGIST = "\U0001F469\U0001F3FB\u200D\U0001F4BB"
# 👋🏻 waving hand with light skin tone
WAVE_SKIN = "\U0001F44B\U0001F3FB"
# café with combining acute accent on e
CAFE = "cafe\u0301"
# ❤️ red heart with VS16 (emoji presentation)
HEART_VS16 = "\u2764\ufe0f"
# ❤ red heart (text presentation)
HEART = "\u2764"
# 中文 Chinese characters
CJK = "\u4e2d\u6587"


class CalcWidthGraphemeTest(unittest.TestCase):
    def wtest(self, text, expected):
        result = str_util.calc_width(text, 0, len(text))
        assert result == expected, f"got:{result!r} expected:{expected!r}"

    def test_basic(self):
        self.wtest("hello", 5)
        self.wtest("", 0)
        self.wtest(CJK, 4)

    def test_flags(self):
        self.wtest(FLAG_CA, 2)
        self.wtest(FLAG_CA + FLAG_CA, 4)

    def test_zwj_sequences(self):
        self.wtest(FAMILY, 2)
        self.wtest(TECHNOLOGIST, 2)

    def test_skin_tones(self):
        self.wtest(WAVE_SKIN, 2)

    def test_combining(self):
        self.wtest(CAFE, 4)
        self.wtest("e\u0301", 1)

    def test_variation_selectors(self):
        self.wtest(HEART_VS16, 2)
        self.wtest(HEART, 1)


class CalcTextPosGraphemeTest(unittest.TestCase):
    def ptest(self, text, pref_col, expected_pos):
        pos, _ = str_util.calc_text_pos(text, 0, len(text), pref_col)
        assert pos == expected_pos, f"got:{pos!r} expected:{expected_pos!r}"

    def test_basic(self):
        self.ptest("hello", 3, 3)

    def test_flag_boundaries(self):
        text = f"A{FLAG_CA}B"
        self.ptest(text, 1, 1)
        self.ptest(text, 2, 1)
        self.ptest(text, 3, 3)

    def test_zwj_boundaries(self):
        text = f"A{FAMILY}B"
        self.ptest(text, 2, 1)
        self.ptest(text, 3, 6)


class MoveNextCharGraphemeTest(unittest.TestCase):
    def test_move_through_family_emoji(self):
        text = f"A{FAMILY}B"
        pos = str_util.move_next_char(text, 1, len(text))
        assert pos == 6

    def test_move_through_flag(self):
        text = f"A{FLAG_CA}B"
        pos = str_util.move_next_char(text, 1, len(text))
        assert pos == 3

    def test_move_through_combining(self):
        pos = str_util.move_next_char(CAFE, 3, len(CAFE))
        assert pos == 5

    def test_move_through_skin_tone(self):
        text = f"A{WAVE_SKIN}B"
        pos = str_util.move_next_char(text, 1, len(text))
        assert pos == 3

    def test_basic_ascii(self):
        pos = str_util.move_next_char("hello", 0, 5)
        assert pos == 1


class MovePrevCharGraphemeTest(unittest.TestCase):
    def test_move_back_through_family_emoji(self):
        text = f"A{FAMILY}B"
        pos = str_util.move_prev_char(text, 0, 6)
        assert pos == 1

    def test_move_back_through_flag(self):
        text = f"A{FLAG_CA}B"
        pos = str_util.move_prev_char(text, 0, 3)
        assert pos == 1

    def test_move_back_through_combining(self):
        pos = str_util.move_prev_char(CAFE, 0, 5)
        assert pos == 3

    def test_move_back_through_skin_tone(self):
        text = f"A{WAVE_SKIN}B"
        pos = str_util.move_prev_char(text, 0, 3)
        assert pos == 1

    def test_basic_ascii(self):
        pos = str_util.move_prev_char("hello", 0, 5)
        assert pos == 4


class IsWideCharGraphemeTest(unittest.TestCase):
    def test_family_emoji_is_wide(self):
        assert str_util.is_wide_char(FAMILY, 0)

    def test_flag_is_wide(self):
        assert str_util.is_wide_char(FLAG_CA, 0)

    def test_cjk_is_wide(self):
        assert str_util.is_wide_char(CJK, 0)

    def test_ascii_not_wide(self):
        assert not str_util.is_wide_char("hello", 0)

    def test_skin_tone_is_wide(self):
        assert str_util.is_wide_char(WAVE_SKIN, 0)


# UTF-8 bytes test constants
FLAG_CA_BYTES = FLAG_CA.encode("utf-8")  # 8 bytes
FAMILY_BYTES = FAMILY.encode("utf-8")  # 18 bytes


class Utf8BytesGraphemeTest(unittest.TestCase):
    """Tests for grapheme clustering with UTF-8 bytes."""

    def setUp(self):
        self._orig_encoding = str_util.get_byte_encoding()
        str_util.set_byte_encoding("utf8")

    def tearDown(self):
        str_util.set_byte_encoding(self._orig_encoding)

    def test_calc_width_flag_bytes(self):
        result = str_util.calc_width(FLAG_CA_BYTES, 0, len(FLAG_CA_BYTES))
        assert result == 2

    def test_calc_width_family_emoji_bytes(self):
        result = str_util.calc_width(FAMILY_BYTES, 0, len(FAMILY_BYTES))
        assert result == 2

    def test_move_next_through_family_emoji_bytes(self):
        # After 'A' (1 byte), should skip entire family emoji
        text = f"A{FAMILY}B".encode("utf-8")
        pos = str_util.move_next_char(text, 1, len(text))
        assert pos == 1 + len(FAMILY_BYTES)

    def test_move_next_through_flag_bytes(self):
        # After 'A' (1 byte), should skip entire flag
        text = f"A{FLAG_CA}B".encode("utf-8")
        pos = str_util.move_next_char(text, 1, len(text))
        assert pos == 1 + len(FLAG_CA_BYTES)

    def test_move_prev_through_family_emoji_bytes(self):
        # From position after family emoji, should go back to after 'A'
        text = f"A{FAMILY}B".encode("utf-8")
        end_pos = 1 + len(FAMILY_BYTES)
        pos = str_util.move_prev_char(text, 0, end_pos)
        assert pos == 1

    def test_move_prev_through_flag_bytes(self):
        # From position after flag, should go back to after 'A'
        text = f"A{FLAG_CA}B".encode("utf-8")
        end_pos = 1 + len(FLAG_CA_BYTES)
        pos = str_util.move_prev_char(text, 0, end_pos)
        assert pos == 1

    def test_is_wide_family_emoji_bytes(self):
        assert str_util.is_wide_char(FAMILY_BYTES, 0)

    def test_is_wide_flag_bytes(self):
        assert str_util.is_wide_char(FLAG_CA_BYTES, 0)

    def test_calc_text_pos_flag_boundaries_bytes(self):
        text = f"A{FLAG_CA}B".encode("utf-8")
        # Column 1 should be at position 1 (after 'A')
        pos, col = str_util.calc_text_pos(text, 0, len(text), 1)
        assert pos == 1
        assert col == 1
        # Column 2 should still be at position 1 (inside flag grapheme)
        pos, col = str_util.calc_text_pos(text, 0, len(text), 2)
        assert pos == 1
        assert col == 1
        # Column 3 should be at position after flag
        pos, col = str_util.calc_text_pos(text, 0, len(text), 3)
        assert pos == 1 + len(FLAG_CA_BYTES)
        assert col == 3

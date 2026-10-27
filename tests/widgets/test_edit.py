from __future__ import annotations

import sys
import typing
import unittest
from unittest import mock

import urwid
from urwid.command_map import Command
from urwid.util import set_temporary_encoding


class EditTest(unittest.TestCase):
    def test_selectable(self) -> None:
        self.assertTrue(urwid.Edit().selectable())

    def test_sizing(self) -> None:
        self.assertEqual(urwid.Edit().sizing(), frozenset([urwid.FLOW]))

    def test_get_text_masked(self) -> None:
        e = urwid.Edit("pw:", "secret", mask="*")
        self.assertEqual(e.get_text(), ("pw:******", []))

    def test_repr_masked_hides_text(self) -> None:
        """repr() of a masked Edit shows the mask, never the text."""
        e = urwid.Edit("pw: ", "hunter2", mask="*")
        self.assertEqual(repr(e), "<Edit selectable flow widget '*******' caption='pw: ' edit_pos=7 mask='*'>")

    def test_insert_text_result_error_masked_hides_text(self) -> None:
        """The ValueError raised for a masked Edit does not carry the text."""
        e = urwid.Edit("", "hunter2", mask="*")
        e._edit_text = b"hunter2"
        with self.assertRaises(ValueError) as ctx:
            e.insert_text_result("x")
        self.assertNotIn("hunter2", str(ctx.exception))

    def test_valid_char_rejects_control_characters(self) -> None:
        """Control characters, which render as '?' but count as zero columns, are refused."""
        e = urwid.Edit()
        for ch in ("\x00", "\x1b", "\x7f", "\x80", "\x9b", "\x9f"):
            with self.subTest(ch=ch):
                self.assertFalse(e.valid_char(ch))
                self.assertEqual(e.keypress((20,), ch), ch)
        self.assertEqual(e.edit_text, "")
        for ch in (" ", "a", "~", "\xa0", "\xe9", "\u044f"):
            with self.subTest(ch=ch):
                self.assertTrue(e.valid_char(ch))

    def test_valid_char_bytes(self) -> None:
        """A byte is refused only when it is a C0 control or DEL: 0x80-0xff are letters in KOI8-R."""
        e = urwid.Edit(b"", b"")
        with set_temporary_encoding("koi8-r"):
            for ch in (b"\x00", b"\x1f", b"\x7f"):
                with self.subTest(ch=ch):
                    self.assertFalse(e.valid_char(ch))
            for ch in (b" ", b"a", b"\x80", b"\x9f", b"\xbf", b"\xff"):
                with self.subTest(ch=ch):
                    self.assertTrue(e.valid_char(ch))

    def test_text_property(self) -> None:
        e = urwid.Edit("Y/n? ", "yes")
        self.assertEqual(e.text, "Y/n? yes")

    def test_attrib_property(self) -> None:
        e = urwid.Edit(("bold", "cap "), "text")
        self.assertEqual(e.attrib, [("bold", 4)])

    def test_set_align_mode(self) -> None:
        e = urwid.Edit()
        e.set_align_mode(urwid.RIGHT)
        self.assertEqual(e.align, urwid.RIGHT)

    def test_set_wrap_mode(self) -> None:
        e = urwid.Edit()
        e.set_wrap_mode(urwid.CLIP)
        self.assertEqual(e.wrap, urwid.CLIP)

    def test_set_layout(self) -> None:
        e = urwid.Edit("", "hello world", wrap="space")
        e.set_layout(urwid.CENTER, urwid.CLIP)
        self.assertEqual(e.align, urwid.CENTER)
        self.assertEqual(e.wrap, urwid.CLIP)

    def test_layout_property(self) -> None:
        e = urwid.Edit()
        self.assertIs(e.layout, e._w.layout)

    def test_set_caption(self) -> None:
        e = urwid.Edit("")
        e.set_caption("cap1")
        self.assertEqual(e.caption, "cap1")
        e.set_caption(("bold", "cap2"))
        self.assertEqual(e.caption, "cap2")
        self.assertEqual(e.attrib, [("bold", 4)])

    def test_normalize_to_caption_bytes_caption(self) -> None:
        e = urwid.Edit(b"cap: ", b"")
        e.insert_text("hi")
        self.assertEqual(e.edit_text, b"hi")

    def test_normalize_to_caption_str_caption(self) -> None:
        e = urwid.Edit("cap: ", "")
        e.insert_text(b"hi")
        self.assertEqual(e.edit_text, "hi")

    def test_get_pref_col_cached(self) -> None:
        size = (10,)
        e = urwid.Edit("", "word")
        e.keypress(size, "left")
        self.assertEqual(e.get_pref_col(size), 3)
        # Same maxcol as last time: hits the cached pref_col_maxcol branch.
        self.assertEqual(e.get_pref_col(size), 3)

    def test_insert_text_result_with_highlight(self) -> None:
        e = urwid.Edit("", "hello world")
        e.highlight = (0, 5)
        result_text, result_pos = e.insert_text_result("HI")
        self.assertEqual(result_text, "HI world")
        self.assertEqual(result_pos, 2)

    def test_insert_text_result_raises_value_error(self) -> None:
        e = urwid.Edit("", "hi")
        # Force a type mismatch between edit_text and the inserted text so the
        # concatenation in insert_text_result() raises, which is re-raised as ValueError.
        e._edit_text = b"hi"
        with self.assertRaises(ValueError):
            e.insert_text_result("x")

    def test_keypress_encodes_str_key_for_bytes_caption(self) -> None:
        e = urwid.Edit(b"cap: ", b"")
        e.keypress((20,), "x")
        self.assertEqual(e.edit_text, b"x")

    def test_keypress_left(self) -> None:
        e = urwid.Edit("", "word")
        e.keypress((20,), "left")
        self.assertEqual(e.edit_pos, 3)

    def test_keypress_left_at_start(self) -> None:
        e = urwid.Edit("", "word", edit_pos=0)
        self.assertEqual(e.keypress((20,), "left"), "left")

    def test_keypress_right(self) -> None:
        e = urwid.Edit("", "word", edit_pos=0)
        e.keypress((20,), "right")
        self.assertEqual(e.edit_pos, 1)

    def test_keypress_right_at_end(self) -> None:
        e = urwid.Edit("", "word")
        self.assertEqual(e.keypress((20,), "right"), "right")

    def test_keypress_down(self) -> None:
        e = urwid.Edit("", "one\ntwo", multiline=True, edit_pos=1)
        e.keypress((20,), "down")
        self.assertEqual(e.edit_pos, 5)

    def test_keypress_up(self) -> None:
        e = urwid.Edit("", "one\ntwo", multiline=True, edit_pos=5)
        e.keypress((20,), "up")
        self.assertEqual(e.edit_pos, 1)

    def test_keypress_up_out_of_bounds_returns_key(self) -> None:
        e = urwid.Edit("", "word")
        self.assertEqual(e.keypress((20,), "up"), "up")

    def test_keypress_tab_allowed(self) -> None:
        e = urwid.Edit("", "", allow_tab=True)
        e.keypress((20,), "tab")
        self.assertEqual(e.edit_text, " " * 8)

    def test_keypress_tab_expanded_to_next_stop(self) -> None:
        e = urwid.Edit("", "abc", allow_tab=True)
        e.keypress((20,), "tab")
        self.assertEqual(e.edit_text, "abc     ")

    def test_keypress_tab_expanded_by_rendered_width(self) -> None:
        # "中文" is 2 characters, but 4 screen columns
        e = urwid.Edit("", "中文", allow_tab=True)
        e.keypress((20,), "tab")
        self.assertEqual(e.edit_text, "中文    ")

    def test_keypress_tab_expanded_after_zwj_sequence(self) -> None:
        # 3 code points joined by ZWJ, 2 screen columns
        e = urwid.Edit("", "👩‍💻", allow_tab=True)
        e.keypress((20,), "tab")
        self.assertEqual(e.edit_text, "👩‍💻      ")

    def test_keypress_tab_expanded_from_line_start(self) -> None:
        e = urwid.Edit("", "abc\nd", multiline=True, allow_tab=True)
        e.keypress((20,), "tab")
        self.assertEqual(e.edit_text, "abc\nd       ")

    def test_keypress_tab_expanded_after_tab_character(self) -> None:
        e = urwid.Edit("", "a\tbc", allow_tab=True)
        e.keypress((20,), "tab")
        self.assertEqual(e.edit_text, "a\tbc      ")

    def test_keypress_tab_expanded_with_layout_tab_stops(self) -> None:
        e = urwid.Edit("", "a", allow_tab=True, layout=urwid.StandardTextLayout(tab_stops=(3,)))
        e.keypress((20,), "tab")
        self.assertEqual(e.edit_text, "a  ")

    def test_keypress_tab_expanded_with_custom_layout(self) -> None:
        class CustomLayout(urwid.TextLayout):
            def layout(self, text: str, width: int, align: str, wrap: str) -> list[list[tuple[int, int, int]]]:
                return [[(len(text), 0, len(text))]] if text else [[]]

        e = urwid.Edit("", "ab", allow_tab=True, layout=CustomLayout())
        e.keypress((20,), "tab")
        self.assertEqual(e.edit_text, "ab      ")

    def test_keypress_tab_expanded_to_zero_width(self) -> None:
        e = urwid.Edit("", "ab", allow_tab=True, layout=urwid.StandardTextLayout(tab_stop_every=0))
        e.keypress((20,), "tab")
        self.assertEqual(e.edit_text, "ab")

    def test_keypress_tab_expanded_bytes(self) -> None:
        e = urwid.Edit(b"", b"ab", allow_tab=True)
        e.keypress((20,), "tab")
        self.assertEqual(e.edit_text, b"ab      ")

    def test_keypress_tab_character(self) -> None:
        e = urwid.Edit("", "ab", allow_tab=True, edit_pos=1, expand_tabs=False)
        e.keypress((20,), "tab")
        self.assertEqual(e.edit_text, "a\tb")
        self.assertEqual(e.edit_pos, 2)
        self.assertEqual(e.get_cursor_coords((20,)), (8, 0))

    def test_keypress_tab_character_bytes(self) -> None:
        e = urwid.Edit(b"", b"", allow_tab=True, expand_tabs=False)
        e.keypress((20,), "tab")
        self.assertEqual(e.edit_text, b"\t")

    def test_keypress_tab_not_allowed(self) -> None:
        e = urwid.Edit("", "")
        self.assertEqual(e.keypress((20,), "tab"), "tab")

    def test_keypress_max_length(self) -> None:
        """A key that would make the text longer than max_length inserts nothing and is returned."""
        tab = {"allow_tab": True}
        cases: tuple[
            tuple[str, str | bytes, str, dict[str, typing.Any], tuple[str, ...], tuple[str | None, ...], str | bytes],
            ...,
        ] = (
            ("typed past the limit", "", "", {"max_length": 3}, ("a", "b", "c", "d"), (None, None, None, "d"), "abc"),
            ("code points", "", "", {"max_length": 3}, ("A", "界", "🙂", "x"), (None, None, None, "x"), "A界🙂"),
            ("bytes caption", b"", "", {"max_length": 3}, ("a", "b", "é", "c"), (None, None, "é", None), b"abc"),
            ("expanded tab", "", "ab", {"max_length": 3, **tab}, ("tab",), ("tab",), "ab"),
            (
                "tab character",
                "",
                "a",
                {"max_length": 2, **tab, "expand_tabs": False},
                ("tab", "tab"),
                (None, "tab"),
                "a\t",
            ),
            ("multiline enter", "", "ab", {"max_length": 2, "multiline": True}, ("enter",), ("enter",), "ab"),
            (
                "bytes enter",
                b"",
                "",
                {"max_length": 2, "multiline": True},
                ("a", "enter", "enter"),
                (None, None, "enter"),
                b"a\n",
            ),
            ("full, then shortened", "", "ab", {"max_length": 2}, ("x", "backspace", "x"), ("x", None, None), "ax"),
            ("zero", "", "", {"max_length": 0}, ("a",), ("a",), ""),
            ("no limit", "", "", {"max_length": None}, ("a", "b"), (None, None), "ab"),
        )
        for label, caption, text, kwargs, keys, returned, expected in cases:
            with self.subTest(case=label):
                e = urwid.Edit(caption, text, **kwargs)
                self.assertEqual(tuple(e.keypress((20,), key) for key in keys), returned)
                self.assertEqual(e.edit_text, expected)

    def test_keypress_max_length_replaces_highlight(self) -> None:
        """At the limit, a key replacing a highlighted range is inserted, and a refused key keeps the highlight."""
        e = urwid.Edit("", "abc", max_length=3)
        e.highlight = (0, 2)
        self.assertIsNone(e.keypress((20,), "x"))
        self.assertEqual(e.edit_text, "xc")

        e = urwid.Edit("", "abc", max_length=3, allow_tab=True)
        e.highlight = (0, 1)
        self.assertEqual(e.keypress((20,), "tab"), "tab")
        self.assertEqual((e.edit_text, e.highlight), ("abc", (0, 1)))

    def test_max_length_limits_all_text(self) -> None:
        """Text longer than max_length is refused from every source, leaving the text and signals untouched."""
        changes: list[str] = []

        def record(edit: urwid.Edit, new: str) -> None:
            changes.append(new)

        e = urwid.Edit("", "ab", max_length=2)
        urwid.connect_signal(e, "change", record)
        with self.assertRaises(ValueError):
            e.set_edit_text("abc")
        with self.assertRaises(ValueError):
            e.insert_text("c")
        self.assertEqual((e.edit_text, e.edit_pos, changes), ("ab", 2, []))

        with self.assertRaises(ValueError):
            urwid.Edit("", "abc", max_length=2)
        with self.assertRaises(ValueError):
            urwid.Edit(max_length=-1)
        with self.assertRaises(ValueError):
            e.max_length = -1
        with self.assertRaises(ValueError):
            e.max_length = 1
        self.assertEqual(e.max_length, 2)
        e.max_length = None
        e.set_edit_text("abcd")
        self.assertEqual(e.edit_text, "abcd")

    def test_keypress_enter_multiline(self) -> None:
        e = urwid.Edit("", "ab", multiline=True, edit_pos=1)
        e.keypress((20,), "enter")
        self.assertEqual(e.edit_text, "a\nb")

    def test_keypress_enter_not_multiline(self) -> None:
        e = urwid.Edit("", "ab")
        self.assertEqual(e.keypress((20,), "enter"), "enter")

    def test_submit_signal(self) -> None:
        """A single-line Edit sends "submit" on enter and still returns the key; a multiline one does not."""
        submitted: list[tuple[urwid.Edit, str]] = []
        e = urwid.Edit("", "ab")
        urwid.connect_signal(e, "submit", lambda edit, text: submitted.append((edit, text)))
        self.assertEqual(e.keypress((20,), "enter"), "enter")
        self.assertEqual(e.keypress((20,), "esc"), "esc")
        self.assertEqual(submitted, [(e, "ab")])

        m = urwid.Edit("", "ab", multiline=True)
        urwid.connect_signal(m, "submit", lambda edit, text: submitted.append((edit, text)))
        m.keypress((20,), "enter")
        self.assertEqual(submitted, [(e, "ab")])

        i = urwid.IntEdit("", 12)
        urwid.connect_signal(i, "submit", lambda edit, text: submitted.append((edit, text)))
        self.assertEqual(i.keypress((20,), " "), " ")
        self.assertEqual(i.keypress((20,), "enter"), "enter")
        self.assertEqual(submitted, [(e, "ab"), (i, "12")])

        r = urwid.Edit("", "ab")
        r._command_map = urwid.CommandMap()
        r._command_map["enter"] = Command.MAX_LEFT
        urwid.connect_signal(r, "submit", lambda edit, text: submitted.append((edit, text)))
        self.assertIsNone(r.keypress((20,), "enter"))
        self.assertEqual(r.edit_pos, 0)
        self.assertEqual(submitted, [(e, "ab"), (i, "12")])

    def test_set_edit_text_edit_pos(self) -> None:
        """edit_pos is set, clipped, before "postchange"; None keeps the current position clipped to the text."""
        positions: list[int] = []
        e = urwid.Edit("", "hello", edit_pos=4)
        urwid.connect_signal(e, "postchange", lambda edit, old: positions.append(edit.edit_pos))
        e.set_edit_text("hi")
        e.set_edit_text("hello world", edit_pos=11)
        e.set_edit_text("abc", edit_pos=10)
        e.set_edit_text("abcdef")
        self.assertEqual(positions, [2, 11, 3, 3])

    def test_keypress_postchange_sees_new_edit_pos(self) -> None:
        """Every editing key has moved the cursor before "postchange", also with a set_edit_text(text) override."""

        class TextOnlyEdit(urwid.Edit):
            """An Edit subclass overriding set_edit_text(text) without the edit_pos keyword."""

            def set_edit_text(self, text: str) -> None:  # type: ignore[override]  # no edit_pos keyword
                super().set_edit_text(text)

        def record(seen: list[tuple[str, int]], edit: urwid.Edit, old: str) -> None:
            seen.append((edit.edit_text, edit.edit_pos))

        cm = urwid.CommandMap()
        cm.bind(Command.DELETE_WORD_LEFT, "ctrl w")
        cm.bind(Command.DELETE_WORD_RIGHT, "meta d")
        cm.bind(Command.DELETE_TO_LINE_START, "ctrl u")
        cm.bind(Command.DELETE_TO_LINE_END, "ctrl k")
        cases = (
            ("insert", "ab", 1, None, "X", "aXb", 2),
            ("insert over highlight", "hello", 5, (1, 4), "X", "hXo", 2),
            ("backspace", "abcd", 2, None, "backspace", "acd", 1),
            ("backspace highlight", "hello", 5, (1, 4), "backspace", "ho", 1),
            ("delete", "abc", 1, None, "delete", "ac", 1),
            ("delete highlight", "hello", 0, (1, 4), "delete", "ho", 1),
            ("delete word left", "foo bar baz", 7, None, "ctrl w", "foo  baz", 4),
            ("delete word right", "foo bar baz", 3, None, "meta d", "foo baz", 3),
            ("delete to line start", "foo bar baz", 7, None, "ctrl u", " baz", 0),
            ("delete to line end", "foo bar baz", 3, None, "ctrl k", "foo", 3),
        )
        for cls in (urwid.Edit, TextOnlyEdit):
            for label, text, pos, highlight, key, expected_text, expected_pos in cases:
                with self.subTest(cls=cls.__name__, case=label):
                    e = cls("", text, edit_pos=pos)
                    e._command_map = cm
                    e.highlight = highlight
                    seen: list[tuple[str, int]] = []
                    urwid.connect_signal(e, "postchange", record, user_args=[seen])
                    self.assertIsNone(e.keypress((20,), key))
                    self.assertEqual(seen, [(expected_text, expected_pos)])
                    self.assertEqual(e.edit_pos, expected_pos)

    def test_keypress_keeps_cursor_moved_by_postchange_handler(self) -> None:
        """A "postchange" handler that moves the cursor, directly or by a nested key, keeps its position."""

        def move_home(edit: urwid.Edit, old: str) -> None:
            edit.set_edit_pos(0)

        def type_b_after_a(edit: urwid.Edit, old: str) -> None:
            if edit.edit_text == "a":
                edit.keypress((20,), "b")

        moved = urwid.Edit("", "ab")
        urwid.connect_signal(moved, "postchange", move_home)
        moved.keypress((20,), "x")
        self.assertEqual((moved.edit_text, moved.edit_pos), ("abx", 0))

        nested = urwid.Edit()
        urwid.connect_signal(nested, "postchange", type_b_after_a)
        nested.keypress((20,), "a")
        self.assertEqual((nested.edit_text, nested.edit_pos), ("ab", 2))

    def test_keypress_moves_cursor_through_set_edit_pos_override(self) -> None:
        """An editing key moves the cursor through an overridden set_edit_pos(), before "postchange"."""

        class RecordingEdit(urwid.Edit):
            """An Edit subclass recording every set_edit_pos() call with the text it was made for."""

            def __init__(self, edit_text: str) -> None:
                self.moves: list[tuple[str, int]] = []
                super().__init__("", edit_text)

            def set_edit_pos(self, pos: int) -> None:
                self.moves.append((self.edit_text, pos))
                super().set_edit_pos(pos)

        def count_moves(edit: RecordingEdit, old: str) -> None:
            seen.append(len(edit.moves))

        e = RecordingEdit("ab")
        seen: list[int] = []
        urwid.connect_signal(e, "postchange", count_moves)
        e.moves.clear()
        e.keypress((20,), "x")
        e.keypress((20,), "backspace")
        self.assertEqual(e.moves, [("abx", 3), ("ab", 2)])
        self.assertEqual(seen, [1, 2])

    def test_keypress_cursor_kept_by_set_edit_text_called_from_handler(self) -> None:
        """A set_edit_text() call made by a "change" handler keeps its own cursor rule."""
        e = urwid.Edit("", "ab", edit_pos=1)
        calls: list[int] = []

        def on_change(edit: urwid.Edit, new_text: str) -> None:
            if not calls:
                calls.append(edit.edit_pos)
                edit.set_edit_text("zz")
                calls.append(edit.edit_pos)

        urwid.connect_signal(e, "change", on_change)
        e.keypress((20,), "X")
        self.assertEqual(calls, [1, 1])
        self.assertEqual((e.edit_text, e.edit_pos), ("aXb", 2))

    def test_keypress_rejected_by_set_edit_text_override(self) -> None:
        """A set_edit_text() override that raises leaves the text, the cursor and the next call unchanged."""

        class RejectingEdit(urwid.Edit):
            """An Edit subclass whose set_edit_text() refuses every text while reject is set."""

            reject = False

            def set_edit_text(self, text: str) -> None:  # type: ignore[override]  # no edit_pos keyword
                if self.reject:
                    raise ValueError(text)
                super().set_edit_text(text)

        e = RejectingEdit("", "ab", edit_pos=1)
        e.reject = True
        with self.assertRaises(ValueError):
            e.keypress((20,), "X")
        self.assertEqual((e.edit_text, e.edit_pos), ("ab", 1))
        e.reject = False
        e.set_edit_text("abc")
        self.assertEqual(e.edit_pos, 1)

    def test_keypress_readline_commands(self) -> None:
        """The readline commands move and delete by word and to the line ends, and return the key at a boundary."""
        cm = urwid.CommandMap()
        cm.bind(Command.WORD_LEFT, "meta b")
        cm.bind(Command.WORD_RIGHT, "meta f")
        cm.bind(Command.DELETE_WORD_LEFT, "ctrl w")
        cm.bind(Command.DELETE_WORD_RIGHT, "meta d")
        cm.bind(Command.DELETE_TO_LINE_START, "ctrl u")
        cm.bind(Command.DELETE_TO_LINE_END, "ctrl k")
        cases = (
            ("one, two", 8, "meta b", "one, two", 5, None),
            ("one, two", 5, "meta b", "one, two", 0, None),
            ("one, two", 0, "meta b", "one, two", 0, "meta b"),
            ("one, two", 0, "meta f", "one, two", 3, None),
            ("one, two", 3, "meta f", "one, two", 8, None),
            ("one, two", 8, "meta f", "one, two", 8, "meta f"),
            ("one, two  ", 10, "ctrl w", "one, ", 5, None),
            ("one, two", 3, "meta d", "one", 3, None),
            ("café au", 7, "meta b", "café au", 6, None),
            ("café au", 6, "meta b", "café au", 0, None),
            ("a ❤️ b", 5, "meta b", "a ❤️ b", 0, None),
            ("a ❤️ b", 6, "ctrl w", "a ❤️ ", 5, None),
            ("a ❤️", 4, "ctrl w", "", 0, None),
            ("one two", 1, "meta d", "o two", 1, None),
            ("one, two", 4, "meta d", "one,", 4, None),
            ("foo_bar baz", 0, "meta f", "foo_bar baz", 7, None),
            ("x foo_bar", 9, "ctrl w", "x ", 2, None),
            (b"x foo_bar", 9, "meta b", b"x foo_bar", 2, None),
            ("ab\ncd ef", 6, "ctrl u", "ab\nef", 3, None),
            ("ab\ncd ef", 3, "ctrl u", "ab\ncd ef", 3, "ctrl u"),
            ("ab\ncd\nef", 4, "ctrl k", "ab\nc\nef", 4, None),
            ("ab\ncd", 3, "ctrl k", "ab\n", 3, None),
            ("ab", 2, "ctrl k", "ab", 2, "ctrl k"),
            (b"one two", 7, "ctrl w", b"one ", 4, None),
            (b"ab\ncd", 4, "ctrl u", b"ab\nd", 3, None),
        )
        for text, pos, key, expected_text, expected_pos, returned in cases:
            with self.subTest(text=text, pos=pos, key=key):
                e = urwid.Edit(b"" if isinstance(text, bytes) else "", text, multiline=True, edit_pos=pos)
                e._command_map = cm
                self.assertEqual(e.keypress((20,), key), returned)
                self.assertEqual((e.edit_text, e.edit_pos), (expected_text, expected_pos))

    def test_keypress_readline_word_bytes_wide_encoding(self) -> None:
        """A double-byte character is not split, even when its trail byte is an ASCII letter."""
        with set_temporary_encoding("big5"):
            e = urwid.Edit(b"", b"x \xa4\x41")
            e._command_map = urwid.CommandMap()
            e._command_map.bind(Command.DELETE_WORD_LEFT, "ctrl w")
            e.keypress((20,), "ctrl w")
            self.assertEqual((e.edit_text, e.edit_pos), (b"x ", 2))

    def test_keypress_readline_word_masked(self) -> None:
        """A masked text is one word, so the cursor does not reveal where the hidden text has spaces."""
        e = urwid.Edit("", "one two", mask="*", edit_pos=4)
        e._command_map = urwid.CommandMap()
        e._command_map.bind(Command.WORD_LEFT, "meta b")
        e._command_map.bind(Command.WORD_RIGHT, "meta f")
        e.keypress((20,), "meta f")
        self.assertEqual(e.edit_pos, 7)
        e.keypress((20,), "meta b")
        self.assertEqual(e.edit_pos, 0)
        e._command_map.bind(Command.DELETE_WORD_RIGHT, "meta d")
        e.keypress((20,), "meta d")
        self.assertEqual(e.edit_text, "")

    def test_readline_commands_unbound_by_default(self) -> None:
        """No key reaches the readline commands unless the application binds it."""
        e = urwid.Edit("", "one two")
        for key in ("ctrl a", "ctrl e", "ctrl u", "ctrl k", "ctrl w", "meta b", "meta f", "meta d", "meta backspace"):
            with self.subTest(key=key):
                self.assertEqual(e.keypress((20,), key), key)
                self.assertEqual((e.edit_text, e.edit_pos), ("one two", 7))

    def test_keypress_up_down_raises_when_pref_col_none(self) -> None:
        e = urwid.Edit("", "hello")

        def broken_get_pref_col(size: tuple[int]) -> None:
            return None

        e.get_pref_col = broken_get_pref_col  # type: ignore[method-assign]
        with self.assertRaises(ValueError):
            e.keypress((20,), "up")

    def test_keypress_backspace_with_highlight(self) -> None:
        e = urwid.Edit("", "hello world")
        e.highlight = (0, 6)
        e.keypress((20,), "backspace")
        self.assertEqual(e.edit_text, "world")
        self.assertIsNone(e.highlight)

    def test_keypress_backspace_at_start(self) -> None:
        e = urwid.Edit("", "hi", edit_pos=0)
        self.assertEqual(e.keypress((20,), "backspace"), "backspace")

    def test_keypress_backspace_removes_char(self) -> None:
        e = urwid.Edit("", "hi")
        e.keypress((20,), "backspace")
        self.assertEqual(e.edit_text, "h")

    def test_keypress_delete_with_highlight(self) -> None:
        e = urwid.Edit("", "hello world")
        e.highlight = (0, 6)
        e.keypress((20,), "delete")
        self.assertEqual(e.edit_text, "world")
        self.assertIsNone(e.highlight)

    def test_keypress_delete_at_end(self) -> None:
        e = urwid.Edit("", "hi", edit_pos=2)
        self.assertEqual(e.keypress((20,), "delete"), "delete")

    def test_keypress_delete_removes_char(self) -> None:
        e = urwid.Edit("", "hi", edit_pos=0)
        e.keypress((20,), "delete")
        self.assertEqual(e.edit_text, "i")

    def test_keypress_max_right(self) -> None:
        e = urwid.Edit("", "hello", edit_pos=0)
        e.keypress((20,), "end")
        self.assertEqual(e.edit_pos, 5)

    def test_mouse_event_button1(self) -> None:
        e = urwid.Edit("", "words here")
        self.assertTrue(e.mouse_event((20,), "mouse press", 1, 2, 0, True))
        self.assertEqual(e.edit_pos, 2)

    def test_mouse_event_other_button(self) -> None:
        e = urwid.Edit("", "words here")
        self.assertFalse(e.mouse_event((20,), "mouse press", 2, 2, 0, True))

    def test_render(self) -> None:
        e = urwid.Edit("? ", "yes")
        canv = e.render((10,), focus=True)
        self.assertEqual(list(canv.text), [b"? yes     "])
        self.assertEqual(canv.cursor, (5, 0))

    def test_render_no_focus(self) -> None:
        e = urwid.Edit("? ", "yes")
        canv = e.render((10,), focus=False)
        self.assertIsNone(canv.cursor)

    def test_get_line_translation_shifts_view_left(self) -> None:
        e = urwid.Edit("", "a very long line of text", wrap=urwid.CLIP)
        e.set_edit_pos(len(e.edit_text))
        canv = e.render((5,), focus=True)
        self.assertEqual(canv.cursor[0], 4)

    def test_get_line_translation_shifts_view_right(self) -> None:
        e = urwid.Edit("", "a very long line of text", wrap=urwid.CLIP)
        e.set_edit_pos(len(e.edit_text))
        e.render((5,), focus=True)
        e.set_edit_pos(0)
        canv = e.render((5,), focus=True)
        self.assertEqual(canv.cursor[0], 0)

    def test_render_ellipsis_scrolls_to_cursor(self) -> None:
        """In focus, an ellipsis Edit clips and scrolls to the cursor; out of focus, it shows the ellipsis again."""
        with set_temporary_encoding("utf-8"):
            e = urwid.Edit("", "abcdefghij", wrap=urwid.ELLIPSIS)
            for pos, row in ((2, "abcde"), (7, "defgh"), (10, "ghij ")):
                with self.subTest(pos=pos):
                    e.set_edit_pos(pos)
                    canv = e.render((5,), focus=True)
                    self.assertEqual(canv.text, [row.encode()])
                    self.assertEqual(canv.cursor, (min(pos, 4), 0))
            self.assertEqual(e.render((5,)).text, ["abcd…".encode()])

            m = urwid.Edit("", "abcdefghij\nklmnopqrstu", multiline=True, wrap=urwid.ELLIPSIS, edit_pos=19)
            canv = m.render((5,), focus=True)
            self.assertEqual(canv.text, ["abcd…".encode(), b"opqrs"])
            self.assertEqual(canv.cursor, (4, 1))

        class FirstLineEllipsisLayout(urwid.StandardTextLayout):
            """A layout whose ellipsis mode shows the first line only, so it has fewer rows than clip."""

            def layout(
                self,
                text: str | bytes,
                width: int,
                align: typing.Literal["left", "center", "right"] | urwid.Align,
                wrap: typing.Literal["any", "space", "clip", "ellipsis"] | urwid.WrapMode,
            ) -> list[list[tuple[int, int, int | bytes] | tuple[int, int | None]]]:
                rows = super().layout(text, width, align, wrap)
                return rows[:1] if wrap == urwid.ELLIPSIS else rows

        f = urwid.Edit("", "ab\ncd", multiline=True, wrap=urwid.ELLIPSIS, layout=FirstLineEllipsisLayout())
        self.assertEqual(f.render((5,), focus=True).rows(), f.rows((5,), True))

    def test_cursor_after_control_characters(self) -> None:
        """The cursor sits where its character is drawn, with the control characters left out of the canvas."""
        e = urwid.Edit("\x07> ", "a\x1b[1mb")

        canv = e.render((10,), focus=True)
        self.assertEqual([b"> ab      "], canv.text)
        self.assertEqual((4, 0), canv.cursor)

        e.set_edit_pos(1)
        self.assertEqual((3, 0), e.render((10,), focus=True).cursor)
        self.assertEqual("a\x1b[1mb", e.edit_text)
        self.assertEqual(("\x07> a\x1b[1mb", []), e.get_text())

    def test_delete_highlighted_no_highlight(self) -> None:
        e = urwid.Edit("", "hi")
        self.assertFalse(e._delete_highlighted())

    def test_delete_highlighted_with_highlight(self) -> None:
        e = urwid.Edit("", "hello world")
        e.highlight = (0, 6)
        self.assertTrue(e._delete_highlighted())
        self.assertEqual(e.edit_text, "world")
        self.assertEqual(e.edit_pos, 0)
        self.assertIsNone(e.highlight)


class GutterEdit(urwid.Edit):
    """Edit drawn right of a gutter, mapping cursor coordinates through overridden methods."""

    gutter = 2

    def get_cursor_coords(self, size: tuple[int]) -> tuple[int, int] | None:
        (maxcol,) = size
        coords = super().get_cursor_coords((maxcol - self.gutter,))
        return None if coords is None else (coords[0] + self.gutter, coords[1])

    def move_cursor_to_coords(self, size: tuple[int], x: int | str, y: int) -> bool:
        (maxcol,) = size
        if isinstance(x, int):
            x -= self.gutter
        return super().move_cursor_to_coords((maxcol - self.gutter,), x, y)


class EditKeypressMovementTest(unittest.TestCase):
    def setUp(self):
        self.t1 = urwid.Edit(b"", "blah blah")
        self.t2 = urwid.Edit(b"stuff:", "blah blah")
        self.t3 = urwid.Edit(b"junk:\n", "blah blah\n\nbloo", 1)
        self.t4 = urwid.Edit("better:")

    def ktest(self, e, key, expected, pos, desc):
        got = e.keypress((12,), key)
        assert got == expected, f"{desc}.  got: {got!r} expected:{expected!r}"
        assert e.edit_pos == pos, f"{desc}. pos: {e.edit_pos!r} expected pos: {pos!r}"

    def test_vertical_keys_use_an_overridden_get_cursor_coords(self):
        for key, start, expected in (("up", 10, 3), ("down", 3, 10), ("home", 10, 7), ("end", 3, 6)):
            with self.subTest(key):
                edit = GutterEdit("", "abcdef\nabcdef")
                edit.set_edit_pos(start)
                self.assertIsNone(edit.keypress((10,), key))
                self.assertEqual(expected, edit.edit_pos)

    def test_keys_without_a_cursor_from_an_override(self):
        """A gutter as wide as the whole edit leaves no columns for the text, so there is no cursor to move from."""
        for key in ("up", "down", "home", "end"):
            with self.subTest(key):
                edit = GutterEdit("", "ab\ncd")
                edit.set_edit_pos(4)
                self.assertEqual(key, edit.keypress((2,), key))
                self.assertEqual(4, edit.edit_pos)

    def test_keys_at_zero_columns(self):
        """With no columns there is no cursor, and the keys that need one still work from the edit position."""
        for key, expected in (("up", "up"), ("down", "down"), ("home", None), ("end", None)):
            with self.subTest(key):
                edit = urwid.Edit("", "ab\ncd")
                edit.set_edit_pos(4)
                self.assertEqual(expected, edit.keypress((0,), key))

    def test1_left(self):
        self.t1.set_edit_pos(0)
        self.ktest(self.t1, "left", "left", 0, "left at left edge")

        self.ktest(self.t2, "left", None, 8, "left within text")

        self.t3.set_edit_pos(10)
        self.ktest(self.t3, "left", None, 9, "left after newline")

    def test2_right(self):
        self.ktest(self.t1, "right", "right", 9, "right at right edge")

        self.t2.set_edit_pos(8)
        self.ktest(self.t2, "right", None, 9, "right at right edge-1")
        self.t3.set_edit_pos(0)
        self.t3.keypress((12,), "right")
        assert self.t3.get_pref_col((12,)) == 1

    def test3_up(self):
        self.ktest(self.t1, "up", "up", 9, "up at top")
        self.t2.set_edit_pos(2)
        self.t2.keypress((12,), "left")
        assert self.t2.get_pref_col((12,)) == 7
        self.ktest(self.t2, "up", "up", 1, "up at top again")
        assert self.t2.get_pref_col((12,)) == 7
        self.t3.set_edit_pos(10)
        self.ktest(self.t3, "up", None, 0, "up at top+1")

    def test4_down(self):
        self.ktest(self.t1, "down", "down", 9, "down single line")
        self.t3.set_edit_pos(5)
        self.ktest(self.t3, "down", None, 10, "down line 1 to 2")
        self.ktest(self.t3, "down", None, 15, "down line 2 to 3")
        self.ktest(self.t3, "down", "down", 15, "down at bottom")

    def test_utf8_input(self):
        with set_temporary_encoding("utf-8"):
            self.t1.set_edit_text("")
            self.t1.keypress((12,), "û")
            self.assertEqual(self.t1.edit_text, "û".encode())
            self.t4.keypress((12,), "û")
            self.assertEqual(self.t4.edit_text, "û")


class EditRenderTest(unittest.TestCase):
    def rtest(self, w, expected_text, expected_cursor):
        expected_text = [t.encode("iso8859-1") for t in expected_text]
        get_cursor = w.get_cursor_coords((4,))
        assert get_cursor == expected_cursor, f"got: {get_cursor!r} expected: {expected_cursor!r}"
        r = w.render((4,), focus=1)
        text = [t for a, cs, t in [ln[0] for ln in r.content()]]
        assert text == expected_text, f"got: {text!r} expected: {expected_text!r}"
        assert r.cursor == expected_cursor, f"got: {r.cursor!r} expected: {expected_cursor!r}"

    def test1_SpaceWrap(self):
        w = urwid.Edit("", "blah blah")
        w.set_edit_pos(0)
        self.rtest(w, ["blah", "blah"], (0, 0))

        w.set_edit_pos(4)
        self.rtest(w, ["blah", "blah"], (3, 0))

        w.set_edit_pos(5)
        self.rtest(w, ["blah", "blah"], (0, 1))

        w.set_edit_pos(9)
        self.rtest(w, ["blah", "blah"], (3, 1))

    def test2_ClipWrap(self):
        w = urwid.Edit("", "blah\nblargh", 1)
        w.set_wrap_mode("clip")
        w.set_edit_pos(0)
        self.rtest(w, ["blah", "blar"], (0, 0))

        w.set_edit_pos(10)
        self.rtest(w, ["blah", "argh"], (3, 1))

        w.set_align_mode("right")
        w.set_edit_pos(6)
        self.rtest(w, ["blah", "larg"], (0, 1))

    def test3_AnyWrap(self):
        w = urwid.Edit("", "blah blah")
        w.set_wrap_mode("any")

        self.rtest(w, ["blah", " bla", "h   "], (1, 2))

    def test_zero_width_has_no_cursor(self):
        for wrap in ("space", "any", "clip"):
            with self.subTest(wrap):
                w = urwid.Edit("? ", "yes", wrap=wrap)
                self.assertIsNone(w.get_cursor_coords((0,)))
                self.assertIsNone(w.render((0,), focus=True).cursor)

    def test4_CursorNudge(self):
        w = urwid.Edit("", "hi", align="right")
        w.keypress((4,), "end")

        self.rtest(w, ["  hi"], (3, 0))

        w.keypress((4,), "left")
        self.rtest(w, ["  hi"], (3, 0))


class IntEditTest(unittest.TestCase):
    def test_valid_char(self) -> None:
        e = urwid.IntEdit()
        self.assertTrue(e.valid_char("5"))
        self.assertFalse(e.valid_char("a"))

    def test_default_none(self) -> None:
        e = urwid.IntEdit()
        self.assertEqual(e.edit_text, "")

    def test_keypress_trims_leading_zeros(self) -> None:
        e = urwid.IntEdit("", 5002)
        e.keypress((10,), "home")
        e.keypress((10,), "delete")
        self.assertEqual(e.edit_text, "002")
        e.keypress((10,), "end")
        self.assertEqual(e.edit_text, "2")

    def test_keypress_keeps_lone_zero(self) -> None:
        e = urwid.IntEdit()
        e.keypress((10,), "0")
        e.keypress((10,), "0")
        self.assertEqual(e.edit_text, "0")
        e = urwid.IntEdit("", 0)
        e.keypress((10,), "end")
        self.assertEqual(e.edit_text, "0")
        self.assertEqual(e.value(), 0)

    def test_keypress_postchange_once_per_change(self) -> None:
        """A key sends "postchange" once with the trimmed text and cursor, and not at all when the text stays."""

        def record(seen: list[tuple[str, int]], edit: urwid.IntEdit, old: str) -> None:
            seen.append((edit.edit_text, edit.edit_pos))

        cases: tuple[tuple[str, str, tuple[str, ...], list[tuple[str, int]]], ...] = (
            ("digit after zero", "0", ("7",), [("7", 1)]),
            ("zero after zero", "0", ("0",), []),
            ("digits into empty", "", ("0", "5"), [("0", 1), ("5", 1)]),
            ("zeros trimmed after delete", "5002", ("home", "delete", "end"), [("002", 0), ("2", 1)]),
        )
        for label, text, keys, expected in cases:
            with self.subTest(case=label):
                e = urwid.IntEdit("", text)
                seen: list[tuple[str, int]] = []
                urwid.connect_signal(e, "postchange", record, user_args=[seen])
                for key in keys:
                    self.assertIsNone(e.keypress((10,), key))
                self.assertEqual(seen, expected)

    def test_keypress_unhandled_passthrough(self) -> None:
        e = urwid.IntEdit()
        self.assertEqual(e.keypress((10,), "shift f1"), "shift f1")

    def test_value(self) -> None:
        e = urwid.IntEdit()
        e.keypress((10,), "5")
        e.keypress((10,), "1")
        self.assertEqual(e.value(), 51)

    def test_keypress_refuses_digits_beyond_int_limit(self) -> None:
        """Typing stops at the int digit limit, so value() still converts the text."""
        e = urwid.IntEdit("", "1" * 9)
        with mock.patch.object(sys, "get_int_max_str_digits", return_value=10):
            self.assertIsNone(e.keypress((20,), "2"))
            self.assertEqual(e.keypress((20,), "3"), "3")
        self.assertEqual(e.edit_text, "1" * 9 + "2")
        self.assertEqual(e.value(), 1111111112)

    def test_keypress_without_int_limit(self) -> None:
        """A limit of 0 accepts digits without bound."""
        e = urwid.IntEdit("", "1" * 9)
        with mock.patch.object(sys, "get_int_max_str_digits", return_value=0):
            self.assertIsNone(e.keypress((20,), "2"))
        self.assertEqual(e.edit_text, "1" * 9 + "2")

    def test_keypress_replaces_highlight_at_int_limit(self) -> None:
        """A digit replacing a highlighted range is accepted when the result stays within the limit."""
        e = urwid.IntEdit("", "1" * 10)
        e.highlight = (0, 2)
        with mock.patch.object(sys, "get_int_max_str_digits", return_value=10):
            self.assertIsNone(e.keypress((20,), "2"))
        self.assertEqual(e.edit_text, "2" + "1" * 8)

    def test_value_empty(self) -> None:
        e = urwid.IntEdit()
        self.assertEqual(e.value(), 0)


if __name__ == "__main__":
    unittest.main()

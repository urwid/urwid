from __future__ import annotations

import contextlib
import itertools
import re
import sys
import typing
import unittest
from unittest import mock

import urwid
import urwid.testing
from urwid.command_map import Command
from urwid.numedit import FloatEdit, NumEdit
from urwid.util import set_temporary_encoding

if typing.TYPE_CHECKING:
    from collections.abc import Generator

# regional indicators U and S: the two together form one flag cluster
RI_U = "\U0001f1fa"
RI_S = "\U0001f1f8"
# man + ZWJ + woman + ZWJ + girl, one cluster
FAMILY = "\U0001f468\u200d\U0001f469\u200d\U0001f467"


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

    def test_cancel_signal(self) -> None:
        """An Edit sends "cancel" on a key mapped to 'menu' and still returns the key, multiline or not."""
        cancelled: list[tuple[urwid.Edit, str]] = []
        e = urwid.Edit("", "ab")
        urwid.connect_signal(e, "cancel", lambda edit, text: cancelled.append((edit, text)))
        self.assertEqual(e.keypress((20,), "enter"), "enter")
        self.assertEqual(e.keypress((20,), "esc"), "esc")
        self.assertEqual(cancelled, [(e, "ab")])

        m = urwid.Edit("", "a\nb", multiline=True)
        urwid.connect_signal(m, "cancel", lambda edit, text: cancelled.append((edit, text)))
        self.assertEqual(m.keypress((20,), "esc"), "esc")
        self.assertEqual(cancelled, [(e, "ab"), (m, "a\nb")])

        r = urwid.Edit("", "ab")
        r._command_map = urwid.CommandMap()
        r._command_map["esc"] = Command.MAX_LEFT
        r._command_map["f10"] = Command.MENU
        urwid.connect_signal(r, "cancel", lambda edit, text: cancelled.append((edit, text)))
        self.assertIsNone(r.keypress((20,), "esc"))
        self.assertEqual(r.keypress((20,), "f10"), "f10")
        self.assertEqual(cancelled, [(e, "ab"), (m, "a\nb"), (r, "ab")])

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
        cm.bind(Command.LINE_START, "ctrl a")
        cm.bind(Command.LINE_END, "ctrl e")
        cm.bind(Command.DELETE_SPACE_WORD_LEFT, "meta w")
        cm.bind(Command.DELETE_RIGHT, "ctrl d")
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

    def test_move_cursor_to_coords_through_set_edit_pos_override(self) -> None:
        """Up, down, home, end and a mouse click move the cursor through an overridden set_edit_pos()."""

        class RecordingEdit(urwid.Edit):
            """An Edit subclass recording every set_edit_pos() call."""

            def __init__(self) -> None:
                self.moves: list[int] = []
                super().__init__("", "one\ntwo\nthree", multiline=True, edit_pos=5)
                self.moves.clear()

            def set_edit_pos(self, pos: int) -> None:
                self.moves.append(pos)
                super().set_edit_pos(pos)

        for key, expected in (("up", 1), ("down", 9), ("home", 4), ("end", 7)):
            with self.subTest(key=key):
                e = RecordingEdit()
                self.assertIsNone(e.keypress((20,), key))
                self.assertEqual(e.moves, [expected])
                self.assertEqual(e.edit_pos, expected)

        e = RecordingEdit()
        self.assertTrue(e.mouse_event((20,), "mouse press", 1, 2, 2, True))
        self.assertEqual(e.moves, [10])
        self.assertEqual(e.edit_pos, 10)

    def test_set_edit_text_moves_cursor_through_set_edit_pos_override(self) -> None:
        """set_edit_text(edit_pos=) and a cursor clipped to a shorter text call the set_edit_pos() override."""

        class RecordingEdit(urwid.Edit):
            """An Edit subclass recording every set_edit_text() and set_edit_pos() call."""

            def __init__(self) -> None:
                self.calls: list[tuple[str, str | int]] = []
                super().__init__("", "hello")
                self.calls.clear()

            def set_edit_text(self, text: str, *, edit_pos: int | None = None) -> None:
                self.calls.append(("text", text))
                super().set_edit_text(text, edit_pos=edit_pos)

            def set_edit_pos(self, pos: int) -> None:
                self.calls.append(("pos", pos))
                super().set_edit_pos(pos)

        cases = (
            ("set_edit_text edit_pos", lambda e: e.set_edit_text("abc", edit_pos=1), [("text", "abc"), ("pos", 1)]),
            ("set_edit_text clips", lambda e: e.set_edit_text("a"), [("text", "a"), ("pos", 1)]),
        )
        for label, write, expected in cases:
            with self.subTest(case=label):
                e = RecordingEdit()
                write(e)
                self.assertEqual(e.calls, expected)

    def test_edit_pos_signal(self) -> None:
        """Send "edit_pos" with the old and the new position for each cursor move.

        A text change sends it before "postchange", and a write that keeps the position sends nothing.
        """
        cm = urwid.CommandMap()
        cm.bind(Command.UNDO, "ctrl _")
        e = urwid.Edit("", "hello", edit_pos=5, undo_limit=10)
        e._command_map = cm
        seen: list[object] = []
        urwid.connect_signal(e, "edit_pos", lambda _w, old, new: seen.append((old, new)))
        urwid.connect_signal(e, "postchange", lambda w, _old: seen.append(("postchange", w.edit_pos)))
        steps = (
            ("left", lambda: e.keypress((20,), "left"), [(5, 4)]),
            ("typed", lambda: e.keypress((20,), "x"), [(4, 5), ("postchange", 5)]),
            ("undo", lambda: e.keypress((20,), "ctrl _"), [(5, 4), ("postchange", 4)]),
            ("same position", lambda: e.set_edit_pos(4), []),
            ("clipped by a shorter text", lambda: e.set_edit_text("hi"), [(4, 2), ("postchange", 2)]),
            ("offset kept by a longer text", lambda: e.set_edit_text("hiya"), [("postchange", 2)]),
            ("explicit position", lambda: e.set_edit_text("hey", edit_pos=0), [(2, 0), ("postchange", 0)]),
            ("property", lambda: setattr(e, "edit_pos", 9), [(0, 3)]),
            ("mouse", lambda: e.mouse_event((20,), "mouse press", 1, 1, 0, True), [(3, 1)]),
        )
        for label, step, expected in steps:
            with self.subTest(step=label):
                seen.clear()
                step()
                self.assertEqual(seen, expected)

    def test_keypress_cursor_after_set_edit_text_override_moves_it(self) -> None:
        """An editing key leaves the cursor at the edit when a set_edit_text() override moves it after the base call."""

        class CursorToEndEdit(urwid.Edit):
            """An Edit subclass whose set_edit_text() puts the cursor at the end unless a position is given."""

            def set_edit_text(self, text: str, edit_pos: int | None = None) -> None:
                super().set_edit_text(text)
                self.set_edit_pos(edit_pos or len(text))

        for key, expected in (("X", ("abXcdef", 3)), ("backspace", ("acdef", 1))):
            with self.subTest(key=key):
                e = CursorToEndEdit("", "abcdef", edit_pos=2)
                self.assertIsNone(e.keypress((20,), key))
                self.assertEqual((e.edit_text, e.edit_pos), expected)

        e = CursorToEndEdit("", "ab", edit_pos=0)
        e.set_edit_text("abcd")
        self.assertEqual(e.edit_pos, 4)

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

    def test_subclass_with_own_keypress_helper(self) -> None:
        """A subclass helper named _keypress that calls the base keypress is not called back by it."""

        class HelperEdit(urwid.Edit):
            def keypress(self, size: tuple[int], key: str) -> str | None:  # type: ignore[override]
                return self._keypress(size, key)

            def _keypress(self, size: tuple[int], key: str) -> str | None:
                return None if key == "f2" else super().keypress(size, key)

        e = HelperEdit("", "ab")
        self.assertIsNone(e.keypress((20,), "x"))
        self.assertIsNone(e.keypress((20,), "f2"))
        self.assertEqual(e.edit_text, "abx")

    def test_keypress_readline_commands(self) -> None:
        """The readline commands move and delete by word and to the line ends, and return the key at a boundary."""
        cm = urwid.CommandMap()
        cm.bind(Command.WORD_LEFT, "meta b")
        cm.bind(Command.WORD_RIGHT, "meta f")
        cm.bind(Command.DELETE_WORD_LEFT, "ctrl w")
        cm.bind(Command.DELETE_WORD_RIGHT, "meta d")
        cm.bind(Command.DELETE_TO_LINE_START, "ctrl u")
        cm.bind(Command.DELETE_TO_LINE_END, "ctrl k")
        cm.bind(Command.LINE_START, "ctrl a")
        cm.bind(Command.LINE_END, "ctrl e")
        cm.bind(Command.DELETE_SPACE_WORD_LEFT, "meta w")
        cm.bind(Command.DELETE_RIGHT, "ctrl d")
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
            # a wrapped line: the line commands go past the screen row, to the newline or the text edge
            ("alpha beta gamma delta epsilon", 23, "ctrl a", "alpha beta gamma delta epsilon", 0, None),
            ("alpha beta gamma delta epsilon", 3, "ctrl e", "alpha beta gamma delta epsilon", 30, None),
            ("ab\ncd\nef", 4, "ctrl a", "ab\ncd\nef", 3, None),
            ("ab\ncd\nef", 4, "ctrl e", "ab\ncd\nef", 5, None),
            ("ab\ncd\nef", 3, "ctrl a", "ab\ncd\nef", 3, "ctrl a"),
            ("ab\ncd\nef", 5, "ctrl e", "ab\ncd\nef", 5, "ctrl e"),
            ("ab\ncd\nef", 2, "ctrl e", "ab\ncd\nef", 2, "ctrl e"),
            (b"ab\ncd", 5, "ctrl a", b"ab\ncd", 3, None),
            (b"ab\ncd", 0, "ctrl e", b"ab\ncd", 2, None),
            # bash's ctrl w (unix-word-rubout) and ctrl d (delete-char) give the same results
            ("ls /usr/local/", 14, "meta w", "ls ", 3, None),
            ("ls /usr/local/  ", 16, "meta w", "ls ", 3, None),
            ("one, two", 4, "meta w", " two", 0, None),
            ("a\nb c", 3, "meta w", "a\n c", 2, None),
            ("  ", 2, "meta w", "", 0, None),
            ("ab", 0, "meta w", "ab", 0, "meta w"),
            (b"x \xc3\xa9t\xc3\xa9", 7, "meta w", b"x ", 2, None),
            ("abc", 1, "ctrl d", "ac", 1, None),
            ("abc", 3, "ctrl d", "abc", 3, "ctrl d"),
            ("a" + FAMILY + "b", 1, "ctrl d", "ab", 1, None),
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
        keys = (
            "ctrl a",
            "ctrl e",
            "ctrl u",
            "ctrl k",
            "ctrl w",
            "ctrl d",
            "meta b",
            "meta f",
            "meta d",
            "meta backspace",
        )
        for key in keys:
            with self.subTest(key=key):
                self.assertEqual(e.keypress((20,), key), key)
                self.assertEqual((e.edit_text, e.edit_pos), ("one two", 7))

    def test_readline_preset_on_shared_map(self) -> None:
        """With the preset on the shared map, ctrl a moves an Edit and leaves a ListBox focus where it is."""
        cm = urwid.CommandMap()
        cm.bind_readline()
        with mock.patch.object(urwid.Widget, "_command_map", cm):
            e = urwid.Edit("", "one two")
            self.assertIsNone(e.keypress((20,), "ctrl a"))
            self.assertEqual(e.edit_pos, 0)
            listbox = urwid.ListBox(urwid.SimpleFocusListWalker([urwid.SelectableIcon(str(n)) for n in range(20)]))
            listbox.focus_position = 10
            self.assertEqual(listbox.keypress((10, 5), "ctrl a"), "ctrl a")
            self.assertEqual(listbox.focus_position, 10)

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

    def test_mouse_drag_and_release_need_a_press_on_the_edit(self) -> None:
        """A button 1 drag or release moves the cursor only after a press on the same Edit, whatever the modifiers."""
        cases = (
            ("press here", [("mouse press", 1, 2, 0)], 6, True),
            ("press with a modifier", [("ctrl mouse press", 1, 2, 0)], 6, True),
            ("no press", [], 0, False),
            ("press of another button", [("mouse press", 3, 2, 0)], 0, False),
            ("press, then focus lost", [("mouse press", 1, 2, 0), "unfocused render"], 2, False),
            ("press already released", [("mouse press", 1, 2, 0), ("mouse release", 1, 4, 0)], 4, False),
        )
        events = ("mouse drag", "mouse release", "meta mouse drag", "double mouse release")
        for (label, before, expected_pos, handled), event in itertools.product(cases, events):
            with self.subTest(case=label, event=event):
                e = urwid.Edit("", "words here", edit_pos=0)
                for step in before:
                    if step == "unfocused render":
                        e.render((20,), focus=False)
                    else:
                        e.mouse_event((20,), *step, True)
                self.assertEqual(e.mouse_event((20,), event, 1, 6, 0, True), handled)
                self.assertEqual(e.edit_pos, expected_pos)

    def test_mouse_drag_and_release_after_a_press_on_a_sibling(self) -> None:
        """A press on one Edit of a Pile, dragged and released over another, leaves the cursor of the other alone."""
        top, bottom = urwid.Edit("", "top text", edit_pos=0), urwid.Edit("", "bottom", edit_pos=0)
        pile = urwid.Pile([top, bottom])
        pile.mouse_event((20,), "mouse press", 1, 3, 1, True)
        pile.render((20,), focus=True)
        pile.mouse_event((20,), "mouse drag", 1, 4, 0, True)
        pile.mouse_event((20,), "mouse release", 1, 5, 0, True)
        self.assertEqual((top.edit_pos, bottom.edit_pos, pile.focus), (0, 3, bottom))

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

    def test_edit_pos_snaps_to_grapheme_cluster_start(self) -> None:
        """A position set inside a grapheme cluster moves back to the cluster start."""
        for label, text, inside, start in (
            ("combining", "e\u0301x", 1, 0),
            ("flag", f"a{RI_U}{RI_S}b", 2, 1),
            ("zwj", f"a{FAMILY}b", 3, 1),
        ):
            with self.subTest(label):
                e = urwid.Edit("", text)
                e.set_edit_pos(inside)
                self.assertEqual(e.edit_pos, start)
                e.edit_pos = inside
                self.assertEqual(e.edit_pos, start)
                e.set_edit_text(text, edit_pos=inside)
                self.assertEqual(e.edit_pos, start)

    def test_typing_into_next_cluster_moves_cursor_past_it(self) -> None:
        """A typed code point that joins the cluster after the cursor leaves the cursor after that cluster."""
        e = urwid.Edit("", f"ab{RI_S}")
        e.keypress((20,), "left")
        self.assertEqual(e.insert_text_result(RI_U), (f"ab{RI_U}{RI_S}", 4))
        e.keypress((20,), RI_U)
        self.assertEqual((e.edit_text, e.edit_pos), (f"ab{RI_U}{RI_S}", 4))
        e.keypress((20,), "c")
        self.assertEqual(e.edit_text, f"ab{RI_U}{RI_S}c")

        e = urwid.Edit("", RI_S, edit_pos=1)
        e.insert_text(RI_U)
        self.assertEqual((e.edit_text, e.edit_pos), (f"{RI_S}{RI_U}", 2))

    def test_deleting_into_one_cluster_keeps_cursor_on_boundary(self) -> None:
        """Deleting the character between two regional indicators leaves the cursor before the flag they form."""
        for key, pos in (("backspace", 2), ("delete", 1)):
            with self.subTest(key):
                e = urwid.Edit("", f"{RI_U}x{RI_S}", edit_pos=pos)
                e.keypress((20,), key)
                self.assertEqual((e.edit_text, e.edit_pos), (f"{RI_U}{RI_S}", 0))
                e.keypress((20,), "c")
                self.assertEqual(e.edit_text, f"c{RI_U}{RI_S}")

    def test_mouse_click_on_wide_character(self) -> None:
        """A click on either half of a double-width character puts the cursor at its start."""
        for col in (2, 3):
            with self.subTest(col=col):
                e = urwid.Edit("", "ab日x")
                self.assertTrue(e.mouse_event((20,), "mouse press", 1, col, 0, True))
                self.assertEqual(e.edit_pos, 2)

    def test_clip_scroll_keeps_wide_characters_whole(self) -> None:
        """Scrolling a clipped row never cuts a double-width character, and shows the one under the cursor."""
        with set_temporary_encoding("utf-8"):
            for wrap in (urwid.CLIP, urwid.ELLIPSIS):
                for text, pos, cols, row, cursor in (
                    ("日本語", 3, 4, "語  ", 2),
                    ("日本語", 3, 2, "  ", 0),
                    ("日本語", 3, 1, " ", 0),
                    ("日本語x", 2, 3, "語x", 0),
                    ("日本語x", 2, 1, " ", 0),
                    # the cursor column fits, but the wide character under it crosses the right edge
                    ("a日本", 1, 2, "日", 0),
                    ("ab日", 2, 3, "b日", 1),
                ):
                    with self.subTest(wrap=wrap, text=text, cols=cols):
                        canv = urwid.Edit("", text, wrap=wrap, edit_pos=pos).render((cols,), focus=True)
                        self.assertEqual(canv.text, [row.encode()])
                        self.assertEqual(canv.cursor, (cursor, 0))

            for pos in range(5):
                with self.subTest(pos=pos):
                    e = urwid.Edit("", "日本語ab", wrap=urwid.CLIP, edit_pos=pos)
                    urwid.testing.check_flow_sizing(e, cols=4)
                    urwid.testing.check_flow_sizing(e, cols=2)

    def test_invalid_utf8_bytes_edit(self) -> None:
        """A bytes Edit holding text that is not valid UTF-8 keeps the cursor where it is set, and scrolls."""
        with set_temporary_encoding("utf-8"):
            e = urwid.Edit(b"", b"a\xff\xfeb", edit_pos=1, wrap=urwid.CLIP)
            e.keypress((20,), "x")
            self.assertEqual((e.edit_text, e.edit_pos), (b"ax\xff\xfeb", 2))
            e.set_edit_pos(3)
            self.assertEqual(e.edit_pos, 3)
            with self.assertWarns(UnicodeWarning):
                self.assertEqual(e.get_cursor_coords((2,)), (1, 0))

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

    def test_render_cache_follows_focus(self) -> None:
        """Cache a focused and an unfocused render apart.

        Both are replaced after an invalidation.
        """
        e = urwid.Edit(
            "? ",
            "ab",
            validator=lambda _text: "bad",
            validation_attr={urwid.Severity.ERROR: "err"},
            validation_focus_attr={urwid.Severity.ERROR: "err focus"},
        )
        plain = e.render((6,))
        focused = e.render((6,), focus=True)
        self.assertIsNone(plain.cursor)
        self.assertEqual(focused.cursor, (4, 0))
        self.assertEqual(next(iter(plain.content())), [("err", None, b"? ab  ")])
        self.assertEqual(next(iter(focused.content())), [("err focus", None, b"? ab  ")])
        self.assertIs(e.render((6,)), plain)
        self.assertIs(e.render((6,), focus=True), focused)
        e._invalidate()
        self.assertIsNot(e.render((6,)), plain)
        self.assertIsNot(e.render((6,), focus=True), focused)


class EditPlaceholderTest(unittest.TestCase):
    def test_drawn_while_empty_focused_or_not(self) -> None:
        e = urwid.Edit("? ", placeholder="name")
        for focus in (False, True):
            with self.subTest(focus=focus):
                self.assertEqual(e.render((10,), focus=focus).text, [b"? name    "])
        self.assertEqual(e.render((10,), focus=True).cursor, (2, 0))
        e.keypress((10,), "x")
        self.assertEqual(e.render((10,)).text, [b"? x       "])

    def test_not_part_of_text(self) -> None:
        e = urwid.Edit("? ", placeholder="name", max_length=1)
        self.assertEqual(e.get_text(), ("? ", []))
        self.assertEqual(e.edit_text, "")
        self.assertEqual(e.pack((10,)), urwid.Edit("? ").pack((10,)))
        self.assertIsNone(e.keypress((10,), "x"))

    def test_attributes_follow_caption(self) -> None:
        e = urwid.Edit("? ", placeholder=("hint", "name"))
        self.assertEqual(
            next(iter(e.render((8,)).content())),
            [(None, None, b"? "), ("hint", None, b"name"), (None, None, b"  ")],
        )

    def test_never_masked(self) -> None:
        e = urwid.Edit("pw: ", mask="*", placeholder="secret")
        self.assertEqual(e.render((12,)).text, [b"pw: secret  "])
        e.keypress((12,), "a")
        self.assertEqual(e.render((12,)).text, [b"pw: *       "])

    def test_bytes_caption(self) -> None:
        e = urwid.Edit(b"? ", b"", placeholder="name")
        self.assertEqual(e.render((8,)).text, [b"? name  "])

    def test_not_drawn_when_caption_does_not_fit(self) -> None:
        """A caption that needs a horizontal shift to show the cursor is drawn without the placeholder."""
        e = urwid.Edit("longcaption", placeholder="x", wrap="clip")
        self.assertEqual(e.render((5,)).text, [b"longc"])
        self.assertEqual(e.render((5,), focus=True).text, [b"tion "])

    def test_rows_by_mode(self) -> None:
        cases = [
            ("single-line default clips", False, None, [b"? a   "]),
            ("single-line grows when asked", False, True, [b"? a   ", b"long  ", b"hint  "]),
            ("multiline default grows", True, None, [b"? a   ", b"long  ", b"hint  "]),
            ("multiline clips when asked", True, False, [b"? a   "]),
        ]
        for (label, multiline, grow, expected), focus in itertools.product(cases, (False, True)):
            with self.subTest(label, focus=focus):
                e = urwid.Edit("? ", multiline=multiline, placeholder="a long hint", placeholder_grow=grow)
                rows = e.rows((6,), focus)  # uncached: no canvas has been rendered yet
                canvas = e.render((6,), focus)
                self.assertEqual(canvas.text, expected)
                self.assertEqual(rows, canvas.rows())
                self.assertEqual(e.render((6,), focus=True).cursor, (2, 0))

    def test_clip_pads_to_caption_rows(self) -> None:
        """A caption laid out on more rows than caption and placeholder together keeps its row count."""
        e = urwid.Edit("ab ", placeholder="c")
        rows = e.rows((2,))
        canvas = e.render((2,))
        self.assertEqual(rows, urwid.Edit("ab ").rows((2,)))
        self.assertEqual(canvas.rows(), rows)

    def test_cursor_with_right_alignment(self) -> None:
        """The cursor stays where the caption alone puts it."""
        e = urwid.Edit("? ", align="right", placeholder="name")
        self.assertEqual(e.get_cursor_coords((10,)), urwid.Edit("? ", align="right").get_cursor_coords((10,)))
        canvas = e.render((10,), focus=True)
        self.assertEqual(canvas.text, [b"    ? name"])
        self.assertEqual(canvas.cursor, (9, 0))

    def test_setters_invalidate(self) -> None:
        e = urwid.Edit("? ", multiline=True)
        self.assertEqual(e.render((6,)).text, [b"?     "])
        e.placeholder = "a long hint"
        self.assertEqual(e.placeholder, "a long hint")
        self.assertEqual(e.render((6,)).text, [b"? a   ", b"long  ", b"hint  "])
        e.placeholder_grow = False
        self.assertEqual(e.render((6,)).text, [b"? a   "])
        self.assertEqual(e.rows((6,)), 1)
        e.placeholder = None
        self.assertEqual(e.render((6,)).text, [b"?     "])

    def test_invalid_placeholder_raises_on_assignment(self) -> None:
        with self.assertRaises(urwid.TagMarkupException):
            urwid.Edit("? ", placeholder=5)
        with self.assertRaises(UnicodeError):
            urwid.Edit(b"? ", b"", placeholder="h\xe9")
        e = urwid.Edit("? ", placeholder="name")
        with self.assertRaises(urwid.TagMarkupException):
            e.placeholder = 5
        self.assertEqual(e.render((8,)).text, [b"? name  "])

    def test_repr(self) -> None:
        self.assertEqual(
            repr(urwid.Edit("? ", placeholder="name")),
            "<Edit selectable flow widget '' caption='? ' edit_pos=0 placeholder='name'>",
        )


class EditValidatorTest(unittest.TestCase):
    ERROR = urwid.ValidationMessage(urwid.Severity.ERROR, "bad")
    WARNING = urwid.ValidationMessage(urwid.Severity.WARNING, "odd")
    INFO = urwid.ValidationMessage(urwid.Severity.INFO, "note")

    def test_return_shapes(self) -> None:
        cases = [
            ("None", None, ()),
            ("empty iterable", [], ()),
            ("str", "bad", (self.ERROR,)),
            ("message", self.WARNING, (self.WARNING,)),
            ("list", [self.INFO, self.ERROR], (self.INFO, self.ERROR)),
            ("generator", (m for m in [self.WARNING]), (self.WARNING,)),
        ]
        for label, result, expected in cases:
            with self.subTest(label):
                e = urwid.Edit(validator=lambda _text, result=result: result)
                self.assertEqual(e.validation, expected)

    def test_wrong_return_type_raises(self) -> None:
        for label, result in (
            ("int", 1),
            ("bytes", b"bad"),
            ("str among messages", [self.ERROR, "bad"]),
            ("severity not a Severity", urwid.ValidationMessage("bad", "m")),
            ("int severity among messages", [urwid.ValidationMessage(3, "m")]),
        ):
            with self.subTest(label), self.assertRaises(TypeError):
                urwid.Edit(validator=lambda _text, result=result: result)
        e = urwid.Edit(validator=lambda text: 1 if text else None)
        with self.assertRaises(TypeError):
            e.set_edit_text("x")
        self.assertEqual(e.edit_text, "x")
        self.assertEqual(e.validation, ())

    def test_severity_is_worst(self) -> None:
        severity = urwid.Severity
        self.assertEqual(
            [severity.DEBUG, severity.INFO, severity.WARNING, severity.ERROR, severity.CRITICAL],
            sorted(severity),
        )
        self.assertEqual((1, 2, 3), (severity.INFO, severity.WARNING, severity.ERROR))
        e = urwid.Edit(validator=lambda _text: [self.INFO, self.ERROR, self.WARNING])
        self.assertIs(e.severity, severity.ERROR)
        self.assertIsNone(urwid.Edit().severity)
        debug = urwid.ValidationMessage(severity.DEBUG, "trace")
        e = urwid.Edit(validator=lambda _text: debug)
        self.assertEqual(e.validation, (debug,))
        self.assertIs(e.severity, severity.DEBUG)
        critical = urwid.ValidationMessage(severity.CRITICAL, "fatal")
        e = urwid.Edit(validator=lambda _text: [debug, critical, self.ERROR])
        self.assertIs(e.severity, severity.CRITICAL)

    def test_called_once_per_change(self) -> None:
        validator = mock.Mock(return_value=None)
        e = urwid.Edit("", "a", validator=validator)
        validator.assert_called_once_with("a")
        validator.reset_mock()
        e.keypress((10,), "b")
        e.keypress((10,), "backspace")
        e.insert_text("c")
        e.set_edit_text("d")
        self.assertEqual([c.args for c in validator.call_args_list], [("ab",), ("a",), ("ac",), ("d",)])
        e.render((10,))
        e.keypress((10,), "left")
        self.assertEqual(validator.call_count, 4)

    def test_signal_only_on_change(self) -> None:
        e = urwid.Edit(validator=lambda text: None if text.isdigit() else "bad")
        seen = []
        urwid.connect_signal(e, "validation", lambda _w, old, new: seen.append((old, new)))
        e.set_edit_text("x")
        self.assertEqual(seen, [])
        e.set_edit_text("1")
        e.set_edit_text("12")
        self.assertEqual(seen, [((self.ERROR,), ())])

    def test_validate_reruns(self) -> None:
        limit = [10]
        e = urwid.Edit("", "5", validator=lambda text: None if int(text) < limit[0] else "too big")
        self.assertEqual(e.validation, ())
        limit[0] = 3
        self.assertEqual(e.validation, ())
        self.assertEqual(e.validate(), (urwid.ValidationMessage(urwid.Severity.ERROR, "too big"),))
        self.assertEqual(e.validation, e.validate())

    def test_validate_returns_value_left_by_handler(self) -> None:
        """A "validation" handler that changes the text leaves the result of its own change."""
        strict = [False]
        e = urwid.Edit("", "x", validator=lambda text: "bad" if strict[0] and text == "x" else None)
        urwid.connect_signal(e, "validation", lambda w, _old, new: new and w.set_edit_text("fixed"))
        strict[0] = True
        self.assertEqual(e.validate(), ())
        self.assertEqual(e.edit_text, "fixed")
        self.assertEqual(e.validation, ())

    def test_result_for_a_replaced_state_is_discarded(self) -> None:
        """A validator that changes the text or replaces itself leaves the result its nested change stored."""

        def change_text(e: urwid.Edit, text: str) -> str | None:
            if text == "b":
                e.set_edit_text("c")
                return "bad"
            return None

        def replace_validator(e: urwid.Edit, text: str) -> str | None:
            if text == "b":
                e.validator = replacement
                return "bad"
            return None

        def replace_validator_wrong_type(e: urwid.Edit, text: str) -> int | None:
            if text == "b":
                e.validator = replacement
                return 1
            return None

        def replacement(_text: str) -> None:
            return None

        for label, validator, assign_last, edit_text, installed in (
            ("text changed", change_text, False, "c", None),
            ("validator replaced", replace_validator, False, "b", replacement),
            ("validator replaced on assignment", replace_validator_wrong_type, True, "b", replacement),
        ):
            with self.subTest(label):
                e = urwid.Edit("", "b" if assign_last else "")
                seen: list[tuple[urwid.ValidationMessage, ...]] = []
                urwid.connect_signal(e, "validation", lambda _w, _old, new, seen=seen: seen.append(new))
                e.validator = lambda text, e=e, validator=validator: validator(e, text)
                if not assign_last:
                    e.set_edit_text("b")
                self.assertEqual(e.edit_text, edit_text)
                self.assertEqual(e.validation, ())
                self.assertEqual(seen, [])
                if installed is not None:
                    self.assertIs(e.validator, installed)

    def test_subclass_validate_is_not_called(self) -> None:
        """A subclass's own validate(), which may need attributes set after __init__, is never called by Edit."""

        class OwnValidate(urwid.Edit):
            def __init__(self) -> None:
                super().__init__("> ", validator=lambda text: None if text else "empty")
                self.required = True
                self.own_calls = 0

            def validate(self) -> bool:  # type: ignore[override]
                self.own_calls += 1
                return not self.required or bool(self.edit_text)

        e = OwnValidate()
        e.set_edit_text("x")
        e.validator = lambda text: "bad"
        self.assertEqual(e.validation, (urwid.ValidationMessage(urwid.Severity.ERROR, "bad"),))
        self.assertEqual(e.own_calls, 0)
        self.assertTrue(e.validate())
        self.assertEqual(urwid.Edit.validate(e), (urwid.ValidationMessage(urwid.Severity.ERROR, "bad"),))

    def test_failing_validator_is_not_installed(self) -> None:
        e = urwid.Edit("", "x", validator=lambda _text: self.WARNING)
        with self.assertRaises(TypeError):
            e.validator = lambda _text: 1
        self.assertEqual(e.validation, (self.WARNING,))
        e.set_edit_text("y")
        self.assertEqual(e.validation, (self.WARNING,))

    def test_validator_assigned_later(self) -> None:
        e = urwid.Edit("", "x")
        self.assertIsNone(e.validator)
        e.validator = lambda _text: self.WARNING
        self.assertEqual(e.validation, (self.WARNING,))
        e.validator = None
        self.assertEqual(e.validation, ())

    def test_colour_by_severity(self) -> None:
        validation_attr = {urwid.Severity.WARNING: "warn", urwid.Severity.ERROR: "err"}
        validation_focus_attr = {urwid.Severity.ERROR: "err focus"}
        cases = [
            ("no finding", None, False, None),
            ("info has no map", self.INFO, False, None),
            ("warning", self.WARNING, False, "warn"),
            ("warning focused falls back", self.WARNING, True, "warn"),
            ("error", self.ERROR, False, "err"),
            ("error focused", self.ERROR, True, "err focus"),
            ("worst message decides", [self.WARNING, self.ERROR], False, "err"),
        ]
        for label, result, focus, attr in cases:
            with self.subTest(label):
                e = urwid.Edit(
                    "",
                    "ab",
                    validator=lambda _text, result=result: result,
                    validation_attr=validation_attr,
                    validation_focus_attr=validation_focus_attr,
                )
                self.assertEqual(next(iter(e.render((4,), focus=focus).content())), [(attr, None, b"ab  ")])

    def test_map_over_caption_markup(self) -> None:
        """A single attribute keeps the caption's own attribute, layered over it."""
        e = urwid.Edit(("cap", "? "), "x", validator=lambda _text: "bad", validation_attr={urwid.Severity.ERROR: "err"})
        self.assertEqual(
            next(iter(e.render((4,)).content())),
            [(urwid.LayeredAttr("cap", "err"), None, b"? "), ("err", None, b"x ")],
        )
        e.validation_attr = {urwid.Severity.ERROR: {None: "err", "cap": "err cap"}}
        self.assertEqual(
            next(iter(e.render((4,)).content())),
            [(urwid.LayeredAttr("err cap", "err"), None, b"? "), ("err", None, b"x ")],
        )
        self.assertEqual(e.validation_attr, {urwid.Severity.ERROR: {None: "err", "cap": "err cap"}})
        e.validation_attr = None
        self.assertEqual(next(iter(e.render((4,)).content())), [("cap", None, b"? "), (None, None, b"x ")])

    def test_cursor_kept_with_map(self) -> None:
        e = urwid.Edit("? ", "ab", validator=lambda _text: "bad", validation_focus_attr={urwid.Severity.ERROR: "err"})
        self.assertEqual(e.render((6,), focus=True).cursor, (4, 0))

    def test_render_follows_validation_change(self) -> None:
        e = urwid.Edit(validator=lambda text: None if text else "empty", validation_attr={urwid.Severity.ERROR: "err"})
        self.assertEqual(next(iter(e.render((2,)).content())), [("err", None, b"  ")])
        e.keypress((2,), "x")
        self.assertEqual(next(iter(e.render((2,)).content())), [(None, None, b"x ")])
        e.validation_focus_attr = {urwid.Severity.ERROR: "err focus"}
        e.keypress((2,), "backspace")
        self.assertEqual(next(iter(e.render((2,), focus=True).content())), [("err focus", None, b"  ")])
        self.assertEqual(e.validation_focus_attr, {urwid.Severity.ERROR: {None: "err focus"}})

    def test_placeholder_coloured(self) -> None:
        e = urwid.Edit(
            placeholder="hint",
            validator=lambda text: None if text else "empty",
            validation_attr={urwid.Severity.ERROR: "err"},
        )
        self.assertEqual(next(iter(e.render((6,)).content())), [("err", None, b"hint  ")])

    def test_masked_text_is_validated(self) -> None:
        validator = mock.Mock(return_value=None)
        urwid.Edit("", "secret", mask="*", validator=validator)
        validator.assert_called_once_with("secret")

    def test_int_edit(self) -> None:
        e = urwid.IntEdit("", 5)
        e.validator = lambda text: None if int(text or 0) < 10 else "too big"
        e.keypress((10,), "0")
        self.assertEqual(e.edit_text, "50")
        self.assertEqual(e.validation, (urwid.ValidationMessage(urwid.Severity.ERROR, "too big"),))


def mark_upper(text: str | bytes) -> list[tuple[str, str | bytes] | str | bytes]:
    """Return *text* as markup with each run of capital letters in the attribute ``"up"``."""
    pattern = re.compile(r"([A-Z]+)") if isinstance(text, str) else re.compile(rb"([A-Z]+)")
    return [("up", part) if index % 2 else part for index, part in enumerate(pattern.split(text)) if part]


class CountingHighlighter:
    """Highlighter that marks capital letters and records the text and validation of each call."""

    def __init__(self) -> None:
        self.edit: urwid.Edit | None = None
        self.calls: list[tuple[str, tuple[urwid.ValidationMessage, ...] | None]] = []

    def __call__(self, text: str) -> list[tuple[str, str | bytes] | str | bytes]:
        self.calls.append((text, None if self.edit is None else self.edit.validation))
        return mark_upper(text)


class ShownControlEdit(urwid.Edit):
    """Edit that shows the zero-width BEL character as a visible ``?`` of the same length."""

    def get_text(self) -> tuple[str | bytes, list[tuple[typing.Hashable, int]]]:
        text, attrib = super().get_text()
        return typing.cast("str", text).replace("\x07", "?"), attrib


class EditHighlightTest(unittest.TestCase):
    ERROR = urwid.ValidationMessage(urwid.Severity.ERROR, "bad")

    def test_render_content(self) -> None:
        cases = [
            (
                "plain caption",
                urwid.Edit("> ", "aBc", highlighter=mark_upper),
                (6,),
                [[(None, None, b"> a"), ("up", None, b"B"), (None, None, b"c ")]],
            ),
            (
                "styled caption",
                urwid.Edit([("cap", ">"), " "], "aBc", highlighter=mark_upper),
                (6,),
                [[("cap", None, b">"), (None, None, b" a"), ("up", None, b"B"), (None, None, b"c ")]],
            ),
            (
                "multiline",
                urwid.Edit("", "aB\nCd", multiline=True, highlighter=mark_upper),
                (3,),
                [
                    [(None, None, b"a"), ("up", None, b"B"), (None, None, b" ")],
                    [("up", None, b"C"), (None, None, b"d ")],
                ],
            ),
            (
                "wrapped",
                urwid.Edit("", "aBCd", wrap="any", highlighter=mark_upper),
                (2,),
                [[(None, None, b"a"), ("up", None, b"B")], [("up", None, b"C"), (None, None, b"d")]],
            ),
            (
                "right aligned",
                urwid.Edit("", "aB", align="right", highlighter=mark_upper),
                (4,),
                [[(None, None, b"  a"), ("up", None, b"B")]],
            ),
            (
                "bytes",
                urwid.Edit(b"> ", b"aBc", highlighter=mark_upper),
                (6,),
                [[(None, None, b"> a"), ("up", None, b"B"), (None, None, b"c ")]],
            ),
        ]
        for label, e, size, expected in cases:
            with self.subTest(label):
                self.assertEqual(list(e.render(size).content()), expected)

    def test_caption_attributes_padded_only_before_edit_runs(self) -> None:
        def deferred_attrib(e: urwid.Edit) -> list[tuple[typing.Hashable, int]]:
            seen: list[list[tuple[typing.Hashable, int]]] = []
            urwid.connect_signal(e, "postchange", lambda w, _old: seen.append(w.attrib))
            e.set_edit_text("xY")
            return seen[0]

        for caption, plain, padded in (
            ("? ", [], [(None, 2), (None, 1), ("up", 1)]),
            ([("cap", "?"), " "], [("cap", 1)], [("cap", 1), (None, 1), (None, 1), ("up", 1)]),
        ):
            with self.subTest(caption=caption):
                self.assertEqual(urwid.Edit(caption, "xY").attrib, plain)
                self.assertEqual(urwid.Edit(caption, "xY", highlighter=mark_upper, mask="*").attrib, plain)
                self.assertEqual(urwid.Edit(caption, "", highlighter=mark_upper).attrib, plain)
                self.assertEqual(deferred_attrib(urwid.Edit(caption, "", highlighter=mark_upper)), plain)
                self.assertEqual(urwid.Edit(caption, "xY", highlighter=mark_upper).attrib, padded)
                self.assertEqual(urwid.Edit(caption, "xY", highlighter=mark_upper).get_text(), (f"{'? '}xY", padded))

    def test_get_text_override_drives_layout_and_cursor(self) -> None:
        """An override that shows a zero-width character as a visible one moves the cursor and the wrapping."""
        for label, kwargs, runs in (
            ("no runs", {}, None),
            ("highlighter", {"highlighter": mark_upper}, None),
            ("edit_attrib", {}, [(None, 2), ("up", 1)]),
        ):
            with self.subTest(label):
                e = ShownControlEdit("", "a\x07B", edit_pos=2, **kwargs)
                if runs is not None:
                    e.edit_attrib = runs
                coloured = label != "no runs"
                self.assertEqual(e.get_text(), ("a?B", [(None, 2), ("up", 1)] if coloured else []))
                self.assertEqual(e.get_cursor_coords((10,)), (2, 0))
                self.assertEqual(e.position_coords(10, 3), (3, 0))
                canvas = e.render((10,), focus=True)
                self.assertEqual(canvas.cursor, (2, 0))
                expected_row = (
                    [(None, None, b"a?"), ("up", None, b"B"), (None, None, b"       ")]
                    if coloured
                    else [(None, None, b"a?B       ")]
                )
                self.assertEqual(next(iter(canvas.content())), expected_row)
                self.assertEqual(e.rows((2,)), 2)
                self.assertEqual(e.render((2,)).text, [b"a?", b"B "])
                self.assertTrue(e.mouse_event((10,), "mouse press", 1, 1, 0, focus=True))
                self.assertEqual(e.edit_pos, 1)
                self.assertTrue(e.mouse_event((10,), "mouse press", 1, 3, 0, focus=True))
                self.assertEqual(e.edit_pos, 3)

    def test_highlighter_called_once_per_text_and_validation(self) -> None:
        highlighter = CountingHighlighter()
        e = urwid.Edit("", "aB", highlighter=highlighter)
        e.get_cursor_coords((5,))
        e.position_coords(5, 1)
        e.rows((3,))
        e.move_cursor_to_coords((5,), 0, 0)
        e.keypress((5,), "end")
        self.assertEqual(highlighter.calls, [])
        e.render((5,))
        e.render((5,), focus=True)
        e.render((8,), focus=True)
        e.keypress((5,), "left")
        e.render((5,), focus=True)
        e.get_cursor_coords((5,))
        e.position_coords(5, 1)
        e.rows((3,))
        e.move_cursor_to_coords((5,), 0, 0)
        self.assertEqual(highlighter.calls, [("aB", None)])
        e.keypress((5,), "C")
        e.render((5,))
        self.assertEqual([text for text, _validation in highlighter.calls], ["aB", "CaB"])
        e.rehighlight()
        e.render((5,))
        self.assertEqual(len(highlighter.calls), 3)
        replacement = CountingHighlighter()
        e.highlighter = replacement
        e.render((5,))
        self.assertEqual((len(highlighter.calls), replacement.calls), (3, [("CaB", None)]))

    def test_highlighter_called_again_for_new_validation(self) -> None:
        strict = [False]
        highlighter = CountingHighlighter()
        e = urwid.Edit("", "aB", validator=lambda _text: "bad" if strict[0] else None, highlighter=highlighter)
        highlighter.edit = e
        e.render((5,))
        e.validate()
        e.render((5,), focus=True)
        strict[0] = True
        e.validate()
        e.render((5,))
        self.assertEqual(highlighter.calls, [("aB", ()), ("aB", (self.ERROR,))])

    def test_highlighter_not_called_for_masked_or_empty_text(self) -> None:
        for label, kwargs in (("masked", {"edit_text": "aB", "mask": "*"}), ("empty", {"edit_text": ""})):
            with self.subTest(label):
                highlighter = CountingHighlighter()
                e = urwid.Edit("> ", highlighter=highlighter, **kwargs)
                e.render((5,), focus=True)
                self.assertEqual(e.attrib, [])
                self.assertEqual(highlighter.calls, [])

    def test_highlighter_markup_of_another_text_raises(self) -> None:
        e = urwid.Edit("", "ab", highlighter=lambda text: text.upper())
        with self.assertRaises(ValueError):
            e.render((5,))

    def test_signal_order(self) -> None:
        """Handlers see the old runs, then none until the new text is validated, then the new runs."""
        highlighter = CountingHighlighter()
        e = urwid.Edit("", "aB", validator=lambda text: "bad" if "X" in text else None, highlighter=highlighter)
        highlighter.edit = e
        seen: list[tuple[str, list[tuple[typing.Hashable, int]], int]] = []
        for name in ("change", "edit_pos", "postchange", "validation"):
            urwid.connect_signal(
                e,
                name,
                lambda w, *_args, name=name: seen.append(
                    (name, w.attrib, len(highlighter.calls), w.render((6,)).text[0])
                ),
            )
        e.set_edit_text("aBX", edit_pos=3)
        self.assertEqual(
            seen,
            [
                ("change", [(None, 1), ("up", 1)], 1, b"aB    "),
                ("edit_pos", [], 1, b"aBX   "),
                ("postchange", [], 1, b"aBX   "),
                ("validation", [(None, 1), ("up", 2)], 2, b"aBX   "),
            ],
        )
        self.assertEqual(highlighter.calls, [("aB", ()), ("aBX", (self.ERROR,))])
        seen.clear()
        e.set_edit_text("aBX")
        e.render((6,))
        self.assertEqual(len(highlighter.calls), 2)

    def test_nested_edit_sees_current_validation(self) -> None:
        for signal in ("postchange", "validation"):
            with self.subTest(signal):
                highlighter = CountingHighlighter()
                e = urwid.Edit("", "", validator=lambda text: "bad" if text == "aB" else None, highlighter=highlighter)
                highlighter.edit = e
                urwid.connect_signal(
                    e, signal, lambda w, *_args: w.edit_text == "aB" and (w.render((6,)), w.set_edit_text("aBC"))
                )
                e.set_edit_text("aB")
                e.render((6,))
                self.assertEqual(e.edit_text, "aBC")
                self.assertEqual(e.attrib, [(None, 1), ("up", 2)])
                for text, validation in highlighter.calls:
                    self.assertEqual(validation, (self.ERROR,) if text == "aB" else ())

    def test_failure_leaves_highlighter_deferred(self) -> None:
        for label in ("validator raises", "postchange raises"):
            with self.subTest(label):
                fail = [True]

                def validator(text: str, fail: list[bool] = fail, label: str = label) -> None:
                    if label == "validator raises" and text == "aB" and fail[0]:
                        raise RuntimeError("validator failed")

                e = urwid.Edit("", "a", validator=validator, highlighter=mark_upper)
                rendered: list[urwid.Canvas] = []

                def postchange(w: urwid.Edit, _old: str, label: str = label) -> None:
                    rendered.append(w.render((4,)))
                    if label == "postchange raises" and fail[0]:
                        raise RuntimeError("handler failed")

                urwid.connect_signal(e, "postchange", postchange)
                with self.assertRaises(RuntimeError):
                    e.set_edit_text("aB")
                self.assertEqual(e.edit_text, "aB")
                self.assertEqual(e.attrib, [])
                self.assertIs(e.render((4,)), rendered[0])
                fail[0] = False
                self.assertEqual(e.validate(), ())
                self.assertEqual(e.attrib, [(None, 1), ("up", 1)])
                canvas = e.render((4,))
                self.assertIsNot(canvas, rendered[0])
                self.assertEqual(
                    next(iter(canvas.content())), [(None, None, b"a"), ("up", None, b"B"), (None, None, b"  ")]
                )

    def test_highlighter_never_sees_masked_text_on_construction(self) -> None:
        class ReadingEdit(urwid.Edit):
            def set_edit_text(self, text: str, *, edit_pos: int | None = None) -> None:
                super().set_edit_text(text, edit_pos=edit_pos)
                self.get_text()

        highlighter = CountingHighlighter()
        e = ReadingEdit("", "secret", mask="*", highlighter=highlighter)
        e.render((8,))
        e.set_edit_text("Other")
        self.assertEqual(highlighter.calls, [])

    def test_edit_attrib(self) -> None:
        e = urwid.Edit("", "abc")
        runs = [("a", 1), ("b", 2)]
        e.edit_attrib = runs
        runs.append(("c", 1))
        self.assertEqual(e.edit_attrib, [("a", 1), ("b", 2)])
        e.edit_attrib.append(("c", 1))
        self.assertEqual(e.edit_attrib, [("a", 1), ("b", 2)])
        self.assertEqual(e.attrib, [("a", 1), ("b", 2)])
        e.edit_attrib = [("a", 1)]
        self.assertEqual(e.attrib, [("a", 1)])
        e.edit_attrib = []
        self.assertEqual(e.attrib, [])
        for label, bad in (("negative", [("a", -1)]), ("too long", [("a", 2), ("b", 2)])):
            with self.subTest(label), self.assertRaises(ValueError):
                e.edit_attrib = bad
        b = urwid.Edit(b"", b"\xc3\xa9")
        b.edit_attrib = [("a", 2)]
        self.assertEqual(b.attrib, [("a", 2)])
        s = urwid.Edit("", "é")
        with self.assertRaises(ValueError):
            s.edit_attrib = [("a", 2)]

    def test_edit_attrib_follows_text(self) -> None:
        e = urwid.Edit("", "abc", highlighter=mark_upper)
        e.edit_attrib = [("x", 3)]
        e.set_edit_text("abc")
        self.assertEqual(e.edit_attrib, [("x", 3)])
        e.set_edit_text("aBc")
        self.assertEqual(e.edit_attrib, [])
        self.assertEqual(e.attrib, [(None, 1), ("up", 1)])
        e.edit_attrib = [(None, 3)]
        self.assertEqual(e.attrib, [(None, 3)])

    def test_edit_attrib_set_for_the_new_text(self) -> None:
        class RunsEdit(urwid.Edit):
            def set_edit_text(self, text: str, *, edit_pos: int | None = None) -> None:
                super().set_edit_text(text, edit_pos=edit_pos)
                self.edit_attrib = [("set", len(self.edit_text))]

        from_handler = urwid.Edit("", "a")
        urwid.connect_signal(from_handler, "postchange", lambda w, _old: setattr(w, "edit_attrib", [("set", 2)]))
        for e in (RunsEdit("", "a"), from_handler):
            with self.subTest(type(e).__name__):
                e.set_edit_text("bc")
                self.assertEqual(e.edit_attrib, [("set", 2)])
                self.assertEqual(e.attrib, [("set", 2)])

    def test_colouring_excludes_validation_colours(self) -> None:
        attr = {urwid.Severity.ERROR: "err"}

        def highlighted() -> urwid.Edit:
            return urwid.Edit("", "ab", highlighter=mark_upper)

        def with_runs() -> urwid.Edit:
            e = urwid.Edit("", "ab")
            e.edit_attrib = [("a", 1)]
            return e

        def validation_coloured() -> urwid.Edit:
            return urwid.Edit("", "ab", validation_attr=attr)

        def focus_coloured() -> urwid.Edit:
            return urwid.Edit("", "ab", validation_focus_attr=attr)

        cases: list[tuple[str, typing.Callable[[], object]]] = [
            ("constructor, validation_attr", lambda: urwid.Edit(highlighter=mark_upper, validation_attr=attr)),
            (
                "constructor, validation_focus_attr",
                lambda: urwid.Edit(highlighter=mark_upper, validation_focus_attr=attr),
            ),
            ("highlighter after validation_attr", lambda: setattr(validation_coloured(), "highlighter", mark_upper)),
            ("highlighter after validation_focus_attr", lambda: setattr(focus_coloured(), "highlighter", mark_upper)),
            ("edit_attrib after validation_attr", lambda: setattr(validation_coloured(), "edit_attrib", [("a", 1)])),
            ("edit_attrib after validation_focus_attr", lambda: setattr(focus_coloured(), "edit_attrib", [("a", 1)])),
            ("validation_attr after highlighter", lambda: setattr(highlighted(), "validation_attr", attr)),
            ("validation_focus_attr after highlighter", lambda: setattr(highlighted(), "validation_focus_attr", attr)),
            ("validation_attr after edit_attrib", lambda: setattr(with_runs(), "validation_attr", attr)),
            ("validation_focus_attr after edit_attrib", lambda: setattr(with_runs(), "validation_focus_attr", attr)),
        ]
        for label, make in cases:
            with self.subTest(label), self.assertRaises(ValueError):
                make()
        e = highlighted()
        e.validation_attr = {}
        e.highlighter = None
        e.validation_attr = attr
        e.edit_attrib = []
        self.assertEqual(e.validation_attr, {urwid.Severity.ERROR: {None: "err"}})


class DelayedLexerTest(unittest.TestCase):
    """The delayed lexer pattern of the manual: a result applies only to the text it was made for."""

    def setUp(self) -> None:
        self.alarms: list[typing.Callable[[], None]] = []
        self.e = urwid.Edit("", "")

        def postchange(w: urwid.Edit, _old: str) -> None:
            text = w.edit_text
            self.alarms.append(lambda: self.apply(text))

        urwid.connect_signal(self.e, "postchange", postchange)

    def apply(self, text: str) -> None:
        if self.e.edit_text == text:
            self.e.edit_attrib = [(attr, 1) for attr in text]

    def run_alarms(self) -> None:
        alarms, self.alarms = self.alarms, []
        for alarm in alarms:
            alarm()

    def test_text_changed_before_alarm(self) -> None:
        """Only the alarm queued for the current text applies its runs, also when the text got shorter."""
        self.e.set_edit_text("abc")
        self.e.set_edit_text("ab")
        self.run_alarms()
        self.assertEqual(self.e.edit_attrib, [("a", 1), ("b", 1)])

    def test_raising_edit_pos_handler(self) -> None:
        """A result queued for the previous text is not applied to a text whose "postchange" never came."""
        self.e.set_edit_text("aa")
        self.run_alarms()
        self.e.set_edit_text("bb")

        def fail(_w: urwid.Edit, _old: int, _new: int) -> None:
            raise RuntimeError("edit_pos handler failed")

        urwid.connect_signal(self.e, "edit_pos", fail)
        queued = list(self.alarms)
        with self.assertRaises(RuntimeError):
            self.e.set_edit_text("cc", edit_pos=1)
        self.assertEqual(self.alarms, queued)
        self.run_alarms()
        self.assertEqual(self.e.edit_text, "cc")
        self.assertEqual(self.e.edit_attrib, [])

    def test_nested_edit_from_change(self) -> None:
        """A result queued by an edit nested in "change" is not applied to the outer edit's text."""
        self.e.set_edit_text("aa")
        self.run_alarms()

        def nested(w: urwid.Edit, text: str) -> None:
            if text == "bb":
                w.set_edit_text("cc")

        urwid.connect_signal(self.e, "change", nested)

        def fail(_w: urwid.Edit, _old: int, _new: int) -> None:
            raise RuntimeError("edit_pos handler failed")

        urwid.connect_signal(self.e, "edit_pos", fail)
        with self.assertRaises(RuntimeError):
            self.e.set_edit_text("bb", edit_pos=1)
        self.run_alarms()
        self.assertEqual(self.e.edit_text, "bb")
        self.assertEqual(self.e.edit_attrib, [])


def complete_words(text: str, pos: int) -> list[tuple[str, int]]:
    """Complete the word before the cursor from a fixed list, keeping the text after the cursor."""
    start = max(text.rfind(" ", 0, pos) + 1, 0)
    return [
        (text[:start] + word + text[pos:], start + len(word))
        for word in ("alpha", "alpine", "beta")
        if word.startswith(text[start:pos])
    ]


class NoAlpineEdit(urwid.Edit):
    """Edit that refuses the text "alpine", as a subclass with an input pattern refuses text."""

    def set_edit_text(self, text: str, *, edit_pos: int | None = None) -> None:
        if text == "alpine":
            raise ValueError(text)
        super().set_edit_text(text, edit_pos=edit_pos)


class EditCompleterTest(unittest.TestCase):
    def test_cycle_forward_and_back_with_wrap(self) -> None:
        e = urwid.Edit("", "x al y", edit_pos=4, text_completer=complete_words)
        seen = []
        for key in ("tab", "tab", "tab", "tab", "shift tab", "shift tab"):
            self.assertIsNone(e.keypress((20,), key))
            seen.append((e.edit_text, e.edit_pos))
        self.assertEqual(
            seen,
            [
                ("x alpha y", 7),
                ("x alpine y", 8),
                ("x al y", 4),
                ("x alpha y", 7),
                ("x al y", 4),
                ("x alpine y", 8),
            ],
        )
        self.assertEqual(e.completion_cycle, ((("x al y", 4), ("x alpha y", 7), ("x alpine y", 8)), 2))

    def test_previous_first_takes_last_candidate(self) -> None:
        e = urwid.Edit("", "al", text_completer=complete_words)
        e.keypress((20,), "shift tab")
        self.assertEqual(e.edit_text, "alpine")

    def test_completer_called_once_per_cycle(self) -> None:
        completer = mock.Mock(side_effect=complete_words)
        e = urwid.Edit("", "al", text_completer=completer)
        for _key in range(5):
            e.keypress((20,), "tab")
        completer.assert_called_once_with("al", 2)

    def test_nothing_to_complete_returns_key(self) -> None:
        e = urwid.Edit("", "zz", text_completer=complete_words)
        self.assertEqual(e.keypress((20,), "tab"), "tab")
        self.assertEqual(e.keypress((20,), "shift tab"), "shift tab")
        self.assertEqual(e.edit_text, "zz")
        self.assertIsNone(e.completion_cycle)

    def test_without_completer_tab_returned(self) -> None:
        self.assertEqual(urwid.Edit("", "al").keypress((20,), "tab"), "tab")

    def test_single_candidate_starts_no_cycle(self) -> None:
        """The next key asks the completer again, and a candidate equal to the current text is left out."""
        completer = mock.Mock(side_effect=complete_words)
        e = urwid.Edit("", "be", text_completer=completer)
        seen = []
        urwid.connect_signal(e, "completion_cycle", lambda _w, completions: seen.append(completions))
        self.assertIsNone(e.keypress((20,), "tab"))
        self.assertEqual((e.edit_text, e.edit_pos), ("beta", 4))
        self.assertIsNone(e.completion_cycle)
        self.assertEqual(e.keypress((20,), "tab"), "tab")
        self.assertEqual(e.edit_text, "beta")
        self.assertEqual(completer.call_args_list, [mock.call("be", 2), mock.call("beta", 4)])
        self.assertEqual(seen, [])

    def test_candidate_position_clipped_before_comparing(self) -> None:
        """A candidate past the end of its text is the text with the cursor at its end, so Tab is returned next."""
        e = urwid.Edit("", "be", text_completer=lambda text, _pos: [("beta", 10)])
        self.assertIsNone(e.keypress((20,), "tab"))
        self.assertEqual((e.edit_text, e.edit_pos), ("beta", 4))
        self.assertEqual(e.keypress((20,), "tab"), "tab")

    def test_prefix_then_cycle(self) -> None:
        """A completer that returns the common prefix first inserts it, then cycles through the matches."""

        def complete_prefix(text: str, pos: int) -> list[tuple[str, int]]:
            matches = [word for word in ("alpha", "alpine", "beta") if word.startswith(text[:pos])]
            prefix = matches[0] if matches else ""
            for word in matches:
                while not word.startswith(prefix):
                    prefix = prefix[:-1]
            if len(matches) > 1 and len(prefix) > pos:
                return [(prefix, len(prefix))]
            return [(word, len(word)) for word in matches]

        e = urwid.Edit("", "a", text_completer=complete_prefix)
        seen = []
        for _key in range(4):
            self.assertIsNone(e.keypress((20,), "tab"))
            seen.append(e.edit_text)
        self.assertEqual(seen, ["alp", "alpha", "alpine", "alp"])

    def test_other_key_ends_cycle(self) -> None:
        completer = mock.Mock(side_effect=complete_words)
        e = urwid.Edit("", "al", text_completer=completer)
        seen = []
        urwid.connect_signal(e, "completion_cycle", lambda _w, completions: seen.append(completions))
        e.keypress((20,), "tab")
        self.assertEqual(e.keypress((20,), "f5"), "f5")
        self.assertIsNone(e.completion_cycle)
        self.assertEqual(seen, [((("al", 2), ("alpha", 5), ("alpine", 6)), 1), None])
        e.keypress((20,), "tab")
        self.assertEqual(e.edit_text, "alpha")
        self.assertEqual(completer.call_args_list, [mock.call("al", 2), mock.call("alpha", 5)])

    def test_change_from_elsewhere_ends_cycle(self) -> None:
        """The cycle ends at once, with a signal, and the next key asks the completer again."""
        e = urwid.Edit("", "al", text_completer=complete_words)
        seen = []
        urwid.connect_signal(e, "completion_cycle", lambda _w, completions: seen.append(completions))
        e.keypress((20,), "tab")
        e.set_edit_text("alp")
        self.assertIsNone(e.completion_cycle)
        self.assertEqual(seen[-1:], [None])
        e.keypress((20,), "tab")
        e.mouse_event((20,), "mouse press", 1, 1, 0, True)
        self.assertIsNone(e.completion_cycle)
        self.assertEqual(e.edit_pos, 1)
        e.set_edit_text("alp")
        e.set_edit_pos(3)
        e.keypress((20,), "tab")
        self.assertEqual(e.edit_text, "alpha")
        self.assertEqual(e.completion_cycle, ((("alp", 3), ("alpha", 5), ("alpine", 6)), 1))

    def test_cycle_ends_after_postchange_and_validation(self) -> None:
        """A change through set_edit_text() ends the cycle once "postchange" and validation are done."""
        e = urwid.Edit("", "al", text_completer=complete_words, validator=lambda text: None if text != "x" else "bad")
        e.keypress((20,), "tab")
        seen = []
        urwid.connect_signal(e, "postchange", lambda _w, _old: seen.append("postchange"))
        urwid.connect_signal(e, "completion_cycle", lambda w, completions: seen.append((completions, w.validation)))
        e.set_edit_text("x")
        self.assertEqual(seen, ["postchange", (None, (urwid.ValidationMessage(urwid.Severity.ERROR, "bad"),))])

    def test_change_without_set_edit_pos_ends_cycle_at_next_key(self) -> None:
        """A subclass that changes the text without set_edit_pos() gets the cycle ended by the next completion key."""
        completer = mock.Mock(side_effect=complete_words)
        e = urwid.Edit("", "al", text_completer=completer)
        e.keypress((20,), "tab")
        e._edit_text, e._edit_pos = "be", 2
        e.keypress((20,), "tab")
        self.assertEqual(e.edit_text, "beta")
        self.assertEqual(completer.call_args_list, [mock.call("al", 2), mock.call("be", 2)])

    def test_allow_tab_completes_by_command_only(self) -> None:
        cm = urwid.CommandMap()
        cm.bind(Command.COMPLETE_NEXT, "ctrl f")
        cm.bind(Command.COMPLETE_PREVIOUS, "ctrl r")
        e = urwid.Edit("", "al", allow_tab=True, text_completer=complete_words)
        e._command_map = cm
        self.assertIsNone(e.keypress((20,), "ctrl r"))
        self.assertEqual(e.edit_text, "alpine")
        self.assertIsNone(e.keypress((20,), "ctrl f"))
        self.assertEqual(e.edit_text, "al")
        self.assertIsNone(e.keypress((20,), "tab"))
        self.assertEqual(e.edit_text, "al      ")
        self.assertEqual(e.keypress((20,), "shift tab"), "shift tab")

    def test_completer_exception_propagates(self) -> None:
        e = urwid.Edit("", "al", text_completer=mock.Mock(side_effect=RuntimeError("boom")))
        with self.assertRaises(RuntimeError):
            e.keypress((20,), "tab")
        self.assertEqual(e.edit_text, "al")

    def test_rejected_candidate_propagates_and_cycle_stays(self) -> None:
        """A refused candidate propagates and is retried."""
        e = NoAlpineEdit("", "al", text_completer=complete_words)
        e.keypress((20,), "tab")
        for _key in range(2):
            with self.assertRaises(ValueError):
                e.keypress((20,), "tab")
            self.assertEqual(e.edit_text, "alpha")
            self.assertEqual(e.completion_cycle, ((("al", 2), ("alpha", 5), ("alpine", 6)), 1))

    def test_rejected_first_candidate_propagates_and_starts_no_cycle(self) -> None:
        """A refused first candidate starts no cycle, so the next key asks the completer again."""
        completer = mock.Mock(return_value=[("alpine", 6), ("alpha", 5)])
        e = NoAlpineEdit("", "al", text_completer=completer)
        for _key in range(2):
            with self.assertRaises(ValueError):
                e.keypress((20,), "tab")
            self.assertEqual((e.edit_text, e.completion_cycle), ("al", None))
        self.assertEqual(completer.call_count, 2)

    def test_candidate_over_max_length(self) -> None:
        e = urwid.Edit("", "al", max_length=5, text_completer=complete_words)
        with self.assertRaises(ValueError):
            e.keypress((20,), "tab")
        self.assertEqual((e.edit_text, e.edit_pos), ("al", 2))
        self.assertIsNone(e.completion_cycle)

    def test_bytes(self) -> None:
        """The completer gets bytes, and str candidates are converted to bytes."""
        completer = mock.Mock(return_value=[("alpha", 5), ("alpine", 6)])
        e = urwid.Edit(b"", b"al", text_completer=completer)
        e.keypress((20,), "tab")
        self.assertEqual(e.edit_text, b"alpha")
        completer.assert_called_once_with(b"al", 2)
        self.assertEqual(e.completion_cycle, (((b"al", 2), (b"alpha", 5), (b"alpine", 6)), 1))

    def test_masked(self) -> None:
        e = urwid.Edit("", "al", mask="*", text_completer=complete_words)
        e.keypress((20,), "tab")
        self.assertEqual(e.edit_text, "alpha")
        self.assertEqual(e.render((8,)).text, [b"*****   "])

    def test_validator_runs_per_step_and_placeholder_returns(self) -> None:
        validator = mock.Mock(return_value=None)
        e = urwid.Edit(
            "",
            placeholder="word",
            validator=validator,
            text_completer=lambda _t, _p: [("beta", 4), ("bet", 3)],
        )
        validator.reset_mock()
        e.keypress((8,), "tab")
        self.assertEqual(e.render((8,)).text, [b"beta    "])
        e.keypress((8,), "tab")
        e.keypress((8,), "tab")
        self.assertEqual(e.render((8,)).text, [b"word    "])
        self.assertEqual([c.args for c in validator.call_args_list], [("beta",), ("bet",), ("",)])

    def test_subclass_completer_attributes_kept(self) -> None:
        """A subclass may keep its own completer and completions attributes, set before Edit.__init__."""

        class OwnCompletion(urwid.Edit):
            def __init__(self, completer: object) -> None:
                self.completer = completer
                self.completions = None
                super().__init__("> ", "al")

        completer = object()
        e = OwnCompletion(completer)
        self.assertIs(e.completer, completer)
        self.assertIsNone(e.text_completer)
        self.assertEqual(e.keypress((20,), "tab"), "tab")

    def test_subclass_complete_method_not_called(self) -> None:
        """A subclass's own _complete(), as urwid-readline and topydo define, is never called by Edit."""

        class OwnComplete(urwid.Edit):
            def _complete(self) -> None:
                raise AssertionError("called by Edit")

        e = OwnComplete("", "al", text_completer=complete_words)
        self.assertIsNone(e.keypress((20,), "tab"))
        self.assertEqual(e.edit_text, "alpha")

    def test_setting_completer_ends_cycle(self) -> None:
        e = urwid.Edit("", "al", text_completer=complete_words)
        e.keypress((20,), "tab")
        e.text_completer = None
        self.assertIsNone(e.completion_cycle)
        self.assertEqual(e.keypress((20,), "tab"), "tab")


READLINE_MAP = urwid.CommandMap()
READLINE_MAP.bind_readline()


def readline_edit(cls: type[urwid.Edit] = urwid.Edit, *args: typing.Any, **kwargs: typing.Any) -> urwid.Edit:
    """Return an edit of *cls* that takes the readline keys."""
    e = cls(*args, **kwargs)
    e._command_map = READLINE_MAP
    return e


def type_keys(e: urwid.Edit, *keys: str) -> None:
    """Send each key to *e* at a width of 20 columns."""
    for key in keys:
        e.keypress((20,), key)


class NoXEdit(urwid.Edit):
    """Edit whose set_edit_text override refuses text containing an x before changing anything."""

    def set_edit_text(self, text: str, *, edit_pos: int | None = None) -> None:
        if "x" in text:
            raise ValueError(text)
        super().set_edit_text(text, edit_pos=edit_pos)


class UpperAfterKeypressEdit(urwid.Edit):
    """Edit that changes the text after the base keypress returns, outside the editing transaction."""

    def keypress(self, size: tuple[int], key: str) -> str | None:  # type: ignore[override]
        unhandled = super().keypress(size, key)
        self.set_edit_text(self.edit_text.upper())
        return unhandled


class EditUndoTest(unittest.TestCase):
    def history(self, e: urwid.Edit) -> tuple[list[tuple[str | bytes, int]], list[tuple[str | bytes, int]]]:
        return list(e._undo_stack), list(e._redo_stack)

    def test_off_by_default(self) -> None:
        """Without a limit nothing is recorded, and the commands return their key."""
        cm = urwid.CommandMap()
        cm.bind(Command.UNDO, "ctrl _")
        cm.bind(Command.REDO, "meta _")
        e = urwid.Edit()
        e._command_map = cm
        type_keys(e, "a", "b")
        self.assertEqual(e.undo_limit, 0)
        self.assertFalse(e.undo())
        self.assertEqual(e.keypress((20,), "ctrl _"), "ctrl _")
        self.assertEqual(e.keypress((20,), "meta _"), "meta _")
        self.assertEqual(e.edit_text, "ab")

    def test_limit_raised_from_zero(self) -> None:
        """Typing after the limit is raised from 0 is a step of its own, not the continuation of an unrecorded run."""
        e = urwid.Edit()
        type_keys(e, "a", "b")
        e.undo_limit = 10
        type_keys(e, "c")
        self.assertTrue(e.undo())
        self.assertEqual(e.edit_text, "ab")

    def test_undo_key_restores_leading_zeros(self) -> None:
        """Undo and redo by key in IntEdit and NumEdit restore the text as it was shown, leading zeros included."""
        for e in (readline_edit(urwid.IntEdit, "", "007"), readline_edit(NumEdit, "0123456789", "", "007")):
            with self.subTest(cls=type(e).__name__):
                e.undo_limit = 10
                type_keys(e, "1")
                self.assertEqual(e.edit_text, "71")
                type_keys(e, "ctrl _")
                self.assertEqual(e.edit_text, "007")
                self.assertEqual(len(e._redo_stack), 1)

    def test_runs_merge_into_one_step(self) -> None:
        """A run of typed characters, of backspace or of delete is one step; a change of kind starts a new one."""
        e = urwid.Edit(undo_limit=10)
        type_keys(e, "a", "b", "c", "d", "backspace", "backspace", "e", "home", "delete", "delete")
        self.assertEqual((e.edit_text, e.edit_pos), ("e", 0))
        expected = [("abe", 0), ("ab", 2), ("abcd", 4), ("", 0)]
        for text, pos in expected:
            self.assertTrue(e.undo())
            self.assertEqual((e.edit_text, e.edit_pos), (text, pos))
        self.assertFalse(e.undo())

    def test_cursor_move_ends_a_run(self) -> None:
        """Typing after a cursor move, by key, by mouse or programmatically, is a new step."""
        for move in ("key", "mouse", "set_edit_pos"):
            with self.subTest(move=move):
                e = urwid.Edit(undo_limit=10)
                type_keys(e, "a", "b")
                if move == "key":
                    type_keys(e, "left")
                elif move == "mouse":
                    e.mouse_event((20,), "mouse press", 1, 1, 0, True)
                else:
                    e.set_edit_pos(1)
                type_keys(e, "c")
                e.undo()
                self.assertEqual(e.edit_text, "ab")
                self.assertTrue(e.undo())
                self.assertEqual(e.edit_text, "")

    def test_other_key_ends_a_run(self) -> None:
        """An unhandled key between two typed characters ends the run."""
        e = urwid.Edit(undo_limit=10)
        type_keys(e, "a", "f1", "b")
        e.undo()
        self.assertEqual(e.edit_text, "a")

    def test_undo_redo_round_trip(self) -> None:
        """Redo makes each undone step again, and a new change clears the redo history."""
        e = urwid.Edit(undo_limit=10)
        type_keys(e, "a", "b", " ", "left", "c")
        self.assertEqual(e.edit_text, "abc ")
        self.assertTrue(e.undo())
        self.assertTrue(e.undo())
        self.assertEqual((e.edit_text, e.edit_pos), ("", 0))
        self.assertTrue(e.redo())
        self.assertEqual((e.edit_text, e.edit_pos), ("ab ", 2))
        self.assertTrue(e.redo())
        self.assertEqual((e.edit_text, e.edit_pos), ("abc ", 3))
        self.assertFalse(e.redo())
        e.undo()
        type_keys(e, "d")
        self.assertFalse(e.redo())
        self.assertEqual(e.edit_text, "abd ")

    def test_commands(self) -> None:
        """The undo and redo commands call undo() and redo(), and return the key when nothing is left."""
        cm = urwid.CommandMap()
        cm.bind_readline()
        cm.bind(Command.REDO, "meta _")
        e = urwid.Edit(undo_limit=10)
        e._command_map = cm
        type_keys(e, "a", "b", "ctrl w")
        self.assertIsNone(e.keypress((20,), "ctrl _"))
        self.assertEqual(e.edit_text, "ab")
        self.assertIsNone(e.keypress((20,), "ctrl _"))
        self.assertEqual(e.keypress((20,), "ctrl _"), "ctrl _")
        self.assertIsNone(e.keypress((20,), "meta _"))
        self.assertEqual(e.edit_text, "ab")
        self.assertEqual(self.history(e), ([("", 0)], [("", 0)]))

    def test_limit(self) -> None:
        """The limit keeps the newest steps; lowering it drops the oldest, 0 clears, a negative value raises."""
        e = urwid.Edit(undo_limit=2)
        type_keys(e, "a", "left", "b", "left", "c")
        self.assertEqual([text for text, _pos in e._undo_stack], ["a", "ba"])
        e.undo_limit = 1
        self.assertEqual([text for text, _pos in e._undo_stack], ["ba"])
        e.undo()
        self.assertEqual(self.history(e), ([], [("cba", 1)]))
        e.undo_limit = 0
        self.assertEqual(self.history(e), ([], []))
        with self.assertRaisesRegex(ValueError, "must not be negative"):
            e.undo_limit = -1
        with self.assertRaisesRegex(ValueError, "must not be negative"):
            urwid.Edit(undo_limit=-1)

    def test_change_from_elsewhere_clears_history(self) -> None:
        """set_edit_text() and insert_text() from the application clear both histories; set_edit_pos() does not."""
        for change in ("set_edit_text", "same text", "insert_text"):
            with self.subTest(change=change):
                e = urwid.Edit(undo_limit=10)
                type_keys(e, "a", "b", "left", "c")
                e.undo()
                e.set_edit_pos(0)
                self.assertNotEqual(self.history(e), ([], []))
                if change == "set_edit_text":
                    e.set_edit_text("other")
                elif change == "same text":
                    e.set_edit_text(e.edit_text)
                else:
                    e.insert_text("x")
                self.assertEqual(self.history(e), ([], []))
                self.assertFalse(e.undo())

    def test_editing_records_one_step(self) -> None:
        """A cut made inside editing() is one step that undo() and redo() take back and make again."""
        e = urwid.Edit("", "", undo_limit=10)
        type_keys(e, *"hello world")
        e.highlight = (5, 11)
        with e.editing():
            e.insert_text("")
            e.insert_text("!")
        self.assertEqual((e.edit_text, e.edit_pos), ("hello!", 6))
        self.assertTrue(e.undo())
        self.assertEqual((e.edit_text, e.edit_pos), ("hello world", 11))
        self.assertTrue(e.redo())
        self.assertEqual(e.edit_text, "hello!")
        self.assertTrue(e.undo())
        self.assertTrue(e.undo())
        self.assertEqual(e.edit_text, "")

    def test_editing_override_and_protected_name(self) -> None:
        """A key enters an override of editing(), and the protected _editing() still records one step."""
        entered: list[str] = []

        class LoggingEdit(urwid.Edit):
            """An Edit that records each editing transaction."""

            @contextlib.contextmanager
            def editing(self) -> Generator[None]:
                entered.append(self.edit_text)
                with super().editing():
                    yield

        e = LoggingEdit("", "", undo_limit=10)
        e.keypress((20,), "a")
        self.assertEqual(entered, [""])
        with e._editing():
            e.insert_text("b")
        self.assertEqual((entered, e.edit_text), (["", "a"], "ab"))
        self.assertTrue(e.undo())
        self.assertEqual(e.edit_text, "a")

    def test_editing_without_a_change_records_nothing(self) -> None:
        e = urwid.Edit("", "", undo_limit=10)
        type_keys(e, "a")
        with e.editing():
            e.set_edit_pos(0)
        self.assertEqual(self.history(e), ([("", 0)], []))

    def test_submit_and_cancel_handler(self) -> None:
        """A submit or cancel handler that clears the field clears the history, masked or not.

        A handler that does not clear it keeps the history.
        """
        for signal, key, mask, clear in (
            ("submit", "enter", None, True),
            ("submit", "enter", "*", True),
            ("submit", "enter", "", True),
            ("submit", "enter", None, False),
            ("cancel", "esc", None, True),
            ("cancel", "esc", None, False),
        ):
            with self.subTest(signal=signal, mask=mask, clear=clear):
                e = urwid.Edit(undo_limit=10, mask=mask)
                if clear:
                    urwid.connect_signal(e, signal, lambda edit, _text: edit.set_edit_text(""))
                type_keys(e, "s", "e", "c", key)
                if clear:
                    self.assertEqual(e.edit_text, "")
                    self.assertEqual(self.history(e), ([], []))
                else:
                    self.assertEqual(self.history(e), ([("", 0)], []))

    def test_change_signal_handler_belongs_to_the_step(self) -> None:
        """A postchange handler that changes the text during a key is part of the key's step."""
        e = urwid.Edit(undo_limit=10)

        def strip_spaces(edit: urwid.Edit, _old: str) -> None:
            if edit.edit_text != edit.edit_text.strip():
                edit.set_edit_text(edit.edit_text.strip())

        urwid.connect_signal(e, "postchange", strip_spaces)
        type_keys(e, "a", " ")
        self.assertEqual(e.edit_text, "a")
        self.assertEqual(self.history(e), ([("", 0)], []))

    def test_override_raising_keeps_history(self) -> None:
        """A set_edit_text override that raises before changing the text leaves the history as it was."""
        e = NoXEdit(undo_limit=10)
        type_keys(e, "a")
        e._undo_stack.append(("x", 1))  # a state recorded before the override started refusing it
        before = self.history(e)
        with self.assertRaises(ValueError):
            e.undo()
        self.assertEqual(self.history(e), before)
        self.assertEqual(e.edit_text, "a")

    def test_postchange_raising_moves_the_step(self) -> None:
        """A postchange handler that raises after the text is restored still moves the step to the other history."""
        e = urwid.Edit(undo_limit=10)
        type_keys(e, "a", "b")
        raising = True

        def fail(_edit: urwid.Edit, _old: str) -> None:
            if raising:
                raise RuntimeError("postchange")

        urwid.connect_signal(e, "postchange", fail)
        with self.assertRaises(RuntimeError):
            e.undo()
        self.assertEqual(e.edit_text, "")
        self.assertEqual(self.history(e), ([], [("ab", 2)]))
        raising = False
        self.assertTrue(e.redo())
        self.assertEqual(e.edit_text, "ab")

    def test_max_length_lowered(self) -> None:
        """A step longer than max_length is not restored and stays in the history."""
        e = urwid.Edit(undo_limit=10, edit_text="abcd")
        type_keys(e, "backspace", "backspace")
        e.max_length = 3
        self.assertFalse(e.undo())
        self.assertEqual(self.history(e), ([("abcd", 4)], []))

    def test_change_after_super_keypress_clears(self) -> None:
        """A subclass that changes the text after the base keypress returns clears the history."""
        e = UpperAfterKeypressEdit(undo_limit=10)
        type_keys(e, "a")
        self.assertEqual(e.edit_text, "A")
        self.assertEqual(self.history(e), ([], []))

    def test_completion_steps(self) -> None:
        """Each completion step is one step, and undo is not a completion key."""
        e = urwid.Edit("", "al", undo_limit=10, text_completer=lambda text, pos: [("alpha", 5), ("alpine", 6)])
        type_keys(e, "tab", "tab")
        self.assertEqual(e.edit_text, "alpine")
        e.undo()
        self.assertEqual(e.edit_text, "alpha")
        self.assertIsNone(e.completion_cycle)

    def test_bytes(self) -> None:
        e = urwid.Edit(b"", undo_limit=10)
        type_keys(e, "a", "b", "backspace")
        e.undo()
        self.assertEqual(e.edit_text, b"ab")
        e.undo()
        self.assertEqual(e.edit_text, b"")

    def test_int_edit_strip_belongs_to_the_digit(self) -> None:
        """IntEdit keeps its history, and the leading-zero strip is undone with the digit that caused it."""
        e = urwid.IntEdit("", 0)
        e.undo_limit = 10
        type_keys(e, "5", "1")
        self.assertEqual(e.edit_text, "51")
        self.assertTrue(e.undo())
        self.assertEqual((e.edit_text, e.edit_pos), ("0", 1))
        self.assertTrue(e.redo())
        self.assertEqual((e.edit_text, e.edit_pos), ("51", 2))
        type_keys(e, "home", "delete")
        self.assertEqual(e.edit_text, "1")
        self.assertTrue(e.undo())
        self.assertEqual((e.edit_text, e.edit_pos), ("51", 0))

    def test_num_edit_trim_belongs_to_the_digit(self) -> None:
        """NumEdit keeps its history, and the trim is undone with the key that caused it."""
        e = NumEdit("0123456789", "", "5002")
        e.undo_limit = 10
        type_keys(e, "home", "delete")
        self.assertEqual(e.edit_text, "002")
        type_keys(e, "end")
        self.assertEqual(e.edit_text, "2")
        self.assertEqual(self.history(e), ([("5002", 0), ("002", 0)], []))
        type_keys(e, "3")
        for text in ("2", "002", "5002"):
            e.undo()
            self.assertEqual(e.edit_text, text)


class EditKillBufferTest(unittest.TestCase):
    def test_chain_joins_in_the_direction_of_the_delete(self) -> None:
        """Backward kills put their text before the entry, forward kills after it, as in readline."""
        cases = (
            ("one two three", 13, ("ctrl w", "ctrl w"), ["two three"]),
            ("one two three", 0, ("meta d", "meta d"), ["one two"]),
            ("one two three", 4, ("ctrl k", "ctrl u"), ["one two three"]),
            ("one two three", 7, ("meta backspace", "meta d"), ["two three"]),
        )
        for text, pos, keys, expected in cases:
            with self.subTest(keys=keys):
                kills: list[str | bytes] = []
                e = readline_edit(urwid.Edit, "", text, edit_pos=pos, kill_buffer=kills)
                type_keys(e, *keys)
                self.assertEqual(kills, expected)

    def test_chain_breaks(self) -> None:
        """Any other key, a mouse event or a change from elsewhere starts a new entry."""
        for interruption in ("left", "x", "unhandled", "mouse", "set_edit_text"):
            with self.subTest(interruption=interruption):
                kills: list[str | bytes] = []
                e = readline_edit(urwid.Edit, "", "aa bb cc dd", kill_buffer=kills)
                type_keys(e, "ctrl w")
                if interruption == "mouse":
                    e.mouse_event((20,), "mouse press", 4, 20, 0, True)
                elif interruption == "set_edit_text":
                    e.set_edit_text("aa bb cc ")
                elif interruption == "unhandled":
                    self.assertEqual(e.keypress((20,), "f1"), "f1")
                else:
                    type_keys(e, interruption, "backspace" if interruption == "x" else "right")
                type_keys(e, "ctrl w")
                self.assertEqual(kills, ["dd", "cc "])

    def test_shared_buffer(self) -> None:
        """Kills from two edits sharing a list never join each other's entries, with or without a mouse event."""
        for click in (True, False):
            with self.subTest(click=click):
                kills: list[str | bytes] = []
                a = readline_edit(urwid.Edit, "", "a1 a2 a3", kill_buffer=kills)
                b = readline_edit(urwid.Edit, "", "b1 b2", kill_buffer=kills)
                type_keys(a, "ctrl w")
                if click:
                    b.mouse_event((20,), "mouse press", 1, 19, 0, True)
                type_keys(b, "ctrl w")
                if click:
                    a.mouse_event((20,), "mouse press", 1, 19, 0, True)
                type_keys(a, "ctrl w")
                self.assertEqual(kills, ["a3", "b2", "a2 "])

    def test_application_change_of_the_list_starts_a_new_entry(self) -> None:
        kills: list[str | bytes] = []
        e = readline_edit(urwid.Edit, "", "aa bb cc", kill_buffer=kills)
        type_keys(e, "ctrl w")
        kills.append("pasted")
        type_keys(e, "ctrl w")
        self.assertEqual(kills, ["cc", "pasted", "bb "])
        kills[-1] = "replaced"
        type_keys(e, "ctrl w")
        self.assertEqual(kills, ["cc", "pasted", "replaced", "aa "])

    def test_assigning_the_list_ends_the_chain(self) -> None:
        kills: list[str | bytes] = ["old"]
        e = readline_edit(urwid.Edit, "", "aa bb", kill_buffer=kills)
        type_keys(e, "ctrl w")
        e.kill_buffer = kills
        type_keys(e, "ctrl w")
        self.assertEqual(kills, ["old", "bb", "aa "])

    def test_masked_edit_kills_nothing(self) -> None:
        """A masked edit, also with an empty mask, puts nothing into a list other widgets may read."""
        for mask in ("*", ""):
            with self.subTest(mask=mask):
                kills: list[str | bytes] = []
                e = readline_edit(urwid.Edit, "", "secret", mask=mask, kill_buffer=kills)
                type_keys(e, "ctrl u")
                self.assertEqual((e.edit_text, kills), ("", []))

    def test_backspace_and_delete_do_not_kill(self) -> None:
        kills: list[str | bytes] = []
        e = readline_edit(urwid.Edit, "", "abc", edit_pos=1, kill_buffer=kills)
        type_keys(e, "backspace", "delete", "ctrl d")
        self.assertEqual((e.edit_text, kills), ("", []))

    def test_yank(self) -> None:
        """Yank inserts the newest entry at the cursor, replacing the highlight, and returns the key with nothing."""
        for kills in (None, []):
            with self.subTest(kills=kills):
                e = readline_edit(urwid.Edit, "", "ab", kill_buffer=kills)
                self.assertEqual(e.keypress((20,), "ctrl y"), "ctrl y")
        e = readline_edit(urwid.Edit, "", "ab", edit_pos=1, kill_buffer=["old", "new"])
        self.assertIsNone(e.keypress((20,), "ctrl y"))
        self.assertEqual((e.edit_text, e.edit_pos), ("anewb", 4))
        e.highlight = (0, 1)
        type_keys(e, "ctrl y")
        self.assertEqual(e.edit_text, "newnewb")

    def test_yank_refused(self) -> None:
        """A yank whose result the keys could not type inserts nothing and returns the key."""
        cases = (
            ("max_length", readline_edit(urwid.Edit, "", "abc", max_length=4), "xy", None),
            ("newline", readline_edit(urwid.Edit, "", "abc"), "x\ny", None),
            ("newline, multiline", readline_edit(urwid.Edit, "", "abc", multiline=True), "x\ny", "abcx\ny"),
            ("tab", readline_edit(urwid.Edit, "", "abc"), "x\ty", None),
            ("tab, allow_tab", readline_edit(urwid.Edit, "", "abc", allow_tab=True), "x\ty", "abcx\ty"),
            ("control", readline_edit(urwid.Edit, "", "abc"), "x\x07", None),
            ("IntEdit letters", readline_edit(urwid.IntEdit, "", 12), "3a", None),
            ("IntEdit digits", readline_edit(urwid.IntEdit, "", 12), "34", "1234"),
            ("NumEdit sign inside", readline_edit(NumEdit, "0123456789", "", "1", allow_negative=True), "-2", None),
            ("NumEdit hex", readline_edit(NumEdit, "0123456789ABCDEF", "", "1"), "fF", "1fF"),
            ("FloatEdit second separator", readline_edit(FloatEdit, "", "1.5"), ".2", None),
            ("bytes from non-ASCII str", readline_edit(urwid.Edit, b"", b"abc"), "\u00e9", None),
            ("str from bytes", readline_edit(urwid.Edit, "", "abc"), b"de", "abcde"),
        )
        for name, e, entry, expected in cases:
            with self.subTest(name=name):
                before = e.edit_text
                e.kill_buffer = [entry]
                result = e.keypress((20,), "ctrl y")
                self.assertEqual(result, None if expected is not None else "ctrl y")
                self.assertEqual(e.edit_text, before if expected is None else expected)

    def test_yank_over_highlighted_separator(self) -> None:
        """FloatEdit judges the result after the highlight is replaced, so its separator may come back."""
        e = readline_edit(FloatEdit, "", "2.0")
        e.kill_buffer = ["1.5"]
        e.highlight = (0, 3)
        self.assertIsNone(e.keypress((20,), "ctrl y"))
        self.assertEqual(e.edit_text, "1.5")

    def test_bytes(self) -> None:
        kills: list[str | bytes] = []
        e = readline_edit(urwid.Edit, b"", "x \u00e9t\u00e9".encode(), kill_buffer=kills)
        type_keys(e, "ctrl w", "ctrl y", "ctrl y")
        self.assertEqual(kills, ["\u00e9t\u00e9".encode()])
        self.assertEqual(e.edit_text, "x \u00e9t\u00e9\u00e9t\u00e9".encode())

    def test_yank_is_one_undo_step(self) -> None:
        kills: list[str | bytes] = []
        e = readline_edit(urwid.Edit, "", "one two", kill_buffer=kills, undo_limit=10)
        type_keys(e, "ctrl w", "ctrl w", "ctrl y")
        self.assertEqual(e.edit_text, "one two")
        for text in ("", "one ", "one two"):
            e.undo()
            self.assertEqual(e.edit_text, text)


def drag(
    e: urwid.Edit,
    press: tuple[int, int],
    *moves: tuple[int, int],
    release: tuple[int, int] | None = None,
    release_button: int = 1,
    size: tuple[int] = (20,),
) -> None:
    """Send a button 1 press, drag reports and an optional release to *e*, each at a ``(col, row)``."""
    e.mouse_event(size, "mouse press", 1, *press, True)
    for move in moves:
        e.mouse_event(size, "mouse drag", 1, *move, True)
    if release is not None:
        e.mouse_event(size, "mouse release", release_button, *release, True)


def first_row(canv: urwid.Canvas) -> list[tuple[typing.Hashable, bytes]]:
    """Return the ``(attribute, text)`` runs of the first row of *canv*."""
    return [(attr, text) for attr, _cs, text in next(iter(canv.content()))]


def record_highlight(e: urwid.Edit) -> list[tuple[tuple[int, int] | None, tuple[int, int] | None]]:
    """Return a list that collects the ``(old, new)`` pairs of the "highlight" signals of *e*."""
    seen: list[tuple[tuple[int, int] | None, tuple[int, int] | None]] = []
    urwid.connect_signal(e, "highlight", lambda _w, old, new: seen.append((old, new)))
    return seen


class EditSelectionTest(unittest.TestCase):
    def test_setter_normalises(self) -> None:
        """The range is ordered, clipped, widened to clusters, and an empty one is None."""
        cases = (
            ("ordered", "hello world", (11, 6), (6, 11)),
            ("clipped", "hello", (-3, 99), (0, 5)),
            ("empty", "hello", (2, 2), None),
            ("empty after clipping", "hello", (7, 9), None),
            ("widened to a cluster", "aéb", (2, 3), (1, 3)),
            ("empty inside a cluster", "aéb", (2, 2), None),
            ("none", "hello", None, None),
        )
        for label, text, value, expected in cases:
            with self.subTest(case=label):
                e = urwid.Edit("", text)
                e.highlight = value
                self.assertEqual(e.highlight, expected)

    def test_setter_rejects_other_values(self) -> None:
        e = urwid.Edit("", "hello")
        for value, error in (((1, 2, 3), ValueError), (3, TypeError)):
            with self.subTest(value=value), self.assertRaises(error):
                e.highlight = value  # type: ignore[assignment]

    def test_signal(self) -> None:
        """ "highlight" is sent for each change of the range, by the setter and by every clear."""
        e = urwid.Edit("", "hello world", undo_limit=10)
        seen = record_highlight(e)
        steps = (
            ("set", lambda: setattr(e, "highlight", (0, 5)), [(None, (0, 5))]),
            ("same value", lambda: setattr(e, "highlight", (5, 0)), []),
            ("cursor move", lambda: e.set_edit_pos(1), [((0, 5), None)]),
            ("set again", lambda: setattr(e, "highlight", (6, 11)), [(None, (6, 11))]),
            ("typed over", lambda: e.keypress((20,), "X"), [((6, 11), None)]),
            ("nothing to clear", lambda: e.set_edit_text("new"), []),
        )
        for label, step, expected in steps:
            with self.subTest(step=label):
                seen.clear()
                step()
                self.assertEqual(seen, expected)

    def test_selected_text(self) -> None:
        e = urwid.Edit("", "hello world", mask="*")
        self.assertEqual(e.selected_text, "")
        e.highlight = (6, 11)
        self.assertEqual(e.selected_text, "world")
        self.assertEqual(urwid.Edit(b"", b"bytes").selected_text, b"")

    def test_copy_cut_and_replace(self) -> None:
        """Copy is selected_text, replace is insert_text(), delete is insert_text("")."""
        e = urwid.Edit("", "hello world")
        e.highlight = (0, 6)
        copied = e.selected_text
        e.insert_text("")
        self.assertEqual((copied, e.edit_text, e.edit_pos, e.highlight), ("hello ", "world", 0, None))
        e.highlight = (0, 5)
        e.insert_text("earth")
        self.assertEqual((e.edit_text, e.highlight), ("earth", None))

    def test_select_attr_draws_the_range(self) -> None:
        """The range is layered over the runs under it, with the bare attribute where there is none."""
        e = urwid.Edit(("cap", "> "), "ls -l", highlighter=lambda text: [("cmd", text[:2]), text[2:]])
        e.highlight = (1, 4)
        self.assertEqual(
            first_row(e.render((10,))),
            [("cap", b"> "), ("cmd", b"ls"), (None, b" -l   ")],
        )
        e.select_attr = "sel"
        self.assertEqual(
            first_row(e.render((10,))),
            [
                ("cap", b"> "),
                ("cmd", b"l"),
                (urwid.LayeredAttr("sel", "cmd"), b"s"),
                ("sel", b" -"),
                (None, b"l   "),
            ],
        )

    def test_select_attr_over_mask_and_not_over_placeholder(self) -> None:
        e = urwid.Edit("", "secret", mask="*", select_attr="sel", placeholder="hint")
        e.highlight = (0, 3)
        self.assertEqual(
            first_row(e.render((8,))),
            [("sel", b"***"), (None, b"***  ")],
        )
        e.set_edit_text("")
        self.assertEqual([attr for attr, _text in first_row(e.render((8,)))], [None])


class EditMouseSelectTest(unittest.TestCase):
    def test_drag_selects_both_end_characters(self) -> None:
        """A forward and a backward drag select the same range, with one signal at the release."""
        cases = (
            ("forward", (3, 0), (9, 0), 1),
            ("backward, X10 release", (9, 0), (3, 0), 0),
            ("press and release only", (3, 0), (9, 0), 1),
        )
        for label, press, release, button in cases:
            with self.subTest(case=label):
                e = urwid.Edit("> ", "hello world", mouse_select=True)
                seen = record_highlight(e)
                moves = () if label == "press and release only" else ((5, 0), (7, 0))
                drag(e, press, *moves, release=release, release_button=button)
                self.assertEqual((seen, e.selected_text), ([(None, (1, 8))], "ello wo"))
                self.assertEqual(e.edit_pos, 7 if press < release else 1)

    def test_click_selects_nothing_and_clears(self) -> None:
        e = urwid.Edit("", "hello world", mouse_select=True)
        drag(e, (1, 0), release=(4, 0))
        seen = record_highlight(e)
        drag(e, (6, 0), release=(6, 0))
        self.assertEqual((seen, e.highlight, e.edit_pos), ([((1, 5), None)], None, 6))

    def test_unfinished_drag_is_drawn_only(self) -> None:
        e = urwid.Edit("", "hello", mouse_select=True, select_attr="sel")
        seen = record_highlight(e)
        drag(e, (1, 0), (3, 0))
        self.assertEqual((seen, e.highlight, e.edit_pos), ([], None, 3))
        self.assertEqual(
            first_row(e.render((10,), focus=True)),
            [(None, b"h"), ("sel", b"ell"), (None, b"o     ")],
        )

    def test_rows_and_line_ends(self) -> None:
        cases = (
            ("across rows", (1, 0), (0, 1), (1, 4)),
            ("row below the text", (0, 0), (1, 5), (0, 5)),
            ("row above the text", (1, 1), (0, -2), (0, 5)),
            ("right of a line", (0, 0), (10, 0), (0, 2)),
            ("right of the text", (0, 1), (10, 1), (3, 5)),
        )
        for label, press, release, expected in cases:
            with self.subTest(case=label):
                e = urwid.Edit("", "ab\ncd", multiline=True, mouse_select=True)
                drag(e, press, release, release=release)
                self.assertEqual(e.highlight, expected)

    def test_wrapped_rows(self) -> None:
        e = urwid.Edit("", "one two three", mouse_select=True)
        drag(e, (4, 0), release=(2, 1), size=(8,))
        self.assertEqual(e.selected_text, "two thr")

    def test_clusters(self) -> None:
        """A wide character released on its second cell, and a base with a combining mark, are selected whole."""
        cases = (
            ("wide", "a中b", (2, 0), "a中"),
            ("combining", "aé", (1, 0), "aé"),
            ("flag", f"a{RI_U}{RI_S}", (2, 0), f"a{RI_U}{RI_S}"),
        )
        for label, text, release, expected in cases:
            with self.subTest(case=label):
                e = urwid.Edit("", text, mouse_select=True)
                drag(e, (0, 0), release=release)
                self.assertEqual(e.selected_text, expected)

    def test_clip_wrap_extends_as_the_view_scrolls(self) -> None:
        e = urwid.Edit("", "0123456789abcdef", wrap="clip", mouse_select=True, edit_pos=0)
        e.render((5,), focus=True)
        drag(e, (1, 0), size=(5,))
        for _report in range(3):  # a report one column past the edge, as at the edge of the screen
            e.mouse_event((5,), "mouse drag", 1, 5, 0, True)
            e.render((5,), focus=True)
        e.mouse_event((5,), "mouse release", 1, 4, 0, True)
        self.assertEqual(e.selected_text, "1234567")

    def test_mask(self) -> None:
        e = urwid.Edit("", "secret", mask="*", mouse_select=True)
        drag(e, (0, 0), release=(2, 0))
        self.assertEqual(e.selected_text, "sec")

    def test_drag_dropped_with_nothing_selected(self) -> None:
        """A key, a new text, a press and an unfocused render each drop an unfinished drag."""
        steps = (
            ("key", lambda e: e.keypress((20,), "X"), "heXllo"),
            ("new text", lambda e: e.set_edit_text("other"), "other"),
            ("unfocused render", lambda e: e.render((20,), focus=False), "hello"),
        )
        for label, step, text in steps:
            with self.subTest(case=label):
                e = urwid.Edit("", "hello", mouse_select=True)
                seen = record_highlight(e)
                drag(e, (0, 0), (2, 0))
                step(e)
                e.mouse_event((20,), "mouse release", 0, 4, 0, True)
                self.assertEqual((seen, e.highlight, e.edit_text), ([], None, text))

    def test_press_starts_a_new_drag(self) -> None:
        e = urwid.Edit("", "hello world", mouse_select=True)
        drag(e, (0, 0), (3, 0))
        drag(e, (6, 0), release=(10, 0))
        self.assertEqual(e.selected_text, "world")

    def test_focus_loss_drops_the_cached_range(self) -> None:
        e = urwid.Edit("", "hello", mouse_select=True, select_attr="sel")
        drag(e, (0, 0), (2, 0))
        self.assertEqual([attr for attr, _text in first_row(e.render((10,), focus=True))], ["sel", None])
        e.render((10,), focus=False)
        self.assertEqual([attr for attr, _text in first_row(e.render((10,), focus=True))], [None])

    def test_release_over_a_sibling(self) -> None:
        """A drag released over another widget of a Pile selects nothing and keeps the range drawn."""
        e = urwid.Edit("", "hello", mouse_select=True, select_attr="sel")
        other = urwid.Edit("", "other")
        pile = urwid.Pile([e, other])
        pile.mouse_event((10,), "mouse press", 1, 0, 0, True)
        pile.mouse_event((10,), "mouse drag", 1, 2, 0, True)
        pile.mouse_event((10,), "mouse drag", 1, 2, 1, True)
        pile.mouse_event((10,), "mouse release", 1, 2, 1, True)
        self.assertIs(pile.focus, e)
        self.assertIsNone(e.highlight)
        self.assertEqual(
            [attr for attr, _text in first_row(pile.render((10,), focus=True))],
            ["sel", None],
        )

    def test_other_events_as_without_mouse_select(self) -> None:
        """Other buttons, the wheel and a release with no drag behave as on a plain Edit."""
        events = (
            ("mouse press", 3, 2, 0),
            ("mouse press", 4, 2, 0),
            ("mouse drag", 1, 3, 0),
            ("mouse release", 1, 4, 0),
            ("mouse release", 0, 1, 0),
        )
        for event in events:
            with self.subTest(event=event):
                plain = urwid.Edit("", "hello world")
                selecting = urwid.Edit("", "hello world", mouse_select=True)
                self.assertEqual(
                    selecting.mouse_event((20,), *event, True),
                    plain.mouse_event((20,), *event, True),
                )
                self.assertEqual((selecting.edit_pos, selecting.highlight), (plain.edit_pos, None))

    def test_default_is_off(self) -> None:
        e = urwid.Edit("", "hello world")
        drag(e, (1, 0), (3, 0), release=(5, 0))
        self.assertEqual((e.edit_pos, e.highlight, e.mouse_select, e.select_attr), (5, None, False, None))


class IntEditTest(unittest.TestCase):
    def test_bytes_caption_trims_zeros_and_preserves_cursor_and_signals(self) -> None:
        for caption in ("", b""):
            for initial, keys, expected, expected_pos, changes in (
                ("0", ("7",), "7", 1, 1),
                ("0", ("0",), "0", 1, 0),
                ("0002", ("end",), "2", 1, 1),
                ("5002", ("home", "delete", "end"), "2", 1, 2),
            ):
                with self.subTest(caption=caption, initial=initial, keys=keys):
                    e = urwid.IntEdit(caption, initial)
                    seen = []
                    urwid.connect_signal(
                        e, "postchange", lambda widget, old, seen=seen: seen.append((widget.edit_text, widget.edit_pos))
                    )
                    for key in keys:
                        self.assertIsNone(e.keypress((20,), key))
                    typed_expected = expected.encode("ascii") if isinstance(caption, bytes) else expected
                    self.assertEqual(e.edit_text, typed_expected)
                    self.assertEqual(e.edit_pos, expected_pos)
                    self.assertEqual(e.value(), int(expected))
                    self.assertEqual(len(seen), changes)
                    if seen:
                        self.assertEqual(seen[-1], (typed_expected, expected_pos))

    def test_bytes_caption_insert_text_trims_zeros_before_cursor(self) -> None:
        for caption, inserted, expected in (("", "7", "7"), (b"", b"7", b"7")):
            with self.subTest(caption=caption):
                e = urwid.IntEdit(caption, 0)
                e.insert_text(inserted)
                self.assertEqual(e.edit_text, expected)
                self.assertEqual(e.edit_pos, 1)

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

    def test_completion_with_leading_zeros_keeps_cycling(self) -> None:
        """Candidates are held without the leading zeros keypress() removes, so the cycle goes on."""
        completer = mock.Mock(return_value=[("007", 3), ("0042", 4)])
        e = urwid.IntEdit("", 1)
        e.text_completer = completer
        seen = []
        for _key in range(3):
            self.assertIsNone(e.keypress((10,), "tab"))
            seen.append((e.edit_text, e.edit_pos))
        self.assertEqual(seen, [("7", 1), ("42", 2), ("1", 1)])
        completer.assert_called_once_with("1", 1)

    def test_completion_from_text_with_leading_zeros_keeps_cycling(self) -> None:
        """A cycle started from text set with leading zeros returns to it without them, and goes on."""
        completer = mock.Mock(return_value=[("10", 2), ("20", 2)])
        e = urwid.IntEdit()
        e.set_edit_text("007")
        e.set_edit_pos(3)
        e.text_completer = completer
        seen = []
        for _key in range(4):
            self.assertIsNone(e.keypress((10,), "tab"))
            seen.append((e.edit_text, e.edit_pos))
        self.assertEqual(seen, [("10", 2), ("20", 2), ("7", 1), ("10", 2)])
        completer.assert_called_once_with("007", 3)

    def test_value_empty(self) -> None:
        e = urwid.IntEdit()
        self.assertEqual(e.value(), 0)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

import urwid


class EditTest(unittest.TestCase):
    def test_selectable(self) -> None:
        self.assertTrue(urwid.Edit().selectable())

    def test_sizing(self) -> None:
        self.assertEqual(urwid.Edit().sizing(), frozenset([urwid.FLOW]))

    def test_get_text_masked(self) -> None:
        e = urwid.Edit("pw:", "secret", mask="*")
        self.assertEqual(e.get_text(), ("pw:******", []))

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

    def test_keypress_tab_not_allowed(self) -> None:
        e = urwid.Edit("", "")
        self.assertEqual(e.keypress((20,), "tab"), "tab")

    def test_keypress_enter_multiline(self) -> None:
        e = urwid.Edit("", "ab", multiline=True, edit_pos=1)
        e.keypress((20,), "enter")
        self.assertEqual(e.edit_text, "a\nb")

    def test_keypress_enter_not_multiline(self) -> None:
        e = urwid.Edit("", "ab")
        self.assertEqual(e.keypress((20,), "enter"), "enter")

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

    def test_keypress_unhandled_passthrough(self) -> None:
        e = urwid.IntEdit()
        self.assertEqual(e.keypress((10,), "shift f1"), "shift f1")

    def test_value(self) -> None:
        e = urwid.IntEdit()
        e.keypress((10,), "5")
        e.keypress((10,), "1")
        self.assertEqual(e.value(), 51)

    def test_value_empty(self) -> None:
        e = urwid.IntEdit()
        self.assertEqual(e.value(), 0)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import copyreg
import pickle
import unittest

import urwid


class WidgetWrapTest(unittest.TestCase):
    def test_delegates_sizing_pack_and_render(self) -> None:
        wrapped = urwid.WidgetWrap(urwid.Text("hello"))

        self.assertEqual(frozenset((urwid.FLOW, urwid.FIXED)), wrapped.sizing())
        self.assertFalse(wrapped.selectable())
        self.assertEqual((5, 1), wrapped.pack(()))
        self.assertEqual([b"hello"], wrapped.render(()).text)

    def test_replace_wrapped_widget(self) -> None:
        wrap = urwid.WidgetWrap(urwid.Button("edit me"))
        self.assertTrue(wrap.selectable())
        self.assertEqual("left", wrap.keypress((12,), "left"))

        wrap._w = urwid.Text("gone")
        self.assertFalse(wrap.selectable())
        self.assertEqual([b"gone"], wrap.render(()).text)


class PlainReduceText(urwid.Text):
    """Text that pickles as its text through its own ``__reduce__``."""

    def __reduce__(self) -> tuple[type[str], tuple[str]]:
        """Rebuild as the plain text string."""
        return str, (self.text,)


class WidgetPickleTest(unittest.TestCase):
    def test_every_protocol_reduces_as_protocol_2(self) -> None:
        """Protocols 0 and 1 do not rebuild a widget from a base class, which is typing.Generic on GraalPy."""
        for protocol in range(pickle.HIGHEST_PROTOCOL + 1):
            with self.subTest(protocol=protocol):
                text = urwid.Text("a", align="right")
                self.assertIs(copyreg.__newobj__, text.__reduce_ex__(protocol)[0])
                result = pickle.loads(pickle.dumps(text, protocol=protocol))
                self.assertIs(urwid.Text, type(result))
                self.assertEqual(("a", "right"), (result.text, result.align))
                self.assertEqual("a", pickle.loads(pickle.dumps(PlainReduceText("a"), protocol=protocol)))


if __name__ == "__main__":
    unittest.main()

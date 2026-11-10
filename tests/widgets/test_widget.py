from __future__ import annotations

import copyreg
import gc
import pickle
import sys
import unittest
import warnings
import weakref

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

    def test_state_without_an_added_attribute(self) -> None:
        """A widget whose state predates an attribute with a default reads the default and lays out as before."""
        for widget, name, default in (
            (
                urwid.Overlay(urwid.Text("a"), urwid.SolidFill("#"), "center", 4, "middle", "pack"),
                "shrink_to_fit",
                False,
            ),
            (urwid.Filler(urwid.Text("a")), "shrink_to_fit", False),
        ):
            with self.subTest(type(widget).__name__):
                state = dict(vars(widget))
                del state[name]
                restored = copyreg.__newobj__(type(widget))
                vars(restored).update(state)
                self.assertEqual(default, getattr(restored, name))
                self.assertEqual(widget.render((6, 3)).text, restored.render((6, 3)).text)


class WidgetSizingErrorTest(unittest.TestCase):
    """A size of an unsupported sizing mode raises an error that names the widget."""

    def test_unsupported_size_names_widget_and_hint(self) -> None:
        """The error names the widget, the size and how to give it that size."""
        cases = (
            ("box size to flow widget", urwid.Text("x"), (20, 10), ValueError, "BOX size (20, 10)", "Filler"),
            ("flow size to box widget", urwid.SolidFill("x"), (20,), ValueError, "FLOW size (20,)", "BoxAdapter"),
            ("box size to BoxAdapter", urwid.BoxAdapter(urwid.SolidFill("x"), 2), (20, 2), ValueError, "BOX", "Filler"),
        )
        for label, widget, size, cause_type, size_text, hint in cases:
            with self.subTest(label), self.assertRaises(urwid.WidgetSizingError) as ctx:
                widget.render(size)
            self.assertIs(widget, ctx.exception.widget)
            self.assertEqual(size, ctx.exception.size)
            self.assertIsInstance(ctx.exception, cause_type)
            self.assertIsInstance(ctx.exception.__cause__, cause_type)
            self.assertIn(size_text, str(ctx.exception))
            self.assertIn(hint, str(ctx.exception))

    def test_notes_list_parents_innermost_first(self) -> None:
        """The notes list the widgets around the failed one, once each."""
        text = urwid.Text("x")
        frame = urwid.Frame(urwid.AttrMap(urwid.Padding(text, left=1), "a"), header=urwid.Text("h"))

        with self.assertRaises(urwid.WidgetSizingError) as ctx:
            frame.render((30, 10))

        self.assertIs(text, ctx.exception.widget)
        self.assertEqual(
            [
                "  inside Padding with size (30, 9)",
                "  inside AttrMap with size (30, 9)",
                "  inside Frame with size (30, 10)",
            ],
            ctx.exception.__notes__,
        )

    def test_rows_of_box_widget_names_the_child(self) -> None:
        """A container that asks a box widget for its rows names that widget."""
        fill = urwid.SolidFill("x")
        pile = urwid.Pile([fill])

        with self.assertWarns(urwid.widget.PileWarning), self.assertRaises(urwid.WidgetSizingError) as ctx:
            pile.rows((20,))

        self.assertIs(fill, ctx.exception.widget)
        self.assertIsNone(ctx.exception.size)
        self.assertIsInstance(ctx.exception, AttributeError)
        self.assertIn("has no rows() method", str(ctx.exception))
        self.assertEqual(["  inside Pile with size (20,)"], ctx.exception.__notes__)

    def test_error_of_supported_size_is_not_converted(self) -> None:
        """An error from a size the widget supports passes through unchanged."""

        class BrokenText(urwid.Text):
            """Text whose render always fails."""

            def render(self, size: tuple[int] | tuple[()], focus: bool = False) -> urwid.Canvas:
                raise ValueError("broken")

        with self.assertRaises(ValueError) as ctx:
            BrokenText("x").render((20,))

        self.assertNotIsInstance(ctx.exception, urwid.WidgetSizingError)


class BoxOnlyWidget(urwid.Widget):
    """A custom box widget whose sizing methods unpack a BOX size."""

    _sizing = frozenset((urwid.BOX,))
    _selectable = True

    def render(self, size: tuple[int, int], focus: bool = False) -> urwid.Canvas:
        """Render a blank box."""
        maxcol, maxrow = size
        return urwid.SolidCanvas(" ", maxcol, maxrow)

    def rows(self, size: tuple[int, int], focus: bool = False) -> int:
        """Return the rows of the box."""
        _maxcol, maxrow = size
        return maxrow

    def pack(self, size: tuple[int, int], focus: bool = False) -> tuple[int, int]:
        """Return the box size."""
        maxcol, maxrow = size
        return maxcol, maxrow

    def keypress(self, size: tuple[int, int], key: str) -> str | None:
        """Leave every key unhandled."""
        _maxcol, _maxrow = size
        return key

    def mouse_event(
        self,
        size: tuple[int, int],
        event: str,
        button: int,
        col: int,
        row: int,
        focus: bool,
    ) -> bool | None:
        """Leave every mouse event unhandled."""
        _maxcol, _maxrow = size
        return False


class CustomWidgetSizingErrorTest(unittest.TestCase):
    """Every sizing method a custom widget defines raises a sizing error for a wrong size."""

    def test_methods_of_custom_widget(self) -> None:
        """Each method names the custom widget and the FLOW size it got."""
        widget = BoxOnlyWidget()
        calls = {
            "render": lambda: widget.render((20,)),
            "rows": lambda: widget.rows((20,)),
            "pack": lambda: widget.pack((20,)),
            "keypress": lambda: widget.keypress((20,), "x"),
            "mouse_event": lambda: widget.mouse_event((20,), "mouse press", 1, 0, 0, True),
        }
        for name, call in calls.items():
            with self.subTest(name), self.assertRaises(urwid.WidgetSizingError) as ctx:
                call()
            self.assertIs(widget, ctx.exception.widget)
            self.assertEqual((20,), ctx.exception.size)
            self.assertIsInstance(ctx.exception, ValueError)
            self.assertIn("FLOW size (20,)", str(ctx.exception))

    def test_keypress_inside_container_is_noted(self) -> None:
        """A wrong size passed down by keypress() lists the container in the notes."""
        widget = BoxOnlyWidget()

        with self.assertRaises(urwid.WidgetSizingError) as ctx:
            urwid.Padding(widget, left=1).keypress((20,), "x")

        self.assertIs(widget, ctx.exception.widget)
        self.assertEqual(["  inside Padding with size (20,)"], ctx.exception.__notes__)

    def test_supported_size_is_unchanged(self) -> None:
        """A BOX size reaches the methods and their results come back unchanged."""
        widget = BoxOnlyWidget()

        self.assertEqual((20, 3), widget.pack((20, 3)))
        self.assertEqual("x", widget.keypress((20, 3), "x"))
        self.assertFalse(widget.mouse_event((20, 3), "mouse press", 1, 0, 0, True))

    def test_pickle_drops_the_widget(self) -> None:
        """A pickled error keeps the message, size, notes and AttributeError fields, without the widget."""
        cases = {
            "unpacked size": lambda: urwid.Padding(BoxOnlyWidget(), left=1).keypress((20,), "x"),
            "missing rows": lambda: urwid.Pile([urwid.SolidFill("x")]).rows((20,)),
        }
        for label, call in cases.items():
            with self.subTest(label), warnings.catch_warnings(), self.assertRaises(urwid.WidgetSizingError) as ctx:
                warnings.simplefilter("ignore", urwid.widget.PileWarning)
                call()
            result = pickle.loads(pickle.dumps(ctx.exception))
            self.assertIs(type(ctx.exception), type(result))
            self.assertEqual(str(ctx.exception), str(result))
            self.assertEqual(ctx.exception.size, result.size)
            self.assertEqual(ctx.exception.__notes__, result.__notes__)
            self.assertIsNone(result.widget)
            self.assertEqual(getattr(ctx.exception, "name", None), getattr(result, "name", None))

    def test_missing_rows_keeps_attribute_error_fields(self) -> None:
        """The converted AttributeError keeps the name and object of the missing attribute."""
        fill = urwid.SolidFill("x")

        with self.assertWarns(urwid.widget.PileWarning), self.assertRaises(AttributeError) as ctx:
            urwid.Pile([fill]).rows((20,))

        self.assertEqual("rows", ctx.exception.name)
        self.assertIs(fill, ctx.exception.obj)

    def test_flow_sizing_without_rows(self) -> None:
        """A widget that claims FLOW sizing but has no rows() is told to define it."""

        class NoRows(urwid.Widget):
            """A widget with the default sizing and no rows()."""

            def render(self, size: tuple[int, ...], focus: bool = False) -> urwid.Canvas:
                """Render nothing; the test never renders it."""
                raise NotImplementedError

        with self.assertRaises(urwid.WidgetSizingError) as ctx:
            urwid.Pile([NoRows()]).rows((20,))

        self.assertIn("has FLOW sizing but no rows() method", str(ctx.exception))

    def test_other_errors_pass_through(self) -> None:
        """Errors that a wrong size did not cause, and a failing sizing(), leave the original error."""

        class Broken(BoxOnlyWidget):
            """A box widget whose keypress fails with errors of its own."""

            def keypress(self, size: tuple[int, int], key: str) -> str | None:
                """Raise the error named by the key."""
                errors = {"index": IndexError("own"), "attribute": AttributeError("own")}
                raise errors[key]

        class BrokenSizing(BoxOnlyWidget):
            """A box widget whose sizing() fails."""

            def sizing(self) -> frozenset[urwid.Sizing]:
                """Fail."""
                raise RuntimeError("sizing")

        for key, error_type in (("index", IndexError), ("attribute", AttributeError)):
            with self.subTest(key), self.assertRaises(error_type) as ctx:
                Broken().keypress((20, 3), key)
            self.assertNotIsInstance(ctx.exception, urwid.WidgetSizingError)

        with self.subTest("sizing fails"), self.assertRaises(ValueError) as ctx:
            BrokenSizing().keypress((20,), "x")
        self.assertNotIsInstance(ctx.exception, urwid.WidgetSizingError)

    @unittest.skipUnless(sys.implementation.name == "cpython", "relies on reference counting freeing the widget")
    def test_error_does_not_keep_widget_alive(self) -> None:
        """The widget is freed by reference counting once the error is dropped."""

        class FlowParent(urwid.Widget):
            """A flow widget that asks its child for rows; unlike Pile, it holds no reference cycle of its own."""

            _sizing = frozenset((urwid.FLOW,))

            def __init__(self, child: urwid.Widget) -> None:
                super().__init__()
                self.child = child

            def rows(self, size: tuple[int], focus: bool = False) -> int:
                """Return the rows of the child."""
                return self.child.rows(size, focus)  # type: ignore[attr-defined]

            def render(self, size: tuple[int], focus: bool = False) -> urwid.Canvas:
                """Render nothing; the test never renders it."""
                raise NotImplementedError

        cases = {
            "unpacked size": (lambda widget: widget.render((20,)), BoxOnlyWidget),
            "missing rows": (lambda widget: FlowParent(widget).rows((20,)), urwid.SolidFill),
        }
        for label, (call, widget_type) in cases.items():
            with self.subTest(label):
                widget = widget_type()
                ref = weakref.ref(widget)
                caught = False
                gc.disable()
                try:
                    # Not assertRaises: it clears the traceback frames, which would hide a reference cycle through them.
                    try:
                        call(widget)
                    except urwid.WidgetSizingError:
                        caught = True
                    del widget
                    self.assertIsNone(ref())
                finally:
                    gc.enable()
                self.assertTrue(caught)


if __name__ == "__main__":
    unittest.main()

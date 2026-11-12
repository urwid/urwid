"""Tests for :class:`urwid.OverlayStack`."""

from __future__ import annotations

import gc
import sys
import typing
import unittest
import weakref

import urwid
from tests.util import collect_and_count_alive
from urwid.testing import check_sizing, render_text

if typing.TYPE_CHECKING:
    from collections.abc import Callable

SIZE = (10, 5)


class RecordingFill(urwid.SolidFill):
    """A box widget that records the mouse events and keys it receives and handles them all."""

    _selectable = True

    def __init__(self, fill_char: str = " ") -> None:
        super().__init__(fill_char)
        self.events: list[tuple[str, int, int, int]] = []
        self.keys: list[str] = []

    def keypress(self, size: tuple[int, int], key: str) -> None:
        self.keys.append(key)

    def mouse_event(
        self,
        size: tuple[int, int],
        event: str,
        button: int,
        col: int,
        row: int,
        focus: bool,
    ) -> bool:
        self.events.append((event, button, col, row))
        return True


def record_closed(stack: urwid.OverlayStack) -> list[tuple[urwid.Widget, object]]:
    """Return the list the ``"closed"`` signals of *stack* are appended to, as (*widget*, *result*)."""
    seen: list[tuple[urwid.Widget, object]] = []

    def on_closed(sender: urwid.OverlayStack, widget: urwid.Widget, result: object) -> None:
        assert sender is stack
        seen.append((widget, result))

    urwid.connect_signal(stack, "closed", on_closed)
    return seen


def top_overlay(stack: urwid.OverlayStack) -> urwid.Overlay[urwid.Widget, urwid.Widget]:
    """Return the overlay of the top dialog of *stack*."""
    overlay = stack._w
    assert isinstance(overlay, urwid.Overlay)
    return overlay


class OverlayStackConstructionTest(unittest.TestCase):
    """Building an ``OverlayStack`` and reading its state."""

    def test_defaults(self) -> None:
        """A new stack has no dialog open, shows its base, and its repr names no argument."""
        base = urwid.SolidFill(".")
        stack = urwid.OverlayStack(base)
        self.assertIs(base, stack.base)
        self.assertEqual((), stack.levels)
        self.assertEqual(0, stack.depth)
        self.assertFalse(stack.close_on_menu)
        self.assertFalse(stack.close_on_click_outside)
        self.assertEqual("<OverlayStack box widget (depth 0)>", repr(stack))
        self.assertEqual(render_text(base, SIZE), render_text(stack, SIZE))

    def test_repr(self) -> None:
        """The repr counts the open dialogs and names the flags that differ from their defaults."""
        stack = urwid.OverlayStack(urwid.SolidFill("."), close_on_menu=True, close_on_click_outside=True)
        stack.open(urwid.Edit())
        self.assertEqual(
            "<OverlayStack selectable box widget (depth 1) close_on_click_outside=True close_on_menu=True>",
            repr(stack),
        )

    def test_sizing(self) -> None:
        """The stack is a box widget at every depth, whatever its base and its dialogs support."""
        stack = urwid.OverlayStack(urwid.SolidFill("."))
        for depth in range(3):
            with self.subTest(depth=depth):
                self.assertEqual(frozenset((urwid.BOX,)), stack.sizing())
                check_sizing(stack, cols=10, rows=5)
                stack.open(urwid.Text(str(depth)))


class OverlayStackOpenCloseTest(unittest.TestCase):
    """Opening and closing dialogs."""

    def test_open_two_levels(self) -> None:
        """Each dialog is drawn on top of the one below, and ``levels`` lists them the lowest first."""
        stack = urwid.OverlayStack(urwid.SolidFill("."))
        first = urwid.Text("1111111111")
        second = urwid.Text("22")
        stack.open(first, width=8, valign="top")
        stack.open(second, width=4)
        self.assertEqual(2, stack.depth)
        self.assertEqual((first, second), stack.levels)
        self.assertEqual(
            [
                ".11111111.",
                ".11      .",
                "...22  ...",
                "..........",
                "..........",
            ],
            render_text(stack, SIZE),
        )

    def test_close_uncovers_the_level_below(self) -> None:
        """``close()`` takes the top dialog down and reports it, with the result, to ``"closed"``."""
        stack = urwid.OverlayStack(urwid.SolidFill("."))
        first = urwid.Text("1")
        second = urwid.Text("2")
        stack.open(first)
        expected = render_text(stack, SIZE)
        stack.open(second)
        seen = record_closed(stack)

        self.assertTrue(stack.close("done"))
        self.assertEqual([(second, "done")], seen)
        self.assertEqual((first,), stack.levels)
        self.assertEqual(expected, render_text(stack, SIZE))

    def test_close_nothing(self) -> None:
        """Closing at depth 0, or a widget that is not open, returns ``False`` and sends nothing."""
        stack = urwid.OverlayStack(urwid.SolidFill("."))
        seen = record_closed(stack)
        self.assertFalse(stack.close())
        stack.open(urwid.Text("1"))
        self.assertFalse(stack.close(widget=urwid.Text("other")))
        self.assertEqual([], seen)
        self.assertEqual(1, stack.depth)

    def test_open_twice(self) -> None:
        """A widget already open in the stack cannot be opened again."""
        stack = urwid.OverlayStack(urwid.SolidFill("."))
        widget = urwid.Text("1")
        stack.open(widget)
        stack.open(urwid.Text("2"))
        with self.assertRaises(ValueError):
            stack.open(widget)
        self.assertEqual(2, stack.depth)

    def test_close_middle_level(self) -> None:
        """Closing a lower dialog closes the ones above it first, top down, each with the result ``None``."""
        stack = urwid.OverlayStack(urwid.SolidFill("."))
        widgets = [urwid.Text(str(n)) for n in range(3)]
        calls: list[tuple[int, object]] = []
        for n, widget in enumerate(widgets):
            stack.open(widget, on_close=lambda result, n=n: calls.append((n, result)))
        seen = record_closed(stack)

        self.assertTrue(stack.close("r", widget=widgets[1]))
        self.assertEqual([(2, None), (1, "r")], calls)
        self.assertEqual([(widgets[2], None), (widgets[1], "r")], seen)
        self.assertEqual((widgets[0],), stack.levels)

        self.assertTrue(stack.close("r", widget=widgets[0]))
        self.assertEqual([(widgets[2], None), (widgets[1], "r"), (widgets[0], "r")], seen)
        self.assertEqual(0, stack.depth)


class OverlayStackCallbackTest(unittest.TestCase):
    """What ``on_close`` and the ``"closed"`` handlers see and may do."""

    def test_on_close_runs_before_closed(self) -> None:
        """``on_close`` runs after the dialog is removed and before ``"closed"`` is sent."""
        stack = urwid.OverlayStack(urwid.SolidFill("."))
        order: list[str] = []
        stack.open(urwid.Text("1"), on_close=lambda _result: order.append(f"on_close depth={stack.depth}"))
        urwid.connect_signal(stack, "closed", lambda *_args: order.append("closed"))
        stack.close()
        self.assertEqual(["on_close depth=0", "closed"], order)

    def test_on_close_opens_the_next_dialog(self) -> None:
        """A dialog opened by ``on_close`` stays open on top."""
        stack = urwid.OverlayStack(urwid.SolidFill("."))
        result_dialog = urwid.Text("result")
        stack.open(urwid.Text("progress"), on_close=lambda _result: stack.open(result_dialog))
        self.assertTrue(stack.close())
        self.assertEqual((result_dialog,), stack.levels)
        self.assertIs(result_dialog, top_overlay(stack).top_w)

    def test_on_close_reopens_itself(self) -> None:
        """A dialog whose ``on_close`` opens it again is closed once and stays open."""
        stack = urwid.OverlayStack(urwid.SolidFill("."))
        widget = urwid.Text("1")
        calls: list[object] = []

        def reopen(result: object) -> None:
            calls.append(result)
            stack.open(widget)

        stack.open(widget, on_close=reopen)
        self.assertTrue(stack.close("r"))
        self.assertEqual(["r"], calls)
        self.assertEqual((widget,), stack.levels)

    def test_dialog_opened_above_the_target_closes_too(self) -> None:
        """A dialog an upper ``on_close`` opens while a lower dialog closes is closed as well."""
        stack = urwid.OverlayStack(urwid.SolidFill("."))
        lower = urwid.Text("lower")
        extra = urwid.Text("extra")
        upper = urwid.Text("upper")
        stack.open(lower)
        stack.open(upper, on_close=lambda _result: stack.open(extra))
        seen = record_closed(stack)
        self.assertTrue(stack.close("r", widget=lower))
        self.assertEqual(0, stack.depth)
        self.assertEqual([(upper, None), (extra, None), (lower, "r")], seen)

    def test_on_close_closes_the_target(self) -> None:
        """When an upper ``on_close`` closes the target itself, the target is closed once."""
        stack = urwid.OverlayStack(urwid.SolidFill("."))
        lower = urwid.Text("lower")
        stack.open(urwid.Text("base dialog"))
        stack.open(lower)
        stack.open(urwid.Text("upper"), on_close=lambda _result: stack.close("inner", widget=lower))
        seen = record_closed(stack)
        self.assertTrue(stack.close("outer", widget=lower))
        self.assertEqual([("inner", lower)], [(result, widget) for widget, result in seen if widget is lower])
        self.assertEqual(1, stack.depth)

    def test_on_close_raises(self) -> None:
        """An exception from ``on_close`` propagates, and the dialog is already gone."""
        stack = urwid.OverlayStack(urwid.SolidFill("."))
        first = urwid.Text("1")
        stack.open(first)

        def fail(_result: object) -> typing.NoReturn:
            raise RuntimeError("callback failed")

        stack.open(urwid.Text("2"), on_close=fail)
        seen = record_closed(stack)
        with self.assertRaisesRegex(RuntimeError, "callback failed"):
            stack.close()
        self.assertEqual((first,), stack.levels)
        self.assertIs(first, top_overlay(stack).top_w)
        self.assertEqual([], seen)


class OverlayStackMenuKeyTest(unittest.TestCase):
    """Closing the top dialog on a key for the ``menu`` command."""

    def test_menu_key(self) -> None:
        """The key closes the top dialog only when the flag is on for that dialog."""
        cases: tuple[tuple[str, bool, bool | None, bool], ...] = (
            # label, stack flag, open() flag, closes
            ("stack flag", True, None, True),
            ("open() overrides the stack flag", True, False, False),
            ("open() flag alone", False, True, True),
            ("no flag", False, None, False),
        )
        for label, stack_flag, open_flag, closes in cases:
            with self.subTest(label):
                stack = urwid.OverlayStack(urwid.SolidFill("."), close_on_menu=stack_flag)
                first = urwid.Text("1")
                stack.open(first, close_on_menu=open_flag)
                stack.open(urwid.Text("2"), close_on_menu=open_flag)
                seen = record_closed(stack)

                self.assertEqual(None if closes else "esc", stack.keypress(SIZE, "esc"))
                self.assertEqual(1 if closes else 2, stack.depth)
                self.assertEqual(1 if closes else 0, len(seen))
                if closes:
                    self.assertIsNone(seen[0][1])

    def test_inner_drop_down_takes_the_first_key(self) -> None:
        """An open drop-down list inside the dialog closes on the first key, and the dialog on the second."""
        stack = urwid.OverlayStack(urwid.SolidFill("."), close_on_menu=True)
        drop_down = urwid.DropDown(["red", "green"])
        stack.open(urwid.PopUpTarget(urwid.Filler(drop_down, valign="top")), width=10, height=5)
        size = (12, 7)
        stack.keypress(size, "enter")
        self.assertIsNotNone(drop_down.pop_up_widget)

        self.assertIsNone(stack.keypress(size, "esc"))
        self.assertIsNone(drop_down.pop_up_widget)
        self.assertEqual(1, stack.depth)

        self.assertIsNone(stack.keypress(size, "esc"))
        self.assertEqual(0, stack.depth)

    def test_key_typed_in_edit(self) -> None:
        """An ``Edit`` leaves the key unhandled, so it closes the dialog."""
        stack = urwid.OverlayStack(urwid.SolidFill("."), close_on_menu=True)
        edit = urwid.Edit()
        stack.open(edit)
        stack.keypress(SIZE, "x")
        self.assertEqual("x", edit.edit_text)
        self.assertIsNone(stack.keypress(SIZE, "esc"))
        self.assertEqual(0, stack.depth)


class OverlayStackClickOutsideTest(unittest.TestCase):
    """Closing the top dialog on a press outside it."""

    def test_press_outside(self) -> None:
        """With the flag, a press outside closes the dialog and does not reach the widget under it."""
        for flag in (True, False):
            with self.subTest(close_on_click_outside=flag):
                base = RecordingFill(".")
                stack = urwid.OverlayStack(base, close_on_click_outside=flag)
                dialog = RecordingFill("x")
                stack.open(dialog, width=4, height=1)
                seen = record_closed(stack)

                self.assertEqual(flag, stack.mouse_event(SIZE, "mouse press", 1, 0, 0, True))
                self.assertEqual(0 if flag else 1, stack.depth)
                self.assertEqual([(dialog, None)] if flag else [], seen)
                self.assertEqual([], base.events)
                self.assertEqual([], dialog.events)

    def test_press_inside(self) -> None:
        """A press inside the dialog reaches the dialog and leaves it open."""
        stack = urwid.OverlayStack(urwid.SolidFill("."), close_on_click_outside=True)
        dialog = RecordingFill("x")
        stack.open(dialog, width=4, height=1)
        self.assertTrue(stack.mouse_event(SIZE, "mouse press", 1, 4, 2, True))
        self.assertEqual([("mouse press", 1, 1, 0)], dialog.events)
        self.assertEqual(1, stack.depth)


class OverlayStackCoveredLevelsTest(unittest.TestCase):
    """The widgets under the top dialog."""

    def test_base_keeps_its_focus(self) -> None:
        """A base ``ListBox`` keeps its focus, receives no key and shows no cursor while a dialog is open."""
        listbox = urwid.ListBox(urwid.SimpleFocusListWalker([urwid.Edit(str(n)) for n in range(5)]))
        listbox.focus_position = 2
        stack = urwid.OverlayStack(listbox)
        self.assertIsNotNone(stack.render(SIZE, focus=True).cursor)

        stack.open(urwid.Text("dialog"))
        self.assertEqual("down", stack.keypress(SIZE, "down"))
        self.assertEqual(2, listbox.focus_position)
        self.assertIsNone(stack.render(SIZE, focus=True).cursor)

        stack.close()
        self.assertIsNone(stack.keypress(SIZE, "down"))
        self.assertEqual(3, listbox.focus_position)


class OverlayStackSizingDefaultsTest(unittest.TestCase):
    """The ``width`` and ``height`` that ``open()`` picks from the dialog's sizing."""

    def test_defaults_by_sizing(self) -> None:
        """Each kind of widget gets a width and a height its sizing supports, and renders."""
        relative = urwid.WHSettings.RELATIVE
        pack = urwid.WHSettings.PACK
        cases: tuple[tuple[str, Callable[[], urwid.Widget], urwid.WHSettings, urwid.WHSettings], ...] = (
            ("Text", lambda: urwid.Text("text"), relative, pack),
            ("Pile of Text and Button", lambda: urwid.Pile([urwid.Text("text"), urwid.Button("ok")]), relative, pack),
            ("LineBox of Pile", lambda: urwid.LineBox(urwid.Pile([urwid.Text("text")])), relative, pack),
            ("ListBox", lambda: urwid.ListBox([urwid.Text("text")]), relative, relative),
            ("LineBox of ListBox", lambda: urwid.LineBox(urwid.ListBox([urwid.Text("text")])), relative, relative),
            ("Filler of Pile", lambda: urwid.Filler(urwid.Pile([urwid.Text("text")])), relative, pack),
            ("BigText", lambda: urwid.BigText("x", urwid.Thin3x3Font()), pack, pack),
            ("AttrMap of BigText", lambda: urwid.AttrMap(urwid.BigText("x", urwid.Thin3x3Font()), "a"), pack, pack),
            ("LineBox of BigText", lambda: urwid.LineBox(urwid.BigText("x", urwid.Thin3x3Font())), pack, pack),
        )
        for label, make_widget, width_type, height_type in cases:
            with self.subTest(label):
                stack = urwid.OverlayStack(urwid.SolidFill("."))
                stack.open(make_widget())
                overlay = top_overlay(stack)
                self.assertEqual(width_type, overlay.width_type)
                self.assertEqual(height_type, overlay.height_type)
                self.assertEqual(10, len(render_text(stack, (40, 10))))

    def test_explicit_options(self) -> None:
        """Given layout options reach the ``Overlay`` unchanged, and an invalid one opens nothing."""
        stack = urwid.OverlayStack(urwid.SolidFill("."))
        stack.open(urwid.Text("text"), width=(urwid.RELATIVE, 50), height=(urwid.RELATIVE, 50), shrink_to_fit=True)
        overlay = top_overlay(stack)
        self.assertEqual((urwid.WHSettings.RELATIVE, 50), (overlay.width_type, overlay.width_amount))
        self.assertEqual((urwid.WHSettings.RELATIVE, 50), (overlay.height_type, overlay.height_amount))
        self.assertIs(True, overlay.shrink_to_fit)

        for label, options, error in (
            ("unknown width", {"width": ("bogus", 1)}, urwid.OverlayError),
            ("unknown align", {"align": "bogus"}, ValueError),
        ):
            with self.subTest(label), self.assertRaises(error):
                stack.open(urwid.Text("bad"), **options)  # type: ignore[arg-type]
            self.assertEqual(1, stack.depth)
            self.assertIs(overlay, top_overlay(stack))


class OverlayStackPropertiesTest(unittest.TestCase):
    """The writable properties."""

    def test_base_at_depth_0(self) -> None:
        """Replacing the base at depth 0 shows the new base."""
        stack = urwid.OverlayStack(urwid.SolidFill("."))
        render_text(stack, SIZE)
        new_base = urwid.SolidFill(":")
        stack.base = new_base
        self.assertIs(new_base, stack.base)
        self.assertEqual([":" * 10] * 5, render_text(stack, SIZE))

    def test_base_at_depth_2(self) -> None:
        """Replacing the base with dialogs open shows it under them and keeps them open."""
        stack = urwid.OverlayStack(urwid.SolidFill("."))
        levels = (urwid.Text("1"), urwid.Text("2"))
        for widget in levels:
            stack.open(widget, width=1)
        before = render_text(stack, SIZE)
        stack.base = urwid.SolidFill(":")
        self.assertEqual(levels, stack.levels)
        self.assertEqual([row.replace(".", ":") for row in before], render_text(stack, SIZE))

        stack.close()
        stack.close()
        self.assertEqual([":" * 10] * 5, render_text(stack, SIZE))

    def test_flags_apply_to_later_dialogs(self) -> None:
        """Changing a flag leaves the open dialogs as they are and applies to the next ``open()``."""
        stack = urwid.OverlayStack(urwid.SolidFill("."))
        stack.open(urwid.Text("1"), width=1, height=1)
        stack.close_on_menu = True
        stack.close_on_click_outside = True
        self.assertTrue(stack.close_on_menu)
        self.assertTrue(stack.close_on_click_outside)
        self.assertEqual("esc", stack.keypress(SIZE, "esc"))
        self.assertFalse(stack.mouse_event(SIZE, "mouse press", 1, 0, 0, True))
        self.assertEqual(1, stack.depth)

        stack.open(urwid.Text("2"), width=1, height=1)
        self.assertIsNone(stack.keypress(SIZE, "esc"))
        self.assertEqual(1, stack.depth)
        stack.open(urwid.Text("3"), width=1, height=1)
        self.assertTrue(stack.mouse_event(SIZE, "mouse press", 1, 0, 0, True))
        self.assertEqual(1, stack.depth)


class OverlayStackLeakTest(unittest.TestCase):
    """Closed dialogs are freed."""

    def test_closed_level_is_freed(self) -> None:
        """After ``close()`` neither the dialog's overlay nor its widget is kept alive by the stack."""
        stack = urwid.OverlayStack(urwid.SolidFill("."), close_on_menu=True, close_on_click_outside=True)
        widget = urwid.Text("1")
        stack.open(widget, on_close=lambda _result: None)
        refs = (weakref.ref(top_overlay(stack)), weakref.ref(widget))
        render_text(stack, SIZE)
        stack.keypress(SIZE, "esc")
        del widget
        self.assertEqual(0, stack.depth)
        self.assertEqual(0, collect_and_count_alive(refs))

    @unittest.skipUnless(sys.implementation.name == "cpython", "relies on reference counting freeing at once")
    def test_dropped_stack_is_freed_with_dialogs_open(self) -> None:
        """An open dialog's close handlers do not keep the stack alive, so no collector run is needed to free it."""
        stack = urwid.OverlayStack(urwid.SolidFill("."), close_on_menu=True, close_on_click_outside=True)
        stack.open(urwid.Text("1"))
        stack.open(urwid.Text("2"))
        render_text(stack, SIZE)
        ref = weakref.ref(stack)
        was_enabled = gc.isenabled()
        gc.disable()
        try:
            del stack
            self.assertIsNone(ref())
        finally:
            if was_enabled:
                gc.enable()

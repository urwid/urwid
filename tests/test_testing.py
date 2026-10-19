from __future__ import annotations

import asyncio
import typing
import unittest

import urwid
import urwid.testing
from urwid.display.common import INPUT_DESCRIPTORS_CHANGED
from urwid.util import set_temporary_encoding

if typing.TYPE_CHECKING:
    from collections.abc import Hashable


class FocusText(urwid.Widget):
    """Flow widget showing whether it was rendered in focus."""

    _sizing = frozenset((urwid.Sizing.FLOW,))

    def rows(self, size: tuple[int], focus: bool = False) -> int:
        return 1

    def render(self, size: tuple[int], focus: bool = False) -> urwid.Canvas:
        (maxcol,) = size
        return urwid.Text("on" if focus else "off").render((maxcol,))


class LyingFlow(urwid.Widget):
    """Flow widget whose rows() reports one row more than it renders."""

    _sizing = frozenset((urwid.Sizing.FLOW,))
    ignore_focus = True

    def rows(self, size: tuple[int], focus: bool = False) -> int:
        return 2

    def render(self, size: tuple[int], focus: bool = False) -> urwid.Canvas:
        (maxcol,) = size
        return urwid.SolidCanvas("x", maxcol, 1)


class CursorOutside(urwid.Widget):
    """Widget of one sizing mode whose canvas has a cursor right of its last column."""

    def __init__(self, sizing: urwid.Sizing) -> None:
        super().__init__()
        self._sizing = frozenset((sizing,))

    def rows(self, size: tuple[int], focus: bool = False) -> int:
        return 1

    def pack(self, size: tuple[()] | tuple[int] | tuple[int, int] = (), focus: bool = False) -> tuple[int, int]:
        return 2, 1

    def render(self, size: tuple[()] | tuple[int] | tuple[int, int], focus: bool = False) -> urwid.Canvas:
        cols = size[0] if size else 2
        rows = size[1] if len(size) == 2 else 1
        canvas = urwid.CompositeCanvas(urwid.SolidCanvas("x", cols, rows))
        canvas.cursor = (cols, 0)
        return canvas


class CursorMismatch(urwid.Widget):
    """Flow widget showing a cursor in focus that get_cursor_coords() does not report."""

    _sizing = frozenset((urwid.Sizing.FLOW,))

    def rows(self, size: tuple[int], focus: bool = False) -> int:
        return 1

    def render(self, size: tuple[int], focus: bool = False) -> urwid.Canvas:
        (maxcol,) = size
        canvas = urwid.CompositeCanvas(urwid.SolidCanvas("x", maxcol, 1))
        if focus and maxcol:
            canvas.cursor = (0, 0)
        return canvas

    def get_cursor_coords(self, size: tuple[int]) -> tuple[int, int] | None:
        return None


class PackLiar(urwid.Widget):
    """Fixed widget whose pack(()) reports a wider size than it renders."""

    _sizing = frozenset((urwid.Sizing.FIXED,))

    def pack(self, size: tuple[()] = (), focus: bool = False) -> tuple[int, int]:
        return 3, 1

    def render(self, size: tuple[()], focus: bool = False) -> urwid.Canvas:
        return urwid.SolidCanvas("x", 2, 1)


class NoSizing(urwid.Widget):
    """Widget supporting no sizing mode."""

    _sizing = frozenset()


class NarrowWhenRowless(urwid.Widget):
    """Box widget rendering a canvas of no columns when it has no rows."""

    _sizing = frozenset((urwid.Sizing.BOX,))

    def render(self, size: tuple[int, int], focus: bool = False) -> urwid.Canvas:
        maxcol, maxrow = size
        return urwid.SolidCanvas("x", maxcol if maxrow else 0, maxrow)


class KeyTranslator(urwid.Widget):
    """Widget handling ``"a"``, translating ``"x"`` to ``"y"`` and returning every other key."""

    _selectable = True
    _sizing = frozenset((urwid.Sizing.FLOW,))

    def keypress(self, size: tuple[int], key: str) -> str | None:
        if key == "a":
            return None
        if key == "x":
            return "y"
        return key


class MouseRecorder(urwid.Widget):
    """Widget recording the arguments of each mouse event and returning a scripted value."""

    _sizing = frozenset((urwid.Sizing.FLOW,))

    def __init__(self, result: bool | None) -> None:
        super().__init__()
        self.result = result
        self.events: list[tuple[typing.Any, ...]] = []

    def mouse_event(
        self,
        size: tuple[int],
        event: str,
        button: int,
        col: int,
        row: int,
        focus: bool,
    ) -> bool | None:
        self.events.append((size, event, button, col, row, focus))
        return self.result


class RenderTextTest(unittest.TestCase):
    def test_focus(self) -> None:
        for focus, expected in ((False, ["off "]), (True, ["on  "])):
            with self.subTest(focus=focus):
                self.assertEqual(expected, urwid.testing.render_text(FocusText(), (4,), focus=focus))

    def test_strip(self) -> None:
        widget = urwid.Text("ab cd")
        self.assertEqual(["ab ", "cd "], urwid.testing.render_text(widget, (3,)))
        self.assertEqual(["ab", "cd"], urwid.testing.render_text(widget, (3,), strip=True))

    def test_box_and_fixed_sizes(self) -> None:
        self.assertEqual(["x", " "], urwid.testing.render_text(urwid.Filler(urwid.Text("x"), "top"), (1, 2)))
        self.assertEqual(["ab"], urwid.testing.render_text(urwid.Text("ab"), ()))

    def test_decodes_with_the_target_encoding(self) -> None:
        widget = urwid.Text("a\N{LATIN SMALL LETTER E WITH ACUTE}")
        for encoding, expected in (("utf-8", ["a\N{LATIN SMALL LETTER E WITH ACUTE} "]), ("ascii", ["a? "])):
            with self.subTest(encoding), set_temporary_encoding(encoding):
                urwid.CanvasCache.clear()
                self.assertEqual(expected, urwid.testing.render_text(widget, (3,)))


class RenderRunsTest(unittest.TestCase):
    def test_merges_runs_split_by_character_set(self) -> None:
        widget = urwid.Text("a\N{BOX DRAWINGS LIGHT HORIZONTAL}b")
        with set_temporary_encoding("ascii"):
            urwid.CanvasCache.clear()
            # The line-drawing character is drawn from the DEC special graphics set, in a run of its own.
            self.assertEqual(3, len(next(iter(widget.render((4,)).content()))))
            self.assertEqual([[(None, "aqb ")]], urwid.testing.render_runs(widget, (4,)))

    def test_keeps_distinct_attributes_apart(self) -> None:
        widget = urwid.Text([("a", "x"), ("a", "y"), ("b", "z")])
        self.assertEqual([[("a", "xy"), ("b", "z"), (None, "  ")]], urwid.testing.render_runs(widget, (5,)))

    def test_nested_attr_maps_give_a_layered_attribute(self) -> None:
        widget = urwid.AttrMap(urwid.AttrMap(urwid.Text("x"), "inner"), "outer")
        self.assertEqual(
            [[(urwid.LayeredAttr("inner", "outer"), "x")]],
            urwid.testing.render_runs(widget, (1,)),
        )

    def test_focus(self) -> None:
        widget = urwid.AttrMap(urwid.SelectableIcon("x"), "normal", "focused")
        self.assertEqual([[("normal", "x")]], urwid.testing.render_runs(widget, (1,)))
        self.assertEqual([[("focused", "x")]], urwid.testing.render_runs(widget, (1,), focus=True))

    def test_no_rows(self) -> None:
        self.assertEqual([], urwid.testing.render_runs(urwid.SolidFill(), (0, 0)))


class ResolveAttrTest(unittest.TestCase):
    palette: typing.ClassVar[list[tuple[Hashable, ...]]] = [
        ("x", "dark red", "light gray", "bold", "#f00", "#000"),
        ("over", "inherit", "dark blue"),
    ]

    def test_colors_select_the_palette_column(self) -> None:
        for colors, expected in (
            (1, urwid.AttrSpec("default,bold", "default", colors=1)),
            (16, urwid.AttrSpec("dark red", "light gray", colors=16)),
            (88, urwid.AttrSpec("#f00", "#000", colors=88)),
            (256, urwid.AttrSpec("#f00", "#000", colors=256)),
            (2**24, urwid.AttrSpec("#f00", "#000", colors=2**24)),
        ):
            with self.subTest(colors=colors):
                self.assertEqual(expected, urwid.testing.resolve_attr("x", self.palette, colors=colors))

    def test_layered_attribute(self) -> None:
        self.assertEqual(
            urwid.AttrSpec("dark red", "dark blue", colors=16),
            urwid.testing.resolve_attr(urwid.LayeredAttr("over", "x"), self.palette, colors=16),
        )

    def test_unknown_name_gives_default_colors(self) -> None:
        self.assertEqual(
            urwid.AttrSpec("default", "default", colors=16),
            urwid.testing.resolve_attr("missing", self.palette, colors=16),
        )

    def test_unsupported_colors(self) -> None:
        for function in (
            lambda: urwid.testing.resolve_attr("x", self.palette, colors=8),
            lambda: urwid.testing.resolve_runs([], self.palette, colors=8),
        ):
            with self.subTest(function), self.assertRaisesRegex(ValueError, "colors must be one of"):
                function()

    def test_resolve_runs_keeps_text_and_shape(self) -> None:
        runs = [[("x", "ab"), ("missing", "c")], [("x", "d")]]
        x = urwid.AttrSpec("dark red", "light gray", colors=16)
        default = urwid.AttrSpec("default", "default", colors=16)
        self.assertEqual(
            [[(x, "ab"), (default, "c")], [(x, "d")]],
            urwid.testing.resolve_runs(runs, self.palette, colors=16),
        )


class SizingCheckTest(unittest.TestCase):
    def test_consistent_widgets_pass(self) -> None:
        for widget in (
            urwid.SolidFill(),
            urwid.Filler(urwid.Text("x")),
            urwid.Filler(urwid.Edit("> ", "abc")),
            urwid.Edit("> ", "abc"),
            urwid.Text("ab cd"),
            urwid.Pile([urwid.Text("x"), urwid.Edit("> ")]),
            urwid.Columns([urwid.Text("x"), urwid.Edit("> ")]),
        ):
            with self.subTest(widget):
                urwid.testing.check_sizing(widget)

    def test_failures(self) -> None:
        for description, check, message in (
            (
                "rows() differs from the canvas",
                lambda: urwid.testing.check_flow_sizing(LyingFlow()),
                r"^LyingFlow\.render\(\(0,\), focus=False\): canvas rows expected 2, got 1$",
            ),
            (
                "flow cursor outside the canvas",
                lambda: urwid.testing.check_flow_sizing(CursorOutside(urwid.Sizing.FLOW)),
                r"^CursorOutside\.render\(\(0,\), focus=False\): cursor expected inside 0x1 canvas, got \(0, 0\)$",
            ),
            (
                "box cursor outside the canvas",
                lambda: urwid.testing.check_box_sizing(CursorOutside(urwid.Sizing.BOX)),
                r"^CursorOutside\.render\(\(80, 0\), focus=False\): cursor expected inside 80x0 canvas, got \(80, 0\)$",
            ),
            (
                "fixed cursor outside the canvas",
                lambda: urwid.testing.check_fixed_sizing(CursorOutside(urwid.Sizing.FIXED)),
                r"^CursorOutside\.render\(\(\), focus=False\): cursor expected inside 2x1 canvas, got \(2, 0\)$",
            ),
            (
                "pack(()) differs from the canvas",
                lambda: urwid.testing.check_fixed_sizing(PackLiar()),
                r"^PackLiar\.render\(\(\), focus=False\): canvas size expected \(3, 1\) from pack\(\(\)\), got \(2, 1\)$",
            ),
            (
                "empty sizing()",
                lambda: urwid.testing.check_sizing(NoSizing()),
                r"^NoSizing\.sizing\(\) is empty$",
            ),
            (
                "no columns at (cols, 0)",
                lambda: urwid.testing.check_box_sizing(NarrowWhenRowless()),
                r"^NarrowWhenRowless\.render\(\(80, 0\), focus=False\): canvas cols expected 80, got 0$",
            ),
        ):
            with self.subTest(description), self.assertRaisesRegex(AssertionError, message):
                check()

    def test_cursor_differs_from_get_cursor_coords(self) -> None:
        with self.assertRaisesRegex(
            AssertionError,
            r"^CursorMismatch\.render\(\(1,\), focus=True\): cursor expected None from get_cursor_coords, got \(0, 0\)$",
        ):
            urwid.testing.check_flow_sizing(CursorMismatch())

    def test_cached_canvases_do_not_answer_rows(self) -> None:
        """A canvas cached before the check, of the widget or of a wrapped child, does not hide a rows() mismatch."""
        for description, widget in (("widget", LyingFlow()), ("wrapped child", urwid.WidgetWrap(LyingFlow()))):
            with self.subTest(description):
                cached = [widget.render((width,), focus=focus) for width in (0, 1, 80) for focus in (False, True)]
                with self.assertRaisesRegex(AssertionError, "canvas rows expected 2, got 1"):
                    urwid.testing.check_flow_sizing(widget)
                del cached


class PressTest(unittest.TestCase):
    def test_returns_unhandled_keys_in_order(self) -> None:
        self.assertEqual(["b", "y"], urwid.testing.press(KeyTranslator(), (5,), "a", "b", "x"))

    def test_non_selectable_widget(self) -> None:
        self.assertEqual(["a", "enter"], urwid.testing.press(urwid.Text("x"), (5,), "a", "enter"))


class ClickTest(unittest.TestCase):
    def test_result(self) -> None:
        for result, expected in ((None, False), (False, False), (True, True)):
            with self.subTest(result=result):
                self.assertIs(expected, urwid.testing.click(MouseRecorder(result), (5,), 1, 0))

    def test_forwards_arguments(self) -> None:
        widget = MouseRecorder(True)
        urwid.testing.click(widget, (5,), 2, 3)
        urwid.testing.click(widget, (5,), 4, 0, button=3, event="mouse release", focus=False)
        self.assertEqual(
            [((5,), "mouse press", 1, 2, 3, True), ((5,), "mouse release", 3, 4, 0, False)],
            widget.events,
        )


class ScriptedScreenTest(unittest.TestCase):
    def test_manual_draws_record_distinct_frames(self) -> None:
        screen = urwid.testing.ScriptedScreen(size=(6, 1))
        loop = urwid.MainLoop(urwid.Filler(urwid.Edit("> ")), screen=screen)
        with self.assertRaises(IndexError):
            _ = screen.last_text
        loop.draw_screen()
        loop.process_input(["a"])
        loop.draw_screen()
        loop.draw_screen()
        self.assertEqual([(">",), ("> a",)], [tuple(t.rstrip() for t in c.decoded_text) for c in screen.canvases])
        self.assertEqual(3, screen.draw_count)
        self.assertEqual(["> a   "], screen.last_text)

    def test_unchanged_screen_adds_no_frame(self) -> None:
        screen = urwid.testing.ScriptedScreen(size=(6, 1))
        loop = urwid.MainLoop(urwid.Filler(urwid.Edit("> ")), screen=screen)
        loop.draw_screen()
        loop.process_input(["f5"])
        loop.draw_screen()
        self.assertEqual(1, len(screen.canvases))
        self.assertEqual(2, screen.draw_count)

    def test_cursor_move_adds_a_frame(self) -> None:
        screen = urwid.testing.ScriptedScreen(size=(6, 1))
        loop = urwid.MainLoop(urwid.Filler(urwid.Edit("> ", "ab")), screen=screen)
        loop.draw_screen()
        loop.process_input(["left"])
        loop.draw_screen()
        first, second = screen.canvases
        self.assertEqual(first.decoded_text, second.decoded_text)
        self.assertEqual((4, 0), first.cursor)
        self.assertEqual((3, 0), second.cursor)

    def test_resize_adds_a_frame_without_rows(self) -> None:
        screen = urwid.testing.ScriptedScreen(size=(5, 0))
        loop = urwid.MainLoop(urwid.SolidFill(), screen=screen)
        loop.draw_screen()
        screen.size = (7, 0)
        loop.process_input(["window resize"])
        loop.screen_size = None
        loop.draw_screen()
        self.assertEqual([5, 7], [canvas.cols() for canvas in screen.canvases])

    def test_run(self) -> None:
        def make_loop() -> urwid.EventLoop:
            asyncio_loop = asyncio.new_event_loop()
            self.addCleanup(asyncio_loop.close)
            return urwid.AsyncioEventLoop(loop=asyncio_loop)

        draw_counts = {}
        for name, event_loop_factory in (("select", urwid.SelectEventLoop), ("asyncio", make_loop)):
            with self.subTest(name):
                screen = urwid.testing.ScriptedScreen(size=(6, 1), inputs=[["a", "b"], ["f5"], ["backspace"]])
                urwid.MainLoop(urwid.Filler(urwid.Edit("> ")), screen=screen, event_loop=event_loop_factory()).run()
                self.assertEqual(
                    [(">",), ("> ab",), ("> a",)],
                    [tuple(t.rstrip() for t in c.decoded_text) for c in screen.canvases],
                )
                self.assertFalse(screen.started)
                self.assertIsNone(screen._event_loop)
                self.assertIsNone(screen._feed_handle)
                draw_counts[name] = screen.draw_count
        # AsyncioEventLoop runs the idle callbacks after the start alarm as well, so it draws the first frame twice.
        self.assertLess(draw_counts["select"], draw_counts["asyncio"])

    def test_run_with_resize(self) -> None:
        screen = urwid.testing.ScriptedScreen(size=(5, 1), inputs=[["r"], ["window resize"]])

        def resize(key: str | tuple[str, int, int, int]) -> bool:
            screen.size = (3, 2)
            return True

        urwid.MainLoop(urwid.Filler(urwid.Text("ab cd")), screen=screen, unhandled_input=resize).run()
        self.assertEqual([["ab cd"], ["ab ", "cd "]], [list(canvas.decoded_text) for canvas in screen.canvases])

    def test_palette_through_main_loop(self) -> None:
        screen = urwid.testing.ScriptedScreen(size=(2, 1))
        loop = urwid.MainLoop(
            urwid.Filler(urwid.Text(("x", "hi"))),
            palette=[("x", "dark red", "default")],
            screen=screen,
        )
        loop.draw_screen()
        ((run,),) = urwid.testing.render_runs(urwid.Filler(urwid.Text(("x", "hi"))), (2, 1))
        self.assertEqual(urwid.AttrSpec("dark red", "default", colors=16), screen.resolve_attr(run[0], 0))

    def test_run_continues_after_the_input_hook_is_reset(self) -> None:
        """Resetting the input hook while a batch is pending cancels it, and the next draw schedules it again."""
        screen = urwid.testing.ScriptedScreen(size=(6, 1), inputs=[["f5"], ["a"]])

        def reset(key: str | tuple[str, int, int, int]) -> bool:
            loop.draw_screen()  # schedules the next batch
            urwid.emit_signal(screen, INPUT_DESCRIPTORS_CHANGED)
            return True

        loop = urwid.MainLoop(urwid.Filler(urwid.Edit("> ")), screen=screen, unhandled_input=reset)
        loop.run()
        self.assertEqual(["> a   "], screen.last_text)

    def test_batch_that_is_not_a_sequence_of_inputs_is_rejected(self) -> None:
        for batch in ("enter", b"ab", ("mouse press", 1, 0, 0), [1]):
            with self.subTest(batch), self.assertRaisesRegex(TypeError, "each input batch must be a sequence"):
                urwid.testing.ScriptedScreen(inputs=[["a"], batch])
        screen = urwid.testing.ScriptedScreen(inputs=[("a", ("mouse press", 1, 0, 0))])
        self.assertEqual(["a", ("mouse press", 1, 0, 0)], screen.get_input(False))

    def test_get_input(self) -> None:
        screen = urwid.testing.ScriptedScreen(inputs=[["a", ("mouse press", 1, 2, 3)], ["b"]])
        self.assertEqual(["a", ("mouse press", 1, 2, 3)], screen.get_input(False))
        self.assertEqual((["b"], []), screen.get_input(True))
        with self.assertRaises(urwid.ExitMainLoop):
            screen.get_input(True)

    def test_unhook_cancels_the_pending_feed(self) -> None:
        event_loop = urwid.SelectEventLoop()
        fed: list[list[typing.Any]] = []
        screen = urwid.testing.ScriptedScreen(inputs=[["a"]])
        screen.hook_event_loop(event_loop, lambda keys, raw: fed.append(keys))
        screen.draw_screen((80, 24), urwid.SolidFill().render((80, 24)))
        self.assertEqual(1, len(event_loop._alarms))
        screen.unhook_event_loop(event_loop)
        self.assertEqual([], event_loop._alarms)
        self.assertEqual([], fed)

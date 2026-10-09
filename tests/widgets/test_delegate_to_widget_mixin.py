from __future__ import annotations

import itertools
import typing
import unittest

import urwid
from urwid.util import get_encoding
from urwid.widget.widget import delegate_to_widget_mixin


FORWARDED = (
    "render",
    "selectable",
    "sizing",
    "pack",
    "keypress",
    "mouse_event",
    "rows",
    "get_cursor_coords",
    "get_pref_col",
    "move_cursor_to_coords",
)
OPTIONAL = ("rows", "get_cursor_coords", "get_pref_col", "move_cursor_to_coords")
USERS: tuple[type[urwid.Widget], ...] = (
    urwid.WidgetWrap,
    urwid.AttrMap,
    urwid.WidgetPlaceholder,
    urwid.PopUpLauncher,
    urwid.LineBox,
)


def mixin_of(cls: type) -> type:
    """Return the class delegate_to_widget_mixin() built for *cls*."""
    (mixin,) = (base for base in cls.__bases__ if base.__name__ == "DelegateToWidgetMixin")
    return mixin


def owner(cls: type, name: str) -> type:
    """Return the first class in the MRO of *cls* that defines *name*."""
    return next(klass for klass in cls.__mro__ if name in vars(klass))


class Recorder(urwid.Widget):
    """Flow widget that records every call made to it."""

    _sizing = frozenset((urwid.FLOW,))
    _selectable = True

    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def render(self, size: tuple[int], focus: bool = False) -> urwid.Canvas:
        self.calls.append(("render", (size, focus)))
        return urwid.Text(self.name).render(size, focus)

    def rows(self, size: tuple[int], focus: bool = False) -> int:
        self.calls.append(("rows", (size, focus)))
        return 1

    def keypress(self, size: tuple[int], key: str) -> str | None:
        self.calls.append(("keypress", (size, key)))
        return key

    def get_cursor_coords(self, size: tuple[int]) -> tuple[int, int] | None:
        self.calls.append(("get_cursor_coords", (size,)))
        return (0, 0)

    def get_pref_col(self, size: tuple[int]) -> int | None:
        self.calls.append(("get_pref_col", (size,)))
        return 0

    def move_cursor_to_coords(self, size: tuple[int], x: int, y: int) -> bool:
        self.calls.append(("move_cursor_to_coords", (size, x, y)))
        return True


class FactoryTest(unittest.TestCase):
    def test_distinct_class_per_call(self) -> None:
        first = delegate_to_widget_mixin("_w")
        second = delegate_to_widget_mixin("_w")
        self.assertIsNot(first, second)
        self.assertTrue(issubclass(first, urwid.Widget))
        self.assertEqual(
            len(set(map(mixin_of, USERS))),
            len(USERS),
            "every user of the factory owns its own generated class",
        )

    def test_dotted_attribute_path(self) -> None:
        class Holder:
            def __init__(self, child: urwid.Widget) -> None:
                self.child = child

        class Deep(delegate_to_widget_mixin("holder.child")):
            def __init__(self, child: urwid.Widget) -> None:
                super().__init__()
                self.holder = Holder(child)

        child = Recorder("deep")
        deep = Deep(child)
        self.assertEqual(1, deep.rows((5,)))
        self.assertEqual([b"deep "], deep.render((5,)).text)
        self.assertEqual([("rows", ((5,), False)), ("render", ((5,), False))], child.calls)

    def test_two_factory_bases_keep_their_own_target(self) -> None:
        class ToFirst(delegate_to_widget_mixin("first")):
            pass

        class ToSecond(delegate_to_widget_mixin("second")):
            def rows(self, size: tuple[int], focus: bool = False) -> int:
                return super().rows(size, focus)

        class Both(ToFirst, ToSecond):
            def __init__(self) -> None:
                super().__init__()
                self.first = Recorder("first")
                self.second = Recorder("second")

        both = Both()
        both.keypress((5,), "x")
        self.assertEqual([("keypress", ((5,), "x"))], both.first.calls)
        self.assertEqual([], both.second.calls)
        self.assertEqual(1, ToSecond.rows(both, (5,)))
        self.assertEqual([("rows", ((5,), False))], both.second.calls)


class HybridTest(unittest.TestCase):
    # Per class, the owner of every forwarded name that is not the class's own mixin.
    EXCEPTIONS: typing.ClassVar[dict[type, dict[str, type]]] = {
        urwid.AttrMap: {"render": urwid.AttrMap},
        urwid.PopUpLauncher: {"render": urwid.PopUpLauncher},
        urwid.LineBox: {"selectable": urwid.WidgetDecoration, "sizing": urwid.WidgetDecoration},
    }

    def expected_owner(self, first: type, second: type, name: str) -> type:
        if first is urwid.LineBox and second is not urwid.WidgetWrap:
            # The second class puts its mixin before WidgetDecoration, so it wins over LineBox's own bases.
            return self.EXCEPTIONS.get(second, {}).get(name, mixin_of(second))
        return self.EXCEPTIONS.get(first, {}).get(name, mixin_of(first))

    def test_owners_single(self) -> None:
        for cls, name in itertools.product(USERS, FORWARDED):
            with self.subTest(cls=cls.__name__, name=name):
                self.assertIs(self.EXCEPTIONS.get(cls, {}).get(name, mixin_of(cls)), owner(cls, name))

    def test_owners_pairs(self) -> None:
        for first, second in itertools.permutations(USERS, 2):
            hybrid = type("Hybrid", (first, second), {})
            for name in FORWARDED:
                with self.subTest(first=first.__name__, second=second.__name__, name=name):
                    self.assertIs(self.expected_owner(first, second, name), owner(hybrid, name))

    def test_linebox_attrmap_render_is_attrmap(self) -> None:
        hybrid = type("Hybrid", (urwid.LineBox, urwid.AttrMap), {})
        self.assertIs(urwid.AttrMap, owner(hybrid, "render"))
        hybrid = type("Hybrid", (urwid.AttrMap, urwid.LineBox), {})
        self.assertIs(urwid.AttrMap, owner(hybrid, "render"))


class Intermediate(urwid.WidgetWrap[Recorder]):
    """Downstream-style subclass that records its overrides and chains through super()."""

    def __init__(self, w: Recorder) -> None:
        super().__init__(w)
        self.trace: list[str] = []

    def rows(self, size: tuple[int], focus: bool = False) -> int:
        self.trace.append("rows")
        return super().rows(size, focus=focus)

    def get_cursor_coords(self, size: tuple[int]) -> tuple[int, int] | None:
        self.trace.append("get_cursor_coords")
        return super().get_cursor_coords(size)

    def move_cursor_to_coords(self, size: tuple[int], col: int, row: int) -> bool:
        self.trace.append("move_cursor_to_coords")
        return super().move_cursor_to_coords(size, col, row)

    def render(self, size: tuple[int], focus: bool = False) -> urwid.Canvas:
        self.trace.append("render")
        return super().render(size, focus=focus)

    def keypress(self, size: tuple[int], key: str) -> str | None:
        self.trace.append("keypress")
        return super().keypress(size, key)


class BehaviourTest(unittest.TestCase):
    def test_super_chain_reaches_delegate(self) -> None:
        inner = Recorder("inner")
        wrap = Intermediate(inner)

        self.assertEqual(1, wrap.rows((5,), focus=True))
        self.assertEqual((0, 0), wrap.get_cursor_coords((5,)))
        self.assertTrue(wrap.move_cursor_to_coords((5,), 1, 0))
        self.assertIsInstance(wrap.render((5,), focus=True), urwid.CompositeCanvas)
        self.assertEqual("x", wrap.keypress((5,), "x"))

        self.assertEqual(["rows", "get_cursor_coords", "move_cursor_to_coords", "render", "keypress"], wrap.trace)
        self.assertEqual(
            [
                ("rows", ((5,), True)),
                ("get_cursor_coords", ((5,),)),
                ("move_cursor_to_coords", ((5,), 1, 0)),
                ("render", ((5,), True)),
                ("keypress", ((5,), "x")),
            ],
            inner.calls,
        )


class DescriptorTest(unittest.TestCase):
    def test_saved_callable_keeps_old_delegate(self) -> None:
        old = Recorder("old")
        new = Recorder("new")
        wrap = urwid.WidgetWrap(old)
        saved = {name: getattr(wrap, name) for name in ("pack", "selectable", "sizing", "mouse_event", "rows")}

        wrap._w = new

        for name, method in saved.items():
            with self.subTest(name=name):
                self.assertIs(old, method.__self__)
                self.assertIs(new, getattr(wrap, name).__self__)
        saved["rows"]((5,))
        self.assertEqual([("rows", ((5,), False))], old.calls)
        self.assertEqual([], new.calls)

    def test_bound_method_of_delegate(self) -> None:
        inner = Recorder("inner")
        wrap = urwid.WidgetWrap(inner)
        self.assertIs(inner, wrap.pack.__self__)
        self.assertEqual(inner.pack, wrap.pack)
        self.assertEqual(inner.get_pref_col, wrap.get_pref_col)


class OptionalApiTest(unittest.TestCase):
    def test_absent_on_box_delegate(self) -> None:
        wrap = urwid.WidgetWrap(urwid.SolidFill("x"))
        for name in OPTIONAL:
            with self.subTest(name=name):
                self.assertFalse(hasattr(wrap, name))
                with self.assertRaises(AttributeError):
                    getattr(wrap, name)

    def test_present_on_edit_delegate(self) -> None:
        edit = urwid.Edit("a: ", "hello")
        wrap = urwid.WidgetWrap(edit)
        for name in OPTIONAL:
            with self.subTest(name=name):
                self.assertTrue(hasattr(wrap, name))
        self.assertEqual(edit.rows((10,)), wrap.rows((10,)))
        self.assertEqual(edit.get_cursor_coords((10,)), wrap.get_cursor_coords((10,)))
        self.assertEqual(edit.get_pref_col((10,)), wrap.get_pref_col((10,)))
        self.assertTrue(wrap.move_cursor_to_coords((10,), 4, 0))
        self.assertEqual(1, edit.edit_pos)


class LineBoxTest(unittest.TestCase):
    def setUp(self) -> None:
        self.old_encoding = get_encoding()
        urwid.set_encoding("utf-8")

    def tearDown(self) -> None:
        urwid.set_encoding(self.old_encoding)

    def test_follows_original_widget(self) -> None:
        box = urwid.LineBox(urwid.Text("x"))
        self.assertFalse(box.selectable())
        self.assertEqual(frozenset((urwid.FLOW, urwid.FIXED)), box.sizing())
        self.assertEqual(["┌───┐", "│x  │", "└───┘"], [line.decode("utf-8") for line in box.render((5,)).text])

        box.original_widget = urwid.Edit("y")
        self.assertTrue(box.selectable())
        self.assertEqual(frozenset((urwid.FLOW,)), box.sizing())
        self.assertEqual(["┌───┐", "│y  │", "└───┘"], [line.decode("utf-8") for line in box.render((5,)).text])

    def test_render_cache_invalidated_on_replacement(self) -> None:
        box = urwid.LineBox(urwid.Text("a"))
        first = box.render((5,))
        self.assertIs(first, box.render((5,)))
        box.original_widget = urwid.Text("b")
        self.assertIsNot(first, box.render((5,)))


if __name__ == "__main__":
    unittest.main()

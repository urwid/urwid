from __future__ import annotations

import dataclasses
import gc
import sys
import typing
import unittest
import weakref

import urwid
from urwid import MenuItem

if typing.TYPE_CHECKING:
    from collections.abc import Iterable

MARKED = (
    MenuItem("(O)pen", "open", key="o"),
    MenuItem("Re(n)ame", "rename", enabled=False, key="n"),
    None,
    MenuItem("(D)elete", "delete", key="d"),
    MenuItem("(P)roperties...", "props", key="p"),
    None,
    MenuItem("E(x)it", "exit", key="x"),
)
SEND_TO = (
    MenuItem("(M)ail", "mail", key="m"),
    MenuItem("(P)rinter", "printer", key="p"),
    None,
    MenuItem("(C)lipboard", "clipboard", key="c"),
)
WITH_SUBMENU = (
    MenuItem("(O)pen", "open", key="o"),
    MenuItem("(S)end to", submenu=SEND_TO, key="s"),
    None,
    MenuItem("(D)elete", "delete", key="d"),
)


def screen(menu: urwid.Widget, rows_before: int = 1, *, right: bool = False) -> urwid.PopUpTarget:
    """Return a screen with `rows_before` text rows, then the 9-column launcher row, then a status row."""
    rows: list[urwid.Widget] = [urwid.Text(f"line {index}") for index in range(rows_before)]
    rows.append(urwid.Padding(menu, "right" if right else "left", 9, right=3 if right else 0))
    rows.append(urwid.Text("status: -"))
    return urwid.PopUpTarget(urwid.Filler(urwid.Pile(rows, focus_item=rows_before), "top"))


def keys(target: urwid.Widget, size: tuple[int, int], *pressed: str) -> None:
    """Render `target`, then press each key, rendering after it as a main loop does."""
    target.render(size, focus=True)
    for key in pressed:
        target.keypress(size, key)
        target.render(size, focus=True)


def lines(target: urwid.Widget, size: tuple[int, int]) -> list[str]:
    return [line.decode() for line in target.render(size, focus=True).text]


def attributes(target: urwid.Widget, size: tuple[int, int], row: int, columns: Iterable[int]) -> set[object]:
    """Return the display attributes of `columns` on screen row `row`."""
    wanted = set(columns)
    found: set[object] = set()
    col = 0
    for attr, _cs, text in list(target.render(size, focus=True).content())[row]:
        width = len(text.decode())
        if wanted & set(range(col, col + width)):
            found.add(attr)
        col += width
    return found


def record(menu: urwid.ActionMenu) -> list[tuple[str, object]]:
    """Connect a recorder to every signal of `menu` and return the list it fills."""
    sent: list[tuple[str, object]] = []
    urwid.connect_signal(menu, "open", lambda _w: sent.append(("open", None)))
    urwid.connect_signal(menu, "close", lambda _w: sent.append(("close", None)))
    urwid.connect_signal(menu, "action", lambda _w, item: sent.append(("action", item.value)))
    return sent


class MenuItemTest(unittest.TestCase):
    def test_entries_are_normalised(self) -> None:
        menu = urwid.ActionMenu("A", ["Open", None, MenuItem("Delete", "delete")])
        self.assertEqual((MenuItem("Open"), None, MenuItem("Delete", "delete")), menu.items)
        self.assertEqual((MenuItem("Mail"), None), MenuItem("Send", submenu=["Mail", None]).submenu)

    def test_invalid_menus(self) -> None:
        for description, build in (
            ("no entries", lambda: urwid.ActionMenu("A", [])),
            ("separators only", lambda: urwid.ActionMenu("A", [None, None])),
            ("no visible items", lambda: urwid.ActionMenu("A", ["x"], max_visible_items=0)),
            ("duplicate keys", lambda: urwid.ActionMenu("A", [MenuItem("a", key="k"), MenuItem("b", key="k")])),
            ("unknown align", lambda: urwid.ActionMenu("A", ["x"], align="center")),
            ("unknown placement", lambda: urwid.ActionMenu("A", ["x"], placement="middle")),
            ("label and launcher", lambda: urwid.ActionMenu("A", ["x"], launcher=urwid.Text("row"))),
            ("neither label nor launcher", lambda: urwid.ActionMenu(None, ["x"])),
            ("submenu of separators", lambda: MenuItem("Send", submenu=[None])),
            ("label with a line break", lambda: MenuItem("one\ntwo")),
            ("markup with a line break", lambda: urwid.ActionMenu("A", [("attr", "one\ntwo")])),
            ("unknown scroll bar side", lambda: urwid.ActionMenu("A", ["x"], scrollbar_side="top")),
            ("end markers not a pair", lambda: urwid.ActionMenu("A", ["x"], scrollbar_end_markers=("^",))),
        ):
            with self.subTest(description), self.assertRaises(ValueError):
                build()

    def test_unknown_scroll_bar_option(self) -> None:
        """A ScrollBar parameter the pop-up list decides itself is not a keyword argument of the menu."""
        with self.assertRaises(TypeError):
            urwid.ActionMenu("A", ["x"], scrollbar_visible=True)

    def test_empty_submenu_is_no_submenu(self) -> None:
        self.assertEqual(MenuItem("x"), MenuItem("x", submenu=[]))
        self.assertEqual((), MenuItem("x", submenu=iter(())).submenu)
        self.assertEqual(hash(MenuItem("x")), hash(MenuItem("x", submenu=[])))

    def test_open_keys_must_not_be_one_string(self) -> None:
        with self.assertRaises(TypeError):
            urwid.ActionMenu("A", ["x"], open_keys="f10")

    def test_on_action_and_user_data(self) -> None:
        for user_data, expected in ((None, ("delete",)), ("report.txt", ("delete", "report.txt"))):
            with self.subTest(user_data=user_data):
                received: list[tuple[object, ...]] = []

                def on_action(menu: urwid.ActionMenu, item: MenuItem, *data: object) -> None:
                    received.append((item.value, *data))

                menu = urwid.ActionMenu("A", MARKED, on_action=on_action, user_data=user_data)
                target = screen(menu)
                keys(target, (30, 12), "enter", "d")
                self.assertEqual([expected], received)


class LayoutTest(unittest.TestCase):
    def test_label_launcher(self) -> None:
        menu = urwid.ActionMenu("Actions", MARKED)
        self.assertEqual((9, 1), menu.pack())
        self.assertEqual([b"Actions >"], menu.render(()).text)

    def test_empty_indicator_adds_no_column(self) -> None:
        class BarMenu(urwid.ActionMenu):
            menu_indicator = urwid.Text("")

        menu = BarMenu(" File ", ["Open", urwid.MenuItem("Recent", submenu=["a.txt"])])
        self.assertEqual((6, 1), menu.pack())
        self.assertEqual([b" File "], menu.render(()).text)
        target = screen(menu)
        keys(target, (20, 6), "enter")
        # the submenu row has no indicator and no column for one
        self.assertEqual(
            ["┌───────┐           ", "│Open   │           ", "│Recent │           ", "└───────┘           "],
            lines(target, (20, 6))[2:6],
        )

    def test_border_with_tee_separators(self) -> None:
        """D1: the list fits, so it has no scroll bar column; separators join the box sides."""
        menu = urwid.ActionMenu("Actions", MARKED, focus_map="focus", disabled_map="disabled")
        target = screen(menu)
        keys(target, (30, 12), "enter")
        self.assertEqual(
            [
                "line 0                        ",
                "Actions >                     ",
                "┌────────────────┐            ",
                "│(O)pen          │            ",
                "│Re(n)ame        │            ",
                "├────────────────┤            ",
                "│(D)elete        │            ",
                "│(P)roperties... │            ",
                "├────────────────┤            ",
                "│E(x)it          │            ",
                "└────────────────┘            ",
                "                              ",
            ],
            lines(target, (30, 12)),
        )
        self.assertIn("focus", attributes(target, (30, 12), 3, range(1, 17)))
        self.assertEqual({"disabled"}, attributes(target, (30, 12), 4, range(1, 17)))

    def test_scroll_bar_outside_the_border(self) -> None:
        """D2: a list with more rows than it shows has its scroll bar outside the right border."""
        items = (*MARKED[:2], MenuItem("(C)opy", "copy", key="c"), MenuItem("(M)ove", "move", key="m"), *MARKED[2:])
        menu = urwid.ActionMenu("Actions", items, max_visible_items=6, focus_map="focus")
        target = screen(menu)
        keys(target, (30, 12), "enter", "down", "down", "down")
        self.assertEqual(
            [
                "┌────────────────┐            ",
                "│(O)pen          │█           ",
                "│Re(n)ame        │█           ",
                "│(C)opy          │█           ",
                "│(M)ove          │█           ",
                "├────────────────┤            ",
                "│(D)elete        │            ",
                "└────────────────┘            ",
            ],
            lines(target, (30, 12))[2:10],
        )
        self.assertIn("focus", attributes(target, (30, 12), 8, range(1, 17)))

    def test_scroll_bar_options(self) -> None:
        """A wide bar on the left of each list; a child list opens beside its parent, covering neither its bar nor its rows."""
        items = (*WITH_SUBMENU, MenuItem("(C)opy", key="c"), MenuItem("(M)ove", key="m"))
        for description, kwargs, right, opening, expected in (
            (
                "child on the right",
                {},
                False,
                "right",
                [
                    "  ┌────────────┐                        ",
                    "##│(O)pen      │  ┌────────────┐        ",
                    "##│(S)end to  >│##│(M)ail      │        ",
                    "..├────────────┤##│(P)rinter   │        ",
                    "  └────────────┘..├────────────┤        ",
                    "                  └────────────┘        ",
                ],
            ),
            (
                "child on the left",
                {"align": "right"},
                True,
                "left",
                [
                    "status: -              ┌────────────┐   ",
                    "       ┌────────────┐##│(O)pen      │   ",
                    "     ##│(M)ail      │##│(S)end to  >│   ",
                    "     ##│(P)rinter   │..├────────────┤   ",
                    "     ..├────────────┤  └────────────┘   ",
                    "       └────────────┘                   ",
                ],
            ),
            (
                "without a border",
                {"border": False},
                False,
                "right",
                [
                    "##(O)pen                                ",
                    "##(S)end to  >##(M)ail                  ",
                    "..────────────##(P)rinter               ",
                    "              ..────────────            ",
                    "                                        ",
                    "                                        ",
                ],
            ),
        ):
            with self.subTest(description):
                menu = urwid.ActionMenu(
                    "Actions",
                    items,
                    max_visible_items=3,
                    scrollbar_side="left",
                    scrollbar_width=2,
                    scrollbar_thumb_char="#",
                    scrollbar_trough_char=".",
                    **kwargs,
                )
                target = screen(menu, right=right)
                keys(target, (40, 10), "enter", "down", opening)
                self.assertEqual(expected, lines(target, (40, 10))[2:8])

    def test_scroll_bar_end_markers(self) -> None:
        menu = urwid.ActionMenu(
            "Actions", [f"Item {index}" for index in range(6)], max_visible_items=4, scrollbar_end_markers=("^", "v")
        )
        target = screen(menu)
        keys(target, (20, 9), "enter")
        self.assertEqual(
            ["│Item 0 │^", "│Item 1 │█", "│Item 2 │ ", "│Item 3 │v"],
            [line[:10] for line in lines(target, (20, 9))[3:7]],
        )

    def test_key_column(self) -> None:
        """D3: show_keys draws each item's key before its label."""
        plain = [
            None if item is None else MenuItem(item.label.replace("(", "").replace(")", ""), key=item.key)
            for item in MARKED
        ]
        target = screen(urwid.ActionMenu("Actions", plain, show_keys=True))
        keys(target, (30, 12), "enter")
        self.assertEqual(
            ["┌─────────────────┐", "│o  Open          │", "│n  Rename        │", "├─────────────────┤"],
            [line[:19] for line in lines(target, (30, 12))[2:6]],
        )

    def test_list_cut_short_by_the_screen_gets_a_scroll_bar(self) -> None:
        """A list that fits by max_visible_items but not on the screen shows the bar outside the box."""
        target = screen(urwid.ActionMenu("Actions", ["Open", "Copy", "Move", "Delete"]), rows_before=0)
        keys(target, (12, 5))
        keys(target, (12, 5), "enter")
        self.assertEqual(
            ["Actions >   ", "┌──────┐    ", "│Open  │█   ", "│Copy  │    ", "└──────┘    "],
            lines(target, (12, 5)),
        )

    def test_wide_characters(self) -> None:
        target = screen(urwid.ActionMenu("操作", ["開く", MenuItem("削除", key="d")], show_keys=True))
        keys(target, (16, 6), "enter")
        # The key column, two spaces and the widest label in display columns, then the blank column.
        self.assertEqual(
            ["┌────────┐      ", "│   開く │      ", "│d  削除 │      ", "└────────┘      "],
            lines(target, (16, 6))[2:6],
        )

    def test_without_border(self) -> None:
        target = screen(urwid.ActionMenu("Actions", ["Open", None, "Delete"], border=False))
        keys(target, (12, 6), "enter")
        # The list is as wide as the launcher, with no border and no blank rows around it.
        self.assertEqual(
            ["line 0      ", "Actions >   ", "Open        ", "─────────   ", "Delete      "], lines(target, (12, 6))[:5]
        )

    def test_flips_above_near_the_bottom(self) -> None:
        target = screen(urwid.ActionMenu("Actions", ["Open", "Delete"]), rows_before=5)
        keys(target, (12, 7), "enter")
        self.assertEqual(
            ["line 0      ", "┌───────┐   ", "│Open   │   ", "│Delete │   ", "└───────┘   ", "Actions >   "],
            lines(target, (12, 7))[:6],
        )

    def test_align_right(self) -> None:
        """T5: the right edges of the list and the launcher line up."""
        items = [
            MenuItem("Open"),
            MenuItem("Rename", enabled=False),
            None,
            MenuItem("Delete"),
            MenuItem("Properties..."),
        ]
        target = screen(urwid.ActionMenu("Actions", items, align="right"), right=True)
        keys(target, (40, 10), "enter")
        self.assertEqual(
            [
                "                            Actions >   ",
                "status: -            ┌──────────────┐   ",
                "                     │Open          │   ",
            ],
            lines(target, (40, 10))[1:4],
        )

    def test_placement_center(self) -> None:
        """The list opens in the middle of the target, as wide as its own entries rather than the launcher."""
        target = screen(urwid.ActionMenu("Actions", ["Open", "Delete"], placement="center"))
        keys(target, (20, 9), "enter")
        self.assertEqual(
            [
                "line 0              ",
                "Actions >           ",
                "statu┌───────┐      ",
                "     │Open   │      ",
                "     │Delete │      ",
                "     └───────┘      ",
            ],
            lines(target, (20, 9))[:6],
        )

    def test_placement_center_cut_short_by_the_screen(self) -> None:
        """A centred list taller than the target is cut to the target's rows and gets a scroll bar."""
        target = screen(urwid.ActionMenu("Actions", ["Open", "Copy", "Move", "Delete"], placement="center"))
        keys(target, (12, 5), "enter")
        self.assertEqual(
            ["l┌──────┐   ", "A│Open  │█  ", "s│Copy  │█  ", " │Move  │   ", " └──────┘   "],
            lines(target, (12, 5)),
        )


class ChoosingTest(unittest.TestCase):
    def test_choose_by_enter_after_skipping_disabled_and_separators(self) -> None:
        menu = urwid.ActionMenu("A", MARKED)
        sent = record(menu)
        keys(screen(menu), (30, 12), "enter", "down", "enter")
        self.assertEqual([("open", None), ("close", None), ("action", "delete")], sent)
        self.assertIsNone(menu.pop_up_widget)

    def test_home_and_end_skip_disabled_and_separators(self) -> None:
        """Home and End focus the first or last enabled item, with the rows beyond it in the scrolled view."""
        items = (MenuItem("A", "a", enabled=False), *(MenuItem(label, label.lower()) for label in "BCDEFG"), None)
        for pressed, view, expected in (
            (
                ("end",),
                [
                    "\u2502F     \u2502 ",
                    "\u2502G     \u2502 ",
                    "\u251c\u2500\u2500\u2500\u2500\u2500\u2500\u2524\u2588",
                ],
                "g",
            ),
            (("end", "home"), ["\u2502A     \u2502\u2588", "\u2502B     \u2502 ", "\u2502C     \u2502 "], "b"),
        ):
            with self.subTest(pressed=pressed):
                menu = urwid.ActionMenu("A", items)
                sent = record(menu)
                target = screen(menu, 0)
                # Six rows leave three for the list inside its box, so it scrolls.
                keys(target, (20, 6), "enter", *pressed)
                self.assertEqual(view, [line[:9] for line in lines(target, (20, 6))[2:5]])
                keys(target, (20, 6), "enter")
                self.assertEqual([("open", None), ("close", None), ("action", expected)], sent)

    def test_choose_by_click(self) -> None:
        menu = urwid.ActionMenu("A", MARKED)
        sent = record(menu)
        target = screen(menu)
        keys(target, (30, 12), "enter")
        target.mouse_event((30, 12), "mouse press", 1, 3, 7, True)
        self.assertEqual([("open", None), ("close", None), ("action", "props")], sent)

    def test_accelerator_keys(self) -> None:
        for description, key, expected in (
            ("an enabled item's key chooses it", "x", [("open", None), ("close", None), ("action", "exit")]),
            ("a disabled item's key does nothing", "n", [("open", None)]),
            ("other keys do nothing", "q", [("open", None)]),
        ):
            with self.subTest(description):
                menu = urwid.ActionMenu("A", MARKED)
                sent = record(menu)
                keys(screen(menu), (30, 12), "enter", key)
                self.assertEqual(expected, sent)

    def test_closing_without_a_choice(self) -> None:
        for description, close in (
            ("esc", lambda target: target.keypress((30, 12), "esc")),
            ("click outside", lambda target: target.mouse_event((30, 12), "mouse press", 1, 25, 0, True)),
        ):
            with self.subTest(description):
                menu = urwid.ActionMenu("A", MARKED)
                sent = record(menu)
                target = screen(menu)
                keys(target, (30, 12), "enter")
                close(target)
                self.assertEqual([("open", None), ("close", None)], sent)
                self.assertTrue(menu.selectable())

    def test_open_keys_and_buttons(self) -> None:
        menu = urwid.ActionMenu("A", MARKED, open_keys=("m",), open_buttons=(3,))
        target = screen(menu)
        keys(target, (30, 12), "enter")
        self.assertIsNone(menu.pop_up_widget)
        target.mouse_event((30, 12), "mouse press", 1, 0, 1, True)
        self.assertIsNone(menu.pop_up_widget)
        keys(target, (30, 12), "m")
        self.assertIsNotNone(menu.pop_up_widget)

    def test_open_list_does_not_keep_the_menu_alive(self) -> None:
        if sys.implementation.name != "cpython":
            self.skipTest("relies on reference counting freeing the widget")
        menu = urwid.ActionMenu("A", WITH_SUBMENU)
        menu.open_pop_up()
        ref = weakref.ref(menu)
        gc.disable()
        try:
            del menu
            self.assertIsNone(ref())
        finally:
            gc.enable()


FILES = ("notes.md         3 KiB", "report.txt      12 KiB", "todo.org         1 KiB", "photo.png        2 MiB")
CONTEXT = (
    MenuItem("(O)pen", key="o"),
    MenuItem("Re(n)ame", enabled=False, key="n"),
    None,
    MenuItem("(D)elete", key="d"),
)


def file_list(**kwargs: typing.Any) -> tuple[urwid.PopUpTarget, list[urwid.ActionMenu]]:
    """Return a target with a list of file rows, each the launcher of its own context menu opened by "m" or button 3."""
    menus = [
        urwid.ActionMenu(
            None, CONTEXT, launcher=urwid.SelectableIcon(name, 0), open_keys=("m",), open_buttons=(3,), **kwargs
        )
        for name in FILES
    ]
    list_box = urwid.ListBox(urwid.SimpleFocusListWalker(menus))
    list_box.focus_position = 1
    return urwid.PopUpTarget(urwid.Padding(list_box, width=22)), menus


class ContextMenuTest(unittest.TestCase):
    def test_key_opens_at_the_row_edge(self) -> None:
        """C1: opened by a key on the focused row, the list is anchored to the row's left edge."""
        target, _menus = file_list()
        keys(target, (34, 9), "m")
        self.assertEqual(
            ["┌────────────────────┐", "│(O)pen              │"], [line[:22] for line in lines(target, (34, 9))[2:4]]
        )

    def test_click_opens_at_the_row_edge_and_focuses_the_row(self) -> None:
        """C2: a right click on a row that is not focused opens its menu as the key does, and focuses the row."""
        target, menus = file_list()
        target.render((34, 9), focus=True)
        target.mouse_event((34, 9), "mouse press", 3, 9, 2, True)
        self.assertIsNotNone(menus[2].pop_up_widget)
        self.assertEqual(
            ["┌────────────────────┐", "│(O)pen              │"],
            [line[:22] for line in lines(target, (34, 9))[3:5]],
        )
        list_box = target.original_widget.original_widget
        self.assertEqual(2, list_box.focus_position)

    def test_row_keeps_its_other_keys_and_buttons(self) -> None:
        target, menus = file_list()
        keys(target, (34, 9), "down")
        self.assertIsNone(menus[1].pop_up_widget)
        self.assertEqual(2, target.original_widget.original_widget.focus_position)

    def test_align_right_at_the_row_edge(self) -> None:
        """C4: align right lines up the list with the row's right edge."""
        target, _menus = file_list(align="right")
        keys(target, (34, 9), "m")
        self.assertEqual("photo.png  │(O)pen   │", lines(target, (34, 9))[3][:22])

    def test_open_at(self) -> None:
        """open_at() opens below the given cell; a later click on the row opens at the row's edge again."""
        target, menus = file_list()
        target.render((34, 9), focus=True)
        menus[1].open_at(4, 0)
        self.assertEqual("phot│(O)pen   │", lines(target, (34, 9))[3][:15])
        menus[1].close_pop_up()
        target.render((34, 9), focus=True)
        target.mouse_event((34, 9), "mouse press", 3, 9, 1, True)
        self.assertEqual(
            ["┌────────────────────┐", "│(O)pen              │"],
            [line[:22] for line in lines(target, (34, 9))[2:4]],
        )

    def test_open_at_with_placement_center(self) -> None:
        """open_at() opens below the given cell, and an opening key opens the list in the middle."""
        target, menus = file_list(placement="center")
        target.render((34, 9), focus=True)
        menus[1].open_at(4, 0)
        self.assertEqual("phot│(O)pen   │", lines(target, (34, 9))[3][:15])
        menus[1].close_pop_up()
        keys(target, (34, 9), "m")
        self.assertEqual(
            ["report.txt ┌─────────┐", "todo.org   │(O)pen   │"], [line[:22] for line in lines(target, (34, 9))[1:3]]
        )


class ArrowToOwnerTest(unittest.TestCase):
    """With pass_arrows_below, an arrow the top list has no use for goes to the widgets under the list."""

    def bar(self, **kwargs: typing.Any) -> tuple[urwid.PopUpTarget, urwid.Columns, list[urwid.ActionMenu]]:
        menus = [
            urwid.ActionMenu("File", WITH_SUBMENU, pass_arrows_below=True, **kwargs),
            urwid.ActionMenu("Edit", ["Copy", "Paste"], pass_arrows_below=True),
        ]
        columns = urwid.Columns([("pack", menu) for menu in menus], dividechars=1)
        return urwid.PopUpTarget(urwid.Filler(columns, "top")), columns, menus

    def test_unused_arrow_moves_to_the_next_launcher(self) -> None:
        """The list closes when the Columns takes the arrow; the next launcher gets the focus without opening."""
        for placement in ("launcher", "center"):
            with self.subTest(placement=placement):
                target, columns, menus = self.bar(placement=placement)
                keys(target, (40, 10), "enter")
                self.assertIsNone(target.keypress((40, 10), "right"))
                self.assertEqual(1, columns.focus_position)
                self.assertEqual([None, None], [menu.pop_up_widget for menu in menus])
                keys(target, (40, 10), "enter")
                self.assertIsNone(target.keypress((40, 10), "left"))
                self.assertEqual(0, columns.focus_position)
                self.assertIsNone(menus[1].pop_up_widget)

    def test_lone_menu_keeps_the_arrow_by_default(self) -> None:
        """Without pass_arrows_below the list keeps an unused arrow, even in a row of launchers."""
        menus = [urwid.ActionMenu("File", WITH_SUBMENU), urwid.ActionMenu("Edit", ["Copy", "Paste"])]
        columns = urwid.Columns([("pack", menu) for menu in menus], dividechars=1)
        target = urwid.PopUpTarget(urwid.Filler(columns, "top"))
        keys(target, (40, 10), "enter")
        self.assertEqual("right", target.keypress((40, 10), "right"))
        self.assertEqual(0, columns.focus_position)
        self.assertIsNotNone(menus[0].pop_up_widget)

    def test_unused_arrow_nobody_takes_keeps_the_list(self) -> None:
        """In a list of rows nothing takes the arrow, so the list stays open and the arrow is returned."""
        target, menus = file_list(pass_arrows_below=True)
        keys(target, (34, 9), "m")
        self.assertEqual("right", target.keypress((34, 9), "right"))
        self.assertIsNotNone(menus[1].pop_up_widget)

    def test_unfocused_launcher_keeps_the_arrow(self) -> None:
        """A list opened by open_at() on an unfocused launcher does not hand the arrow to the focused widget."""
        edit = urwid.Edit("", "hello")
        menu = urwid.ActionMenu(None, ["Copy"], launcher=urwid.SelectableIcon("row", 0), pass_arrows_below=True)
        target = urwid.PopUpTarget(urwid.ListBox(urwid.SimpleFocusListWalker([edit, menu])))
        target.render((20, 6), focus=True)
        menu.open_at(0, 0)
        keys(target, (20, 6))
        self.assertEqual("left", target.keypress((20, 6), "left"))
        self.assertEqual(5, edit.edit_pos)
        self.assertIsNotNone(menu.pop_up_widget)

    def test_list_closed_during_the_keypress_keeps_the_arrow(self) -> None:
        """A list a subclass closed while handling the arrow does not hand it to the widgets under it."""

        class ClosingMenu(urwid.ActionMenu):
            def _close_on_menu_key(self, key: str) -> str | None:
                self.close_pop_up()
                return key

        menus = [ClosingMenu("File", ["Open"], pass_arrows_below=True), urwid.ActionMenu("Edit", ["Copy"])]
        columns = urwid.Columns([("pack", menu) for menu in menus], dividechars=1)
        target = urwid.PopUpTarget(urwid.Filler(columns, "top"))
        keys(target, (40, 10), "enter")
        self.assertEqual("right", target.keypress((40, 10), "right"))
        self.assertEqual(0, columns.focus_position)

    def test_submenus_keep_their_arrows(self) -> None:
        """Either arrow on a submenu row of the top list opens the child, and a child list keeps every arrow."""
        for opening in ("left", "right"):
            with self.subTest(opening=opening):
                target, columns, menus = self.bar()
                keys(target, (40, 10), "enter", "down", opening)
                self.assertIn("(M)ail", "".join(lines(target, (40, 10))))
                # On the plain (M)ail row the arrow away from the parent is returned, with every list still open.
                self.assertEqual("right", target.keypress((40, 10), "right"))
                self.assertEqual(0, columns.focus_position)
                self.assertIn("(M)ail", "".join(lines(target, (40, 10))))


class SubmenuTest(unittest.TestCase):
    def open_child(
        self, *, right: bool = False, rows_before: int = 1, size: tuple[int, int] = (40, 10), **kwargs: typing.Any
    ) -> tuple[urwid.PopUpTarget, urwid.ActionMenu, list[tuple[str, object]]]:
        menu = urwid.ActionMenu("Actions", WITH_SUBMENU, focus_map="focus", **kwargs)
        sent = record(menu)
        target = screen(menu, rows_before, right=right)
        # The key towards the side the child prefers opens it.
        keys(target, size, "enter", "down", "left" if kwargs.get("align") == "right" else "right")
        return target, menu, sent

    def test_child_opens_beside_the_row_and_keeps_it_highlighted(self) -> None:
        """U2: the child's first item is level with its row, and the row keeps the focus attribute."""
        target, _menu, _sent = self.open_child()
        self.assertEqual(
            [
                "│(O)pen      │┌────────────┐            ",
                "│(S)end to  >││(M)ail      │            ",
                "├────────────┤│(P)rinter   │            ",
            ],
            lines(target, (40, 10))[3:6],
        )
        self.assertIn("focus", attributes(target, (40, 10), 4, range(1, 13)))
        self.assertIn("focus", attributes(target, (40, 10), 4, range(15, 27)))

    def test_child_opens_beside_a_centred_list(self) -> None:
        """The child of a centred list opens beside it, level with its row."""
        target, _menu, _sent = self.open_child(size=(44, 10), placement="center")
        self.assertEqual(
            [
                "status: -      ┌────────────┐               ",
                "               │(O)pen      │┌────────────┐ ",
                "               │(S)end to  >││(M)ail      │ ",
            ],
            lines(target, (44, 10))[2:5],
        )

    def test_child_flips_left_at_the_right_edge(self) -> None:
        """U3: near the right edge the child opens left of the parent, over none of its columns."""
        target, _menu, _sent = self.open_child(right=True, rows_before=0, size=(40, 8))
        self.assertEqual(
            [
                "                            Actions >   ",
                "status: -                 ┌────────────┐",
                "            ┌────────────┐│(O)pen      │",
                "            │(M)ail      ││(S)end to  >│",
                "            │(P)rinter   │├────────────┤",
                "            ├────────────┤│(D)elete    │",
                "            │(C)lipboard │└────────────┘",
                "            └────────────┘              ",
            ],
            lines(target, (40, 8)),
        )

    def test_align_right_opens_left_and_flips_right_at_the_left_edge(self) -> None:
        for description, right, expected_row in (
            ("room on the left", True, "         │(M)ail      ││(S)end to  >│   "),
            ("at the left edge", False, "│(S)end to  >││(M)ail      │            "),
        ):
            with self.subTest(description):
                target, _menu, _sent = self.open_child(right=right, rows_before=0, size=(40, 8), align="right")
                text = lines(target, (40, 8))
                self.assertIn(expected_row, text)

    def test_arrows_follow_the_side_the_child_is_drawn_on(self) -> None:
        """The arrow back towards the parent closes only the child, also after the child flipped at an edge."""
        for description, align, right, back, away in (
            ("align left, child on the right", "left", False, "left", "right"),
            ("align left at the right edge, child flipped left", "left", True, "right", "left"),
            ("align right, child on the left", "right", True, "right", "left"),
            ("align right at the left edge, child flipped right", "right", False, "left", "right"),
        ):
            for opening in ("left", "right"):
                with self.subTest(description, opening=opening):
                    menu = urwid.ActionMenu("Actions", WITH_SUBMENU, align=align)
                    sent = record(menu)
                    target = screen(menu, rows_before=0, right=right)
                    # In the top list either arrow opens the child.
                    keys(target, (40, 8), "enter", "down", opening)
                    self.assertIn("(M)ail", "".join(lines(target, (40, 8))))
                    # The arrow away from the parent has nothing to open in this child, and keeps it open.
                    keys(target, (40, 8), away)
                    self.assertIn("(M)ail", "".join(lines(target, (40, 8))))
                    keys(target, (40, 8), back)
                    self.assertNotIn("(M)ail", "".join(lines(target, (40, 8))))
                    self.assertIsNotNone(menu.pop_up_widget)
                    self.assertEqual([("open", None)], sent)

    def test_deep_menu_keeps_the_direction_of_a_flipped_child(self) -> None:
        """A child that flipped left at the right edge has its own child further left, opened with Left."""
        bottom = MenuItem("Deeper", submenu=[MenuItem("Bottom", "bottom")])
        menu = urwid.ActionMenu("Actions", [MenuItem("More", submenu=[bottom, MenuItem("Other")])])
        target = screen(menu, rows_before=0, right=True)
        keys(target, (40, 10), "enter", "right", "left")
        row = next(line for line in lines(target, (40, 10)) if "Bottom" in line)
        # Bottom, Deeper and More from left to right, each list left of the one that opened it.
        self.assertLess(row.index("Bottom"), row.index("Deeper"))
        self.assertLess(row.index("Deeper"), row.index("More"))
        keys(target, (40, 10), "right")
        self.assertNotIn("Bottom", "".join(lines(target, (40, 10))))
        self.assertIn("Deeper", "".join(lines(target, (40, 10))))

    def test_arrow_away_from_the_parent_opens_a_further_child(self) -> None:
        deeper = MenuItem("Deeper", submenu=[MenuItem("Bottom", "bottom")])
        menu = urwid.ActionMenu("Actions", [MenuItem("More", submenu=[deeper, MenuItem("Other")])])
        sent = record(menu)
        target = screen(menu)
        keys(target, (40, 10), "enter", "right")
        # "left" leads back to the top list, so it closes the child instead of opening "Deeper".
        keys(target, (40, 10), "right", "enter")
        self.assertEqual([("open", None), ("close", None), ("action", "bottom")], sent)

    def test_left_and_esc_close_only_the_child(self) -> None:
        for key in ("left", "esc"):
            with self.subTest(key):
                target, menu, sent = self.open_child()
                keys(target, (40, 10), key)
                self.assertIsNotNone(menu.pop_up_widget)
                self.assertEqual("│(S)end to  >│                          ", lines(target, (40, 10))[4])
                self.assertEqual([("open", None)], sent)

    def test_choice_in_the_child_closes_every_level(self) -> None:
        for description, pressed in (("enter", ("down", "enter")), ("accelerator", ("p",))):
            with self.subTest(description):
                target, menu, sent = self.open_child()
                keys(target, (40, 10), *pressed)
                self.assertIsNone(menu.pop_up_widget)
                self.assertEqual([("open", None), ("close", None), ("action", "printer")], sent)
                self.assertEqual("Actions >", lines(target, (40, 10))[1][:9])

    def test_row_is_drawn_as_usual_after_the_child_closed(self) -> None:
        target, _menu, _sent = self.open_child()
        keys(target, (40, 10), "left")
        self.assertIn("focus", attributes(target, (40, 10), 4, range(1, 13)))
        keys(target, (40, 10), "up")
        self.assertNotIn("focus", attributes(target, (40, 10), 4, range(1, 13)))

    def test_submenu_by_accelerator_and_enter(self) -> None:
        for pressed in (("s",), ("down", "enter")):
            with self.subTest(pressed):
                menu = urwid.ActionMenu("Actions", WITH_SUBMENU)
                target = screen(menu)
                keys(target, (40, 10), "enter", *pressed)
                self.assertIn("(M)ail", "".join(lines(target, (40, 10))))

    def test_child_opens_beside_a_list_widened_to_its_launcher(self) -> None:
        """A list as wide as a long launcher is the anchor at its drawn width, so the child does not cover it."""
        menu = urwid.ActionMenu("A rather long launcher", WITH_SUBMENU)
        pile = urwid.Pile([urwid.Padding(menu, width=24), urwid.Text("status")])
        target = urwid.PopUpTarget(urwid.Filler(pile, "top"))
        keys(target, (40, 10), "enter", "down", "right")
        # The parent list takes columns 0-23, the launcher's width, and the child starts right after it.
        self.assertEqual("│(S)end to            >││(M)ail      │  ", lines(target, (40, 10))[3])

    def test_open_child_does_not_keep_the_menu_alive(self) -> None:
        if sys.implementation.name != "cpython":
            self.skipTest("relies on reference counting freeing the widget")
        menu = urwid.ActionMenu("Actions", WITH_SUBMENU)
        target = screen(menu)
        keys(target, (40, 10), "enter", "down", "right")
        ref = weakref.ref(menu)
        gc.disable()
        try:
            del menu, target
            self.assertIsNone(ref())
        finally:
            gc.enable()

    def test_narrow_target_still_opens_the_child(self) -> None:
        """With no column beside the parent, the child overlaps it, and still takes keys and closes alone."""
        target, menu, sent = self.open_child(size=(14, 10))
        self.assertIn("│(M)ail      │", lines(target, (14, 10)))
        keys(target, (14, 10), "left")
        self.assertIsNotNone(menu.pop_up_widget)
        self.assertNotIn("│(M)ail      │", lines(target, (14, 10)))
        keys(target, (14, 10), "right", "esc")
        self.assertNotIn("│(M)ail      │", lines(target, (14, 10)))
        self.assertEqual([("open", None)], sent)


class ReadOnlyTest(unittest.TestCase):
    NOTHING = (MenuItem("Rename", enabled=False), None, MenuItem("Send", submenu=[MenuItem("Mail", enabled=False)]))

    def test_label_launcher(self) -> None:
        """E-B2: not selectable, opens nothing, and drawn with disabled_map."""
        menu = urwid.ActionMenu("Actions", self.NOTHING, disabled_map="disabled")
        self.assertFalse(menu.selectable())
        self.assertEqual("enter", menu.keypress((9,), "enter"))
        self.assertFalse(menu.mouse_event((9,), "mouse press", 1, 0, 0, True))
        menu.open_pop_up()
        menu.open_at(0, 0)
        self.assertIsNone(menu.pop_up_widget)
        self.assertEqual({"disabled"}, {attr for attr, _cs, _text in next(iter(menu.render((9,)).content()))})

    def test_launcher_attributes(self) -> None:
        """The label launcher takes the list's maps unless the ``launcher_*`` maps override them.

        While its list is open, it keeps its focus map although the focus is in the list,
        and it takes its own map again once the list closes.
        """
        items = [MenuItem("Open")]
        for name, kwargs, focus, opened, expected in (
            ("attr_map", {"attr_map": "option", "focus_map": "focus"}, False, False, {"option"}),
            ("focus_map", {"attr_map": "option", "focus_map": "focus"}, True, False, {"focus"}),
            ("focused without focus_map", {"attr_map": "option"}, True, False, {"option"}),
            ("override", {"attr_map": "option", "launcher_attr_map": "own"}, False, False, {"own"}),
            ("focused takes launcher_attr_map", {"launcher_attr_map": "own"}, True, False, {"own"}),
            ("focus override", {"focus_map": "focus", "launcher_focus_map": "own focus"}, True, False, {"own focus"}),
            ("open takes focus_map", {"attr_map": "option", "focus_map": "focus"}, False, True, {"focus"}),
            (
                "open takes launcher_focus_map",
                {"focus_map": "focus", "launcher_focus_map": "own"},
                False,
                True,
                {"own"},
            ),
            ("open without focus_map", {"attr_map": "option"}, False, True, {"option"}),
        ):
            with self.subTest(name):
                menu = urwid.ActionMenu("Actions", items, **kwargs)
                if opened:
                    menu.open_pop_up()
                canvas = menu.render((9,), focus=focus)
                self.assertEqual(expected, {attr for attr, _cs, _text in next(iter(canvas.content()))})
                menu.close_pop_up()
                fresh = urwid.ActionMenu("Actions", items, **kwargs).render((9,), focus=focus)
                self.assertEqual(list(fresh.content()), list(menu.render((9,), focus=focus).content()))

        menu = urwid.ActionMenu(
            "Actions",
            self.NOTHING,
            disabled_map="disabled",
            launcher_disabled_map="own disabled",
        )
        self.assertEqual({"own disabled"}, {attr for attr, _cs, _text in next(iter(menu.render((9,)).content()))})

    def test_launcher_map_survives_reopening_and_handlers(self) -> None:
        """The launcher takes its own map back after a second opening, and after a handler that reverses the change."""

        def launcher_attributes(menu: urwid.ActionMenu) -> set[object]:
            return {attr for attr, _cs, _text in next(iter(menu.render((9,)).content()))}

        def open_twice(menu: urwid.ActionMenu) -> None:
            menu.open_pop_up()
            menu.open_at(0, 0)
            self.assertEqual({"focus"}, launcher_attributes(menu))
            menu.close_pop_up()

        def close_on_open(menu: urwid.ActionMenu) -> None:
            urwid.connect_signal(menu, "open", lambda opened: opened.close_pop_up())
            menu.open_pop_up()
            self.assertIsNone(menu.pop_up_widget)

        def open_on_close(menu: urwid.ActionMenu) -> None:
            menu.open_pop_up()
            key = urwid.connect_signal(menu, "close", lambda closed: closed.open_pop_up())
            menu.close_pop_up()
            self.assertIsNotNone(menu.pop_up_widget)
            self.assertEqual({"focus"}, launcher_attributes(menu))
            urwid.disconnect_signal_by_key(menu, "close", key)
            menu.close_pop_up()

        for action in (open_twice, close_on_open, open_on_close):
            with self.subTest(action.__name__):
                menu = urwid.ActionMenu("Actions", [MenuItem("Open")], attr_map="option", focus_map="focus")
                action(menu)
                self.assertEqual({"option"}, launcher_attributes(menu))
                menu.open_pop_up()
                menu.close_pop_up()
                self.assertEqual({"option"}, launcher_attributes(menu))

    def test_given_launcher_is_not_restyled(self) -> None:
        """A launcher widget from the application keeps its own maps, also while the list is open."""
        menu = urwid.ActionMenu(None, [MenuItem("Open")], launcher=urwid.Text("x"), attr_map="option", focus_map="f")
        self.assertEqual({None}, {attr for attr, _cs, _text in next(iter(menu.render((3,), focus=True).content()))})
        launcher = urwid.AttrMap(urwid.SelectableIcon("x"), "own", "own focus")
        menu = urwid.ActionMenu(None, [MenuItem("Open")], launcher=launcher, focus_map="f")
        menu.open_pop_up()
        self.assertEqual({"own"}, {attr for attr, _cs, _text in next(iter(menu.render((3,)).content()))})

    def test_launcher_attr_map_is_not_hashable(self) -> None:
        with self.assertRaises(urwid.AttrMapError):
            urwid.ActionMenu("Actions", [MenuItem("Open")], launcher_attr_map={"a": []})

    def test_launcher_widget_keeps_its_keys_and_buttons(self) -> None:
        edit = urwid.Edit()
        menu = urwid.ActionMenu(None, self.NOTHING, launcher=edit, open_keys=("m",), disabled_map="disabled")
        self.assertTrue(menu.selectable())
        for key in ("m", "x"):
            self.assertIsNone(menu.keypress((10,), key))
        self.assertEqual("mx", edit.edit_text)
        menu.mouse_event((10,), "mouse press", 1, 0, 0, True)
        menu.open_pop_up()
        self.assertIsNone(menu.pop_up_widget)
        self.assertNotIn("disabled", {attr for attr, _cs, _text in next(iter(menu.render((10,)).content()))})


class ItemsSetterTest(unittest.TestCase):
    ITEMS = (MenuItem("Cut", "cut", key="t", enabled=False), MenuItem("Copy", "copy", key="c", enabled=False))
    ENABLED = tuple(dataclasses.replace(item, enabled=True) for item in ITEMS)

    def test_enabling_restyles_the_label_launcher(self) -> None:
        menu = urwid.ActionMenu("Edit", self.ITEMS, attr_map="option", focus_map="focus", disabled_map="disabled")
        self.assertFalse(menu.selectable())
        menu.items = self.ENABLED
        self.assertTrue(menu.selectable())
        self.assertEqual(menu.items[1], MenuItem("Copy", "copy", key="c"))
        fresh = urwid.ActionMenu("Edit", menu.items, attr_map="option", focus_map="focus", disabled_map="disabled")
        for focus in (False, True):
            with self.subTest(focus=focus):
                self.assertEqual(
                    list(fresh.render((9,), focus=focus).content()), list(menu.render((9,), focus=focus).content())
                )
        menu.items = self.ITEMS
        self.assertFalse(menu.selectable())
        self.assertEqual(
            {"disabled"}, {attr for attr, _cs, _text in next(iter(menu.render((9,), focus=True).content()))}
        )

    def test_open_list_is_rebuilt(self) -> None:
        """An open list shows the new items at once, without a close and an open signal."""
        menu = urwid.ActionMenu("Edit", self.ENABLED)
        target = screen(menu)
        sent = record(menu)
        keys(target, (20, 8), "enter")
        self.assertIn("Cut", "".join(lines(target, (20, 8))))
        menu.items = [MenuItem("Paste", "paste", key="p")]
        self.assertNotIn("Cut", "".join(lines(target, (20, 8))))
        keys(target, (20, 8), "p")
        self.assertEqual(sent, [("open", None), ("close", None), ("action", "paste")])

    def test_list_closes_when_nothing_can_be_chosen(self) -> None:
        menu = urwid.ActionMenu("Edit", self.ENABLED, focus_map="focus", disabled_map="disabled")
        sent = record(menu)
        menu.open_pop_up()
        menu.items = self.ITEMS
        self.assertIsNone(menu.pop_up_widget)
        self.assertEqual(sent, [("open", None), ("close", None)])
        self.assertEqual({"disabled"}, {attr for attr, _cs, _text in next(iter(menu.render((9,)).content()))})

    def test_invalid_items_are_refused(self) -> None:
        menu = urwid.ActionMenu("Edit", self.ITEMS)
        for items in ([], [None], [MenuItem("A", key="a"), MenuItem("B", key="a")]):
            with self.subTest(items=items), self.assertRaises(ValueError):
                menu.items = items
            self.assertEqual(menu.items, self.ITEMS)


if __name__ == "__main__":
    unittest.main()

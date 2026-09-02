from __future__ import annotations

import unittest

import urwid


class WidgetSquishTest(unittest.TestCase):
    def wstest(self, w):
        c = w.render((80, 0), focus=False)
        assert c.rows() == 0
        c = w.render((80, 0), focus=True)
        assert c.rows() == 0
        c = w.render((80, 1), focus=False)
        assert c.rows() == 1
        c = w.render((0, 25), focus=False)
        c = w.render((1, 25), focus=False)

    def fwstest(self, w):
        def t(cols: int, focus: bool):
            wrows = w.rows((cols,), focus)
            c = w.render((cols,), focus)
            self.assertEqual(c.rows(), wrows, f"Canvas rows {c.rows()} != widget rows {wrows}")
            if focus and hasattr(w, "get_cursor_coords"):
                gcc = w.get_cursor_coords((cols,))
                self.assertEqual(c.cursor, gcc, f"Canvas cursor {c.cursor} != widget cursor {gcc}")

        for cols, focus in ((0, False), (1, False), (0, True), (1, True)):
            with self.subTest(f"{w.__class__.__name__} cols={cols} and focus={focus}"):
                t(cols, focus)

    def test_listbox(self):
        self.wstest(urwid.ListBox(urwid.SimpleListWalker([])))
        self.wstest(urwid.ListBox(urwid.SimpleListWalker([urwid.Text("hello")])))

    def test_bargraph(self):
        self.wstest(urwid.BarGraph(["foo", "bar"]))

    def test_graphvscale(self):
        self.wstest(urwid.GraphVScale([(0, "hello")], 1))
        self.wstest(urwid.GraphVScale([(5, "hello")], 1))

    def test_solidfill(self):
        self.wstest(urwid.SolidFill())

    def test_filler(self):
        self.wstest(urwid.Filler(urwid.Text("hello")))

    def test_overlay(self):
        self.wstest(
            urwid.Overlay(
                urwid.BigText("hello", urwid.Thin6x6Font()), urwid.SolidFill(), "center", None, "middle", None
            )
        )
        self.wstest(urwid.Overlay(urwid.Text("hello"), urwid.SolidFill(), "center", ("relative", 100), "middle", None))

    def test_frame(self):
        self.wstest(urwid.Frame(urwid.SolidFill()))
        self.wstest(urwid.Frame(urwid.SolidFill(), header=urwid.Text("hello")))
        self.wstest(urwid.Frame(urwid.SolidFill(), header=urwid.Text("hello"), footer=urwid.Text("hello")))

    def test_pile(self):
        self.wstest(urwid.Pile([urwid.SolidFill()]))
        self.wstest(urwid.Pile([("flow", urwid.Text("hello"))]))
        self.wstest(urwid.Pile([]))

    def test_columns(self):
        self.wstest(urwid.Columns([urwid.SolidFill()]))
        self.wstest(urwid.Columns([(4, urwid.SolidFill())]))

    def test_buttons(self):
        self.fwstest(urwid.Button("hello"))
        self.fwstest(urwid.RadioButton([], "hello"))

    def testFocus(self):
        expect_focused = urwid.Button("Focused")
        pile = urwid.Pile((urwid.Button("First"), expect_focused, urwid.Button("Last")), focus_item=expect_focused)
        self.assertEqual(1, pile.focus_position)
        self.assertEqual(expect_focused, pile.focus)


class CommonContainerTest(unittest.TestCase):
    def test_list_box(self):
        lb = urwid.ListBox(urwid.SimpleFocusListWalker([]))
        self.assertEqual(lb.focus, None)
        self.assertRaises(IndexError, lambda: getattr(lb, "focus_position"))
        self.assertRaises(IndexError, lambda: setattr(lb, "focus_position", None))
        self.assertRaises(IndexError, lambda: setattr(lb, "focus_position", 0))

        t1 = urwid.Text("one")
        t2 = urwid.Text("two")
        lb = urwid.ListBox(urwid.SimpleListWalker([t1, t2]))
        self.assertEqual(lb.focus, t1)
        self.assertEqual(lb.focus_position, 0)
        lb.focus_position = 1
        self.assertEqual(lb.focus, t2)
        self.assertEqual(lb.focus_position, 1)
        lb.focus_position = 0
        self.assertRaises(IndexError, lambda: setattr(lb, "focus_position", -1))
        self.assertRaises(IndexError, lambda: setattr(lb, "focus_position", 2))

    def test_focus_path(self):
        # big tree of containers
        t = urwid.Text("x")
        e = urwid.Edit("?")
        c = urwid.Columns([t, e, t, t])
        p = urwid.Pile([t, t, c, t])
        a = urwid.AttrMap(p, "gets ignored")
        s = urwid.SolidFill("/")
        o = urwid.Overlay(e, s, "center", "pack", "middle", "pack")
        lb = urwid.ListBox(urwid.SimpleFocusListWalker([t, a, o, t]))
        lb.focus_position = 1
        g = urwid.GridFlow([t, t, t, t, e, t], 10, 0, 0, "left")
        g.focus_position = 4
        f = urwid.Frame(lb, header=t, footer=g)

        self.assertEqual(f.get_focus_path(), ["body", 1, 2, 1])
        f.set_focus_path(["footer"])  # same as f.focus_position = 'footer'
        self.assertEqual(f.get_focus_path(), ["footer", 4])
        f.set_focus_path(["body", 1, 2, 2])
        self.assertEqual(f.get_focus_path(), ["body", 1, 2, 2])
        self.assertRaises(IndexError, lambda: f.set_focus_path([0, 1, 2]))
        self.assertRaises(IndexError, lambda: f.set_focus_path(["body", 2, 2]))
        f.set_focus_path(["body", 2])  # focus the overlay
        self.assertEqual(f.get_focus_path(), ["body", 2, 1])

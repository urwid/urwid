from __future__ import annotations

import unittest

import urwid
from tests.util import SelectableText


class ListBoxCalculateVisibleTest(unittest.TestCase):
    def cvtest(
        self,
        desc: str,
        body,
        focus: int,
        offset_rows: int,
        inset_fraction,
        exp_offset_inset: int,
        exp_cur: tuple[int, int] | None,
    ) -> None:
        with self.subTest(desc):
            lbox = urwid.ListBox(urwid.SimpleListWalker(body))
            lbox.body.set_focus(focus)
            lbox.offset_rows = offset_rows
            lbox.inset_fraction = inset_fraction

            middle, top, bottom = lbox.calculate_visible((4, 5), focus=1)
            offset_inset, focus_widget, focus_pos, _ign, cursor = middle

            if cursor is not None:
                x, y = cursor
                y += offset_inset
                cursor = x, y

            self.assertEqual(exp_offset_inset, offset_inset)
            self.assertEqual(exp_cur, cursor)

    def test1_simple(self):
        T = urwid.Text

        l = [T(""), T(""), T("\n"), T("\n\n"), T("\n"), T(""), T("")]

        self.cvtest(
            "simple top position",
            l,
            3,
            0,
            (0, 1),
            0,
            None,
        )

        self.cvtest(
            "simple middle position",
            l,
            3,
            1,
            (0, 1),
            1,
            None,
        )

        self.cvtest(
            "simple bottom position",
            l,
            3,
            2,
            (0, 1),
            2,
            None,
        )

        self.cvtest(
            "straddle top edge",
            l,
            3,
            0,
            (1, 2),
            -1,
            None,
        )

        self.cvtest(
            "straddle bottom edge",
            l,
            3,
            4,
            (0, 1),
            4,
            None,
        )

        self.cvtest(
            "off bottom edge",
            l,
            3,
            5,
            (0, 1),
            4,
            None,
        )

        self.cvtest(
            "way off bottom edge",
            l,
            3,
            100,
            (0, 1),
            4,
            None,
        )

        self.cvtest(
            "gap at top",
            l,
            0,
            2,
            (0, 1),
            0,
            None,
        )

        self.cvtest(
            "gap at top and off bottom edge",
            l,
            2,
            5,
            (0, 1),
            2,
            None,
        )

        self.cvtest(
            "gap at bottom",
            l,
            6,
            1,
            (0, 1),
            4,
            None,
        )

        self.cvtest(
            "gap at bottom and straddling top edge",
            l,
            4,
            0,
            (1, 2),
            1,
            None,
        )

        self.cvtest(
            "gap at bottom cannot completely fill",
            [T(""), T(""), T("")],
            1,
            0,
            (0, 1),
            1,
            None,
        )

        self.cvtest(
            "gap at top and bottom",
            [T(""), T(""), T("")],
            1,
            2,
            (0, 1),
            1,
            None,
        )

    def test2_cursor(self):
        T, E = urwid.Text, urwid.Edit

        l1 = [T(""), T(""), T("\n"), E("", "\n\nX"), T("\n"), T(""), T("")]
        l2 = [T(""), T(""), T("\n"), E("", "YY\n\n"), T("\n"), T(""), T("")]

        l2[3].set_edit_pos(2)

        self.cvtest(
            "plain cursor in view",
            l1,
            3,
            1,
            (0, 1),
            1,
            (1, 3),
        )

        self.cvtest(
            "cursor off top",
            l2,
            3,
            0,
            (1, 3),
            0,
            (2, 0),
        )

        self.cvtest(
            "cursor further off top",
            l2,
            3,
            0,
            (2, 3),
            0,
            (2, 0),
        )

        self.cvtest(
            "cursor off bottom",
            l1,
            3,
            3,
            (0, 1),
            2,
            (1, 4),
        )

        self.cvtest(
            "cursor way off bottom",
            l1,
            3,
            100,
            (0, 1),
            2,
            (1, 4),
        )

    def test_sized(self):
        lbox = urwid.ListBox(urwid.SimpleListWalker([urwid.Text(str(num)) for num in range(5)]))
        self.assertEqual(5, len(lbox))

    def test_not_sized(self):
        class TestWalker(urwid.ListWalker):
            @property
            def contents(self):
                return self

            @staticmethod
            def next_position(position: int) -> tuple[urwid.Text, int]:
                return urwid.Text(str(position)), position

            @staticmethod
            def prev_position(position: int) -> tuple[urwid.Text, int]:
                return urwid.Text(str(position)), position

        lbox = urwid.ListBox(TestWalker())
        with self.assertRaises(AttributeError) as exc:
            len(lbox)

        self.assertEqual(f"{TestWalker.__name__} is not Sized", str(exc.exception))


class ListBoxChangeFocusTest(unittest.TestCase):
    def cftest(
        self,
        desc: str,
        body,
        pos: int,
        offset_inset: int,
        coming_from,
        cursor: tuple[int, int] | None,
        snap_rows,
        exp_offset_rows: int,
        exp_inset_fraction,
        exp_cur: tuple[int, int] | None,
    ):
        with self.subTest(desc):
            lbox = urwid.ListBox(urwid.SimpleListWalker(body))

            lbox.change_focus((4, 5), pos, offset_inset, coming_from, cursor, snap_rows)

            exp = exp_offset_rows, exp_inset_fraction
            act = lbox.offset_rows, lbox.inset_fraction

            cursor = None
            focus_widget, focus_pos = lbox.body.get_focus()
            if focus_widget.selectable():
                if hasattr(focus_widget, "get_cursor_coords"):
                    cursor = focus_widget.get_cursor_coords((4,))

            self.assertEqual(exp, act)
            self.assertEqual(exp_cur, cursor)

    def test1unselectable(self):
        T = urwid.Text
        l = [T("\n"), T("\n\n"), T("\n\n"), T("\n\n"), T("\n")]

        self.cftest(
            "simple unselectable",
            l,
            2,
            0,
            None,
            None,
            None,
            0,
            (0, 1),
            None,
        )

        self.cftest(
            "unselectable",
            l,
            2,
            1,
            None,
            None,
            None,
            1,
            (0, 1),
            None,
        )

        self.cftest(
            "unselectable off top",
            l,
            2,
            -2,
            None,
            None,
            None,
            0,
            (2, 3),
            None,
        )

        self.cftest(
            "unselectable off bottom",
            l,
            3,
            2,
            None,
            None,
            None,
            2,
            (0, 1),
            None,
        )

    def test2selectable(self):
        T, S = urwid.Text, SelectableText
        l = [T("\n"), T("\n\n"), S("\n\n"), T("\n\n"), T("\n")]

        self.cftest(
            "simple selectable",
            l,
            2,
            0,
            None,
            None,
            None,
            0,
            (0, 1),
            None,
        )

        self.cftest(
            "selectable",
            l,
            2,
            1,
            None,
            None,
            None,
            1,
            (0, 1),
            None,
        )

        self.cftest(
            "selectable at top",
            l,
            2,
            0,
            "below",
            None,
            None,
            0,
            (0, 1),
            None,
        )

        self.cftest(
            "selectable at bottom",
            l,
            2,
            2,
            "above",
            None,
            None,
            2,
            (0, 1),
            None,
        )

        self.cftest(
            "selectable off top snap",
            l,
            2,
            -1,
            "below",
            None,
            None,
            0,
            (0, 1),
            None,
        )

        self.cftest(
            "selectable off bottom snap",
            l,
            2,
            3,
            "above",
            None,
            None,
            2,
            (0, 1),
            None,
        )

        self.cftest(
            "selectable off top no snap",
            l,
            2,
            -1,
            "above",
            None,
            None,
            0,
            (1, 3),
            None,
        )

        self.cftest(
            "selectable off bottom no snap",
            l,
            2,
            3,
            "below",
            None,
            None,
            3,
            (0, 1),
            None,
        )

    def test3large_selectable(self):
        T, S = urwid.Text, SelectableText
        l = [T("\n"), S("\n\n\n\n\n\n"), T("\n")]
        self.cftest(
            "large selectable no snap",
            l,
            1,
            -1,
            None,
            None,
            None,
            0,
            (1, 7),
            None,
        )

        self.cftest(
            "large selectable snap up",
            l,
            1,
            -2,
            "below",
            None,
            None,
            0,
            (0, 1),
            None,
        )

        self.cftest(
            "large selectable snap up2",
            l,
            1,
            -2,
            "below",
            None,
            2,
            0,
            (0, 1),
            None,
        )

        self.cftest(
            "large selectable almost snap up",
            l,
            1,
            -2,
            "below",
            None,
            1,
            0,
            (2, 7),
            None,
        )

        self.cftest(
            "large selectable snap down",
            l,
            1,
            0,
            "above",
            None,
            None,
            0,
            (2, 7),
            None,
        )

        self.cftest(
            "large selectable snap down2",
            l,
            1,
            0,
            "above",
            None,
            2,
            0,
            (2, 7),
            None,
        )

        self.cftest(
            "large selectable almost snap down",
            l,
            1,
            0,
            "above",
            None,
            1,
            0,
            (0, 1),
            None,
        )

        m = [T("\n\n\n\n"), S("\n\n\n\n\n"), T("\n\n\n\n")]
        self.cftest(
            "large selectable outside view down",
            m,
            1,
            4,
            "above",
            None,
            None,
            0,
            (0, 1),
            None,
        )

        self.cftest(
            "large selectable outside view up",
            m,
            1,
            -5,
            "below",
            None,
            None,
            0,
            (1, 6),
            None,
        )

    def test4cursor(self):
        T, E = urwid.Text, urwid.Edit
        # ...

    def test5set_focus_valign(self):
        T, E = urwid.Text, urwid.Edit
        lbox = urwid.ListBox(urwid.SimpleFocusListWalker([T(""), T("")]))
        lbox.set_focus_valign("middle")
        # TODO: actually test the result


class ListBoxRenderTest(unittest.TestCase):
    def ltest(
        self,
        desc: str,
        body,
        focus: int,
        offset_inset_rows: int,
        exp_text: list[bytes],
        exp_cur: tuple[int, int] | None,
    ) -> None:
        with self.subTest(desc):
            exp_text = [t.encode("iso8859-1") for t in exp_text]
            lbox = urwid.ListBox(urwid.SimpleListWalker(body))
            lbox.body.set_focus(focus)
            lbox.shift_focus((4, 10), offset_inset_rows)
            canvas = lbox.render((4, 5), focus=1)

            self.assertEqual(exp_text, canvas.text)
            self.assertEqual(exp_cur, canvas.cursor)

    def test1_simple(self):
        T = urwid.Text

        self.ltest(
            "simple one text item render",
            [T("1\n2")],
            0,
            0,
            ["1   ", "2   ", "    ", "    ", "    "],
            None,
        )

        self.ltest(
            "simple multi text item render off bottom",
            [T("1"), T("2"), T("3\n4"), T("5"), T("6")],
            2,
            2,
            ["1   ", "2   ", "3   ", "4   ", "5   "],
            None,
        )

        self.ltest(
            "simple multi text item render off top",
            [T("1"), T("2"), T("3\n4"), T("5"), T("6")],
            2,
            1,
            ["2   ", "3   ", "4   ", "5   ", "6   "],
            None,
        )

    def test2_trim(self):
        T = urwid.Text

        self.ltest(
            "trim unfocused bottom",
            [T("1\n2"), T("3\n4"), T("5\n6")],
            1,
            2,
            ["1   ", "2   ", "3   ", "4   ", "5   "],
            None,
        )

        self.ltest(
            "trim unfocused top",
            [T("1\n2"), T("3\n4"), T("5\n6")],
            1,
            1,
            ["2   ", "3   ", "4   ", "5   ", "6   "],
            None,
        )

        self.ltest(
            "trim none full focus",
            [T("1\n2\n3\n4\n5")],
            0,
            0,
            ["1   ", "2   ", "3   ", "4   ", "5   "],
            None,
        )

        self.ltest(
            "trim focus bottom",
            [T("1\n2\n3\n4\n5\n6")],
            0,
            0,
            ["1   ", "2   ", "3   ", "4   ", "5   "],
            None,
        )

        self.ltest(
            "trim focus top",
            [T("1\n2\n3\n4\n5\n6")],
            0,
            -1,
            ["2   ", "3   ", "4   ", "5   ", "6   "],
            None,
        )

        self.ltest(
            "trim focus top and bottom",
            [T("1\n2\n3\n4\n5\n6\n7")],
            0,
            -1,
            ["2   ", "3   ", "4   ", "5   ", "6   "],
            None,
        )

    def test3_shift(self):
        T, E = urwid.Text, urwid.Edit

        self.ltest(
            "shift up one fit",
            [T("1\n2"), T("3"), T("4"), T("5"), T("6")],
            4,
            5,
            ["2   ", "3   ", "4   ", "5   ", "6   "],
            None,
        )

        e = E("", "ab\nc", 1)
        e.set_edit_pos(2)
        self.ltest(
            "shift down one cursor over edge",
            [e, T("3"), T("4"), T("5\n6")],
            0,
            -1,
            ["ab  ", "c   ", "3   ", "4   ", "5   "],
            (2, 0),
        )

        self.ltest(
            "shift up one cursor over edge",
            [T("1\n2"), T("3"), T("4"), E("", "d\ne")],
            3,
            4,
            ["2   ", "3   ", "4   ", "d   ", "e   "],
            (1, 4),
        )

        self.ltest(
            "shift none cursor top focus over edge",
            [E("", "ab\n"), T("3"), T("4"), T("5\n6")],
            0,
            -1,
            ["    ", "3   ", "4   ", "5   ", "6   "],
            (0, 0),
        )

        e = E("", "abc\nd")
        e.set_edit_pos(3)
        self.ltest(
            "shift none cursor bottom focus over edge",
            [T("1\n2"), T("3"), T("4"), e],
            3,
            4,
            ["1   ", "2   ", "3   ", "4   ", "abc "],
            (3, 4),
        )

    def test4_really_large_contents(self):
        T, E = urwid.Text, urwid.Edit
        self.ltest(
            "really large edit",
            [T("hello" * 100)],
            0,
            0,
            ["hell", "ohel", "lohe", "lloh", "ello"],
            None,
        )

        self.ltest(
            "really large edit",
            [E("", "hello" * 100)],
            0,
            0,
            ["hell", "ohel", "lohe", "lloh", "llo "],
            (3, 4),
        )


class ListBoxKeypressTest(unittest.TestCase):
    def ktest(
        self,
        desc: str,
        key,
        body,
        focus: int,
        offset_inset: int,
        exp_focus: int,
        exp_offset_inset: int,
        exp_cur: tuple[int, int] | None,
        lbox=None,
    ) -> tuple[str | None, urwid.ListBox]:

        if lbox is None:
            lbox = urwid.ListBox(urwid.SimpleListWalker(body))
            lbox.body.set_focus(focus)
            lbox.shift_focus((4, 10), offset_inset)

        ret_key = lbox.keypress((4, 5), key)
        middle, top, bottom = lbox.calculate_visible((4, 5), focus=1)
        offset_inset, focus_widget, focus_pos, _ign, cursor = middle

        if cursor is not None:
            x, y = cursor
            y += offset_inset
            cursor = x, y

        exp = exp_focus, exp_offset_inset
        act = focus_pos, offset_inset
        self.assertEqual(exp, act)
        self.assertEqual(exp_cur, cursor)
        return ret_key, lbox

    def test1_up(self):
        T, S, E = urwid.Text, SelectableText, urwid.Edit

        self.ktest(
            "direct selectable both visible",
            "up",
            [S(""), S("")],
            1,
            1,
            0,
            0,
            None,
        )

        self.ktest(
            "selectable skip one all visible",
            "up",
            [S(""), T(""), S("")],
            2,
            2,
            0,
            0,
            None,
        )

        key, lbox = self.ktest(
            "nothing above no scroll",
            "up",
            [S("")],
            0,
            0,
            0,
            0,
            None,
        )
        self.assertEqual("up", key)

        key, lbox = self.ktest(
            "unselectable above no scroll",
            "up",
            [T(""), T(""), S("")],
            2,
            2,
            2,
            2,
            None,
        )
        self.assertEqual("up", key)

        self.ktest(
            "unselectable above scroll 1",
            "up",
            [T(""), S(""), T("\n\n\n")],
            1,
            0,
            1,
            1,
            None,
        )

        self.ktest(
            "selectable above scroll 1",
            "up",
            [S(""), S(""), T("\n\n\n")],
            1,
            0,
            0,
            0,
            None,
        )

        self.ktest(
            "selectable above too far",
            "up",
            [S(""), T(""), S(""), T("\n\n\n")],
            2,
            0,
            2,
            1,
            None,
        )

        self.ktest(
            "selectable above skip 1 scroll 1",
            "up",
            [S(""), T(""), S(""), T("\n\n\n")],
            2,
            1,
            0,
            0,
            None,
        )

        self.ktest(
            "tall selectable above scroll 2",
            "up",
            [S(""), S("\n"), S(""), T("\n\n\n")],
            2,
            0,
            1,
            0,
            None,
        )

        self.ktest(
            "very tall selectable above scroll 5",
            "up",
            [S(""), S("\n\n\n\n"), S(""), T("\n\n\n\n")],
            2,
            0,
            1,
            0,
            None,
        )

        self.ktest(
            "very tall selected scroll within 1",
            "up",
            [S(""), S("\n\n\n\n\n")],
            1,
            -1,
            1,
            0,
            None,
        )

        self.ktest(
            "edit above pass cursor",
            "up",
            [E("", "abc"), E("", "de")],
            1,
            1,
            0,
            0,
            (2, 0),
        )

        key, lbox = self.ktest(
            "edit too far above pass cursor A",
            "up",
            [E("", "abc"), T("\n\n\n\n"), E("", "de")],
            2,
            4,
            1,
            0,
            None,
        )

        self.ktest(
            "edit too far above pass cursor B",
            "up",
            None,
            None,
            None,
            0,
            0,
            (2, 0),
            lbox,
        )

        self.ktest(
            "within focus cursor made not visible",
            "up",
            [T("\n\n\n"), E("hi\n", "ab")],
            1,
            3,
            0,
            0,
            None,
        )

        self.ktest(
            "within focus cursor made not visible (2)",
            "up",
            [T("\n\n\n\n"), E("hi\n", "ab")],
            1,
            3,
            0,
            -1,
            None,
        )

        self.ktest(
            "force focus unselectable",
            "up",
            [T("\n\n\n\n"), S("")],
            1,
            4,
            0,
            0,
            None,
        )

        self.ktest(
            "pathological cursor widget",
            "up",
            [T("\n"), E("\n\n\n\n\n", "a")],
            1,
            4,
            0,
            -1,
            None,
        )

        self.ktest(
            "unselectable to unselectable",
            "up",
            [T(""), T(""), T(""), T(""), T(""), T(""), T("")],
            2,
            0,
            1,
            0,
            None,
        )

        self.ktest(
            "unselectable over edge to same",
            "up",
            [T(""), T("12\n34"), T(""), T(""), T(""), T("")],
            1,
            -1,
            1,
            0,
            None,
        )

        key, lbox = self.ktest(
            "edit short between pass cursor A",
            "up",
            [E("", "abcd"), E("", "a"), E("", "def")],
            2,
            2,
            1,
            1,
            (1, 1),
        )

        self.ktest(
            "edit short between pass cursor B",
            "up",
            None,
            None,
            None,
            0,
            0,
            (3, 0),
            lbox,
        )

        e = E("", "\n\n\n\n\n")
        e.set_edit_pos(1)
        key, lbox = self.ktest(
            "edit cursor force scroll",
            "up",
            [e],
            0,
            -1,
            0,
            0,
            (0, 0),
        )
        self.assertEqual(0, lbox.inset_fraction[0])

    def test2_down(self):
        T, S, E = urwid.Text, SelectableText, urwid.Edit

        self.ktest(
            "direct selectable both visible",
            "down",
            [S(""), S("")],
            0,
            0,
            1,
            1,
            None,
        )

        self.ktest(
            "selectable skip one all visible",
            "down",
            [S(""), T(""), S("")],
            0,
            0,
            2,
            2,
            None,
        )

        key, lbox = self.ktest(
            "nothing below no scroll",
            "down",
            [S("")],
            0,
            0,
            0,
            0,
            None,
        )
        self.assertEqual("down", key)

        key, lbox = self.ktest(
            "unselectable below no scroll",
            "down",
            [S(""), T(""), T("")],
            0,
            0,
            0,
            0,
            None,
        )
        self.assertEqual("down", key)

        self.ktest(
            "unselectable below scroll 1",
            "down",
            [T("\n\n\n"), S(""), T("")],
            1,
            4,
            1,
            3,
            None,
        )

        self.ktest(
            "selectable below scroll 1",
            "down",
            [T("\n\n\n"), S(""), S("")],
            1,
            4,
            2,
            4,
            None,
        )

        self.ktest(
            "selectable below too far",
            "down",
            [T("\n\n\n"), S(""), T(""), S("")],
            1,
            4,
            1,
            3,
            None,
        )

        self.ktest(
            "selectable below skip 1 scroll 1",
            "down",
            [T("\n\n\n"), S(""), T(""), S("")],
            1,
            3,
            3,
            4,
            None,
        )

        self.ktest(
            "tall selectable below scroll 2",
            "down",
            [T("\n\n\n"), S(""), S("\n"), S("")],
            1,
            4,
            2,
            3,
            None,
        )

        self.ktest(
            "very tall selectable below scroll 5",
            "down",
            [T("\n\n\n\n"), S(""), S("\n\n\n\n"), S("")],
            1,
            4,
            2,
            0,
            None,
        )

        self.ktest(
            "very tall selected scroll within 1",
            "down",
            [S("\n\n\n\n\n"), S("")],
            0,
            0,
            0,
            -1,
            None,
        )

        self.ktest(
            "edit below pass cursor",
            "down",
            [E("", "de"), E("", "abc")],
            0,
            0,
            1,
            1,
            (2, 1),
        )

        key, lbox = self.ktest(
            "edit too far below pass cursor A",
            "down",
            [E("", "de"), T("\n\n\n\n"), E("", "abc")],
            0,
            0,
            1,
            0,
            None,
        )

        self.ktest(
            "edit too far below pass cursor B",
            "down",
            None,
            None,
            None,
            2,
            4,
            (2, 4),
            lbox,
        )

        odd_e = E("", "hi\nab")
        odd_e.set_edit_pos(2)
        # disble cursor movement in odd_e object
        odd_e.move_cursor_to_coords = lambda s, c, xy: 0
        self.ktest(
            "within focus cursor made not visible",
            "down",
            [odd_e, T("\n\n\n\n")],
            0,
            0,
            1,
            1,
            None,
        )

        self.ktest(
            "within focus cursor made not visible (2)",
            "down",
            [
                odd_e,
                T("\n\n\n\n"),
            ],
            0,
            0,
            1,
            1,
            None,
        )

        self.ktest(
            "force focus unselectable",
            "down",
            [S(""), T("\n\n\n\n")],
            0,
            0,
            1,
            0,
            None,
        )

        odd_e.set_edit_text("hi\n\n\n\n\n")
        self.ktest(
            "pathological cursor widget",
            "down",
            [odd_e, T("\n")],
            0,
            0,
            1,
            4,
            None,
        )

        self.ktest(
            "unselectable to unselectable",
            "down",
            [T(""), T(""), T(""), T(""), T(""), T(""), T("")],
            4,
            4,
            5,
            4,
            None,
        )

        self.ktest(
            "unselectable over edge to same",
            "down",
            [T(""), T(""), T(""), T(""), T("12\n34"), T("")],
            4,
            4,
            4,
            3,
            None,
        )

        key, lbox = self.ktest(
            "edit short between pass cursor A",
            "down",
            [E("", "abc"), E("", "a"), E("", "defg")],
            0,
            0,
            1,
            1,
            (1, 1),
        )

        self.ktest(
            "edit short between pass cursor B",
            "down",
            None,
            None,
            None,
            2,
            2,
            (3, 2),
            lbox,
        )

        e = E("", "\n\n\n\n\n")
        e.set_edit_pos(4)
        key, lbox = self.ktest(
            "edit cursor force scroll",
            "down",
            [e],
            0,
            0,
            0,
            -1,
            (0, 4),
        )
        self.assertEqual(1, lbox.inset_fraction[0])

    def test3_page_up(self):
        T, S, E = urwid.Text, SelectableText, urwid.Edit

        self.ktest(
            "unselectable aligned to aligned",
            "page up",
            [T(""), T("\n"), T("\n\n"), T(""), T("\n"), T("\n\n")],
            3,
            0,
            1,
            0,
            None,
        )

        self.ktest(
            "unselectable unaligned to aligned",
            "page up",
            [T(""), T("\n"), T("\n"), T("\n"), T("\n"), T("\n\n")],
            3,
            -1,
            1,
            0,
            None,
        )

        self.ktest(
            "selectable to unselectable",
            "page up",
            [T(""), T("\n"), T("\n"), T("\n"), S("\n"), T("\n\n")],
            4,
            1,
            1,
            -1,
            None,
        )

        self.ktest(
            "selectable to cut off selectable",
            "page up",
            [S("\n\n"), T("\n"), T("\n"), S("\n"), T("\n\n")],
            3,
            1,
            0,
            -1,
            None,
        )

        self.ktest(
            "seletable to selectable",
            "page up",
            [T("\n\n"), S("\n"), T("\n"), S("\n"), T("\n\n")],
            3,
            1,
            1,
            1,
            None,
        )

        self.ktest(
            "within very long selectable",
            "page up",
            [S(""), S("\n\n\n\n\n\n\n\n"), T("\n")],
            1,
            -6,
            1,
            -1,
            None,
        )

        e = E("", "\n\nab\n\n\n\n\ncd\n")
        e.set_edit_pos(11)
        self.ktest(
            "within very long cursor widget",
            "page up",
            [S(""), e, T("\n")],
            1,
            -6,
            1,
            -2,
            (2, 0),
        )

        self.ktest(
            "pathological cursor widget",
            "page up",
            [T(""), E("\n\n\n\n\n\n\n\n", "ab"), T("")],
            1,
            -5,
            0,
            0,
            None,
        )

        e = E("", "\nab\n\n\n\n\ncd\n")
        e.set_edit_pos(10)
        self.ktest(
            "very long cursor widget snap",
            "page up",
            [T(""), e, T("\n")],
            1,
            -5,
            1,
            0,
            (2, 1),
        )

        self.ktest(
            "slight scroll selectable",
            "page up",
            [T("\n"), S("\n"), T(""), S(""), T("\n\n\n"), S("")],
            5,
            4,
            3,
            0,
            None,
        )

        self.ktest(
            "scroll into snap region",
            "page up",
            [T("\n"), S("\n"), T(""), T(""), T("\n\n\n"), S("")],
            5,
            4,
            1,
            0,
            None,
        )

        self.ktest(
            "mid scroll short",
            "page up",
            [T("\n"), T(""), T(""), S(""), T(""), T("\n"), S(""), T("\n")],
            6,
            2,
            3,
            1,
            None,
        )

        self.ktest(
            "mid scroll long",
            "page up",
            [T("\n"), S(""), T(""), S(""), T(""), T("\n"), S(""), T("\n")],
            6,
            2,
            1,
            0,
            None,
        )

        self.ktest(
            "mid scroll perfect",
            "page up",
            [T("\n"), S(""), S(""), S(""), T(""), T("\n"), S(""), T("\n")],
            6,
            2,
            2,
            0,
            None,
        )

        self.ktest(
            "cursor move up fail short",
            "page up",
            [T("\n"), T("\n"), E("", "\nab"), T(""), T("")],
            2,
            1,
            2,
            4,
            (0, 4),
        )

        self.ktest(
            "cursor force fail short",
            "page up",
            [T("\n"), T("\n"), E("\n", "ab"), T(""), T("")],
            2,
            1,
            0,
            0,
            None,
        )

        odd_e = E("", "hi\nab")
        odd_e.set_edit_pos(2)
        # disble cursor movement in odd_e object
        odd_e.move_cursor_to_coords = lambda s, c, xy: 0
        self.ktest(
            "cursor force fail long",
            "page up",
            [odd_e, T("\n"), T("\n"), T("\n"), S(""), T("\n")],
            4,
            2,
            1,
            -1,
            None,
        )

        self.ktest(
            "prefer not cut off",
            "page up",
            [S("\n"), T("\n"), S(""), T("\n\n"), S(""), T("\n")],
            4,
            2,
            2,
            1,
            None,
        )

        self.ktest(
            "allow cut off",
            "page up",
            [S("\n"), T("\n"), T(""), T("\n\n"), S(""), T("\n")],
            4,
            2,
            0,
            -1,
            None,
        )

        self.ktest(
            "at top fail",
            "page up",
            [T("\n\n"), T("\n"), T("\n\n\n")],
            0,
            0,
            0,
            0,
            None,
        )

        self.ktest(
            "all visible fail",
            "page up",
            [T("a"), T("\n")],
            0,
            0,
            0,
            0,
            None,
        )

        self.ktest(
            "current ok fail",
            "page up",
            [T("\n\n"), S("hi")],
            1,
            3,
            1,
            3,
            None,
        )

        self.ktest(
            "all visible choose top selectable",
            "page up",
            [T(""), S("a"), S("b"), S("c")],
            3,
            3,
            1,
            1,
            None,
        )

        self.ktest(
            "bring in edge choose top",
            "page up",
            [S("b"), T("-"), S("-"), T("c"), S("d"), T("-")],
            4,
            3,
            0,
            0,
            None,
        )

        self.ktest(
            "bring in edge choose top selectable",
            "page up",
            [T("b"), S("-"), S("-"), T("c"), S("d"), T("-")],
            4,
            3,
            1,
            1,
            None,
        )

    def test4_page_down(self):
        T, S, E = urwid.Text, SelectableText, urwid.Edit

        self.ktest(
            "unselectable aligned to aligned",
            "page down",
            [T("\n\n"), T("\n"), T(""), T("\n\n"), T("\n"), T("")],
            2,
            4,
            4,
            3,
            None,
        )

        self.ktest(
            "unselectable unaligned to aligned",
            "page down",
            [T("\n\n"), T("\n"), T("\n"), T("\n"), T("\n"), T("")],
            2,
            4,
            4,
            3,
            None,
        )

        self.ktest(
            "selectable to unselectable",
            "page down",
            [T("\n\n"), S("\n"), T("\n"), T("\n"), T("\n"), T("")],
            1,
            2,
            4,
            4,
            None,
        )

        self.ktest(
            "selectable to cut off selectable",
            "page down",
            [T("\n\n"), S("\n"), T("\n"), T("\n"), S("\n\n")],
            1,
            2,
            4,
            3,
            None,
        )

        self.ktest(
            "seletable to selectable",
            "page down",
            [T("\n\n"), S("\n"), T("\n"), S("\n"), T("\n\n")],
            1,
            1,
            3,
            2,
            None,
        )

        self.ktest(
            "within very long selectable",
            "page down",
            [T("\n"), S("\n\n\n\n\n\n\n\n"), S("")],
            1,
            2,
            1,
            -3,
            None,
        )

        e = E("", "\nab\n\n\n\n\ncd\n\n")
        e.set_edit_pos(2)
        self.ktest(
            "within very long cursor widget",
            "page down",
            [T("\n"), e, S("")],
            1,
            2,
            1,
            -2,
            (1, 4),
        )

        odd_e = E("", "ab\n\n\n\n\n\n\n\n\n")
        odd_e.set_edit_pos(1)
        # disble cursor movement in odd_e object
        odd_e.move_cursor_to_coords = lambda s, c, xy: 0
        self.ktest(
            "pathological cursor widget",
            "page down",
            [T(""), odd_e, T("")],
            1,
            1,
            2,
            4,
            None,
        )

        e = E("", "\nab\n\n\n\n\ncd\n")
        e.set_edit_pos(2)
        self.ktest(
            "very long cursor widget snap",
            "page down",
            [T("\n"), e, T("")],
            1,
            2,
            1,
            -3,
            (1, 3),
        )

        self.ktest(
            "slight scroll selectable",
            "page down",
            [S(""), T("\n\n\n"), S(""), T(""), S("\n"), T("\n")],
            0,
            0,
            2,
            4,
            None,
        )

        self.ktest(
            "scroll into snap region",
            "page down",
            [S(""), T("\n\n\n"), T(""), T(""), S("\n"), T("\n")],
            0,
            0,
            4,
            3,
            None,
        )

        self.ktest(
            "mid scroll short",
            "page down",
            [T("\n"), S(""), T("\n"), T(""), S(""), T(""), T(""), T("\n")],
            1,
            2,
            4,
            3,
            None,
        )

        self.ktest(
            "mid scroll long",
            "page down",
            [T("\n"), S(""), T("\n"), T(""), S(""), T(""), S(""), T("\n")],
            1,
            2,
            6,
            4,
            None,
        )

        self.ktest(
            "mid scroll perfect",
            "page down",
            [T("\n"), S(""), T("\n"), T(""), S(""), S(""), S(""), T("\n")],
            1,
            2,
            5,
            4,
            None,
        )

        e = E("", "hi\nab")
        e.set_edit_pos(1)
        self.ktest(
            "cursor move up fail short",
            "page down",
            [T(""), T(""), e, T("\n"), T("\n")],
            2,
            1,
            2,
            -1,
            (1, 0),
        )

        odd_e = E("", "hi\nab")
        odd_e.set_edit_pos(1)
        # disble cursor movement in odd_e object
        odd_e.move_cursor_to_coords = lambda s, c, xy: 0
        self.ktest(
            "cursor force fail short",
            "page down",
            [T(""), T(""), odd_e, T("\n"), T("\n")],
            2,
            2,
            4,
            3,
            None,
        )

        self.ktest(
            "cursor force fail long",
            "page down",
            [T("\n"), S(""), T("\n"), T("\n"), T("\n"), E("hi\n", "ab")],
            1,
            2,
            4,
            4,
            None,
        )

        self.ktest(
            "prefer not cut off",
            "page down",
            [T("\n"), S(""), T("\n\n"), S(""), T("\n"), S("\n")],
            1,
            2,
            3,
            3,
            None,
        )

        self.ktest(
            "allow cut off",
            "page down",
            [T("\n"), S(""), T("\n\n"), T(""), T("\n"), S("\n")],
            1,
            2,
            5,
            4,
            None,
        )

        self.ktest(
            "at bottom fail",
            "page down",
            [T("\n\n"), T("\n"), T("\n\n\n")],
            2,
            1,
            2,
            1,
            None,
        )

        self.ktest(
            "all visible fail",
            "page down",
            [T("a"), T("\n")],
            1,
            1,
            1,
            1,
            None,
        )

        self.ktest(
            "current ok fail",
            "page down",
            [S("hi"), T("\n\n")],
            0,
            0,
            0,
            0,
            None,
        )

        self.ktest(
            "all visible choose last selectable",
            "page down",
            [S("a"), S("b"), S("c"), T("")],
            0,
            0,
            2,
            2,
            None,
        )

        self.ktest(
            "bring in edge choose last",
            "page down",
            [T("-"), S("d"), T("c"), S("-"), T("-"), S("b")],
            1,
            1,
            5,
            4,
            None,
        )

        self.ktest(
            "bring in edge choose last selectable",
            "page down",
            [T("-"), S("d"), T("c"), S("-"), S("-"), T("b")],
            1,
            1,
            4,
            3,
            None,
        )


class ZeroHeightContentsTest(unittest.TestCase):
    def test_listbox_pile(self):
        lb = urwid.ListBox(urwid.SimpleListWalker([urwid.Pile([])]))
        size = (2, 5)
        canvas = lb.render(size, focus=True)
        self.assertEqual([b"  ", b"  ", b"  ", b"  ", b"  "], canvas.text)

    def test_listbox_text_pile_page_down(self):
        lb = urwid.ListBox(urwid.SimpleListWalker([urwid.Text("above"), urwid.Pile([])]))
        size = (7, 5)
        lb.keypress(size, "page down")
        self.assertEqual(lb.focus_position, 0)
        lb.keypress(size, "page down")  # second one caused ListBox failure
        self.assertEqual(lb.focus_position, 0)
        canvas = lb.render(size, focus=True)
        self.assertEqual([b"above  ", b"       ", b"       ", b"       ", b"       "], canvas.text)

    def test_listbox_text_pile_page_up(self):
        lb = urwid.ListBox(urwid.SimpleListWalker([urwid.Pile([]), urwid.Text("below")]))
        size = (7, 5)
        lb.set_focus(1)
        lb.keypress(size, "page up")
        self.assertEqual(lb.focus_position, 1)
        lb.keypress(size, "page up")  # second one caused pile failure
        self.assertEqual(lb.focus_position, 1)
        canvas = lb.render(size, focus=True)
        self.assertEqual([b"below  ", b"       ", b"       ", b"       ", b"       "], canvas.text)

    def test_listbox_text_pile_down(self):
        sp = urwid.Pile([])
        sp.selectable = lambda: True  # abuse our Pile
        lb = urwid.ListBox(urwid.SimpleListWalker([urwid.Text("above"), sp]))
        size = (7, 5)
        lb.keypress(size, "down")
        self.assertEqual(lb.focus_position, 0)
        lb.keypress(size, "down")
        self.assertEqual(lb.focus_position, 0)
        canvas = lb.render(size, focus=True)
        self.assertEqual([b"above  ", b"       ", b"       ", b"       ", b"       "], canvas.text)

    def test_listbox_text_pile_up(self):
        sp = urwid.Pile([])
        sp.selectable = lambda: True  # abuse our Pile
        lb = urwid.ListBox(urwid.SimpleListWalker([sp, urwid.Text("below")]))
        size = (7, 5)
        lb.set_focus(1)
        lb.keypress(size, "up")
        self.assertEqual(lb.focus_position, 1)
        lb.keypress(size, "up")
        self.assertEqual(lb.focus_position, 1)
        canvas = lb.render(size, focus=True)
        self.assertEqual([b"below  ", b"       ", b"       ", b"       ", b"       "], canvas.text)


class PageDownAboveTopTest(unittest.TestCase):
    def test_page_down_does_not_raise(self):
        # Two-row rows so the four-item list does not fit the viewport at once.
        lb = urwid.ListBox(
            urwid.SimpleListWalker(
                [
                    urwid.Text("a0\nb0"),
                    SelectableText("a1\nb1"),
                    urwid.Text("a2\nb2"),
                    urwid.Text("a3\nb3"),
                ]
            )
        )
        size = (7, 4)
        lb.set_focus(0)
        lb.render(size, focus=True)
        lb.keypress(size, "page down")  # used to raise ListBoxError
        self.assertEqual(lb.focus_position, 3)
        canvas = lb.render(size, focus=True)
        self.assertEqual([b"a2     ", b"b2     ", b"a3     ", b"b3     "], canvas.text)
        # a second page down at the bottom is a no-op, not a crash
        lb.keypress(size, "page down")
        self.assertEqual(lb.focus_position, 3)


class ListBoxSetBodyTest(unittest.TestCase):
    def test_signal_connected(self):
        lb = urwid.ListBox([])
        lb.body = urwid.SimpleListWalker([])
        self.assertEqual(
            lb.body._urwid_signals["modified"][0][1],
            lb._invalidate,
            "outdated canvas cache reuse after ListWalker's contents modified",
        )


class TestListWalkerFromIterable(unittest.TestCase):
    def test_01_simple_list_walker(self):
        walker = urwid.SimpleListWalker(str(num) for num in range(5))
        self.assertEqual(5, len(walker))

    def test_02_simple_focus_list_walker(self):
        walker = urwid.SimpleFocusListWalker(str(num) for num in range(5))
        self.assertEqual(5, len(walker))


class ListBoxConsumerApiTest(unittest.TestCase):
    def test_simple_list_walker_clear_and_append(self) -> None:
        walker = urwid.SimpleListWalker([urwid.Text("old")])
        listbox = urwid.ListBox(walker)

        walker.clear()
        walker.append(urwid.AttrMap(urwid.Text("new"), None))

        self.assertEqual(1, len(listbox))
        self.assertEqual(0, listbox.focus_position)
        self.assertEqual("new", listbox.focus.original_widget.text)

    def test_set_focus_and_len(self) -> None:
        items = [urwid.Text(str(idx)) for idx in range(3)]
        listbox = urwid.ListBox(urwid.SimpleListWalker(items))

        listbox.set_focus(2)
        self.assertEqual(2, listbox.focus_position)
        self.assertIs(items[2], listbox.focus)
        self.assertEqual(3, len(listbox))
        self.assertEqual([items[2]], listbox.get_focus_widgets())


class DuckTypedWalker:
    """Minimal duck-typed ListWalker-like object (not a ListWalker subclass)."""

    def __init__(self, widgets):
        self._widgets = widgets
        self._focus = 0

    def get_focus(self):
        if not self._widgets:
            return None, None
        return self._widgets[self._focus], self._focus

    def get_next(self, position):
        pos = position + 1
        if pos >= len(self._widgets):
            return None, None
        return self._widgets[pos], pos

    def get_prev(self, position):
        pos = position - 1
        if pos < 0:
            return None, None
        return self._widgets[pos], pos

    def set_focus(self, position):
        self._focus = position


class V1ProtocolWalker(urwid.ListWalker):
    """ListWalker subclass without a ``__getitem__()``, to exercise the v1 contents protocol."""

    def __init__(self, widgets):
        self._widgets = widgets
        self.focus = 0

    def get_focus(self):
        if not self._widgets:
            return None, None
        return self._widgets[self.focus], self.focus

    def get_next(self, position):
        pos = position + 1
        if pos >= len(self._widgets):
            return None, None
        return self._widgets[pos], pos

    def get_prev(self, position):
        pos = position - 1
        if pos < 0:
            return None, None
        return self._widgets[pos], pos

    def set_focus(self, position):
        self.focus = position
        self._modified()


class _LeafNode(urwid.TreeNode):
    pass


class _RootNode(urwid.ParentNode):
    """Minimal tree used to build a real urwid.TreeWalker, which (like a few other ListWalker implementations)
    has no positions() method -- unlike inventing a throwaway stand-in,
    this exercises ListBox's "no positions()" fallback paths with an existing ListWalker subclass from the codebase.
    """

    def __init__(self, n_children):
        self._n_children = n_children
        super().__init__("root", key="root", depth=0)

    def load_child_keys(self):
        return list(range(self._n_children))

    def load_child_node(self, key):
        return _LeafNode(f"item{key}", parent=self, key=key, depth=1)


def make_tree_walker(n_children=4, focus_key=0):
    root = _RootNode(n_children)
    walker = urwid.TreeWalker(root.get_child_node(focus_key))
    return walker, root


class EmptyNoPositionsWalker(urwid.ListWalker):
    """ListWalker subclass without positions() that can also be empty.

    urwid.TreeWalker always has a focus node and cannot represent "no widgets",
    so it cannot be used for this specific empty-body case.
    """

    def get_focus(self):
        return None, None


class ListBoxInitAndBodySetterTest(unittest.TestCase):
    def test_init_duck_typed_body_warns(self):
        widgets = [urwid.Text("a"), urwid.Text("b")]
        walker = DuckTypedWalker(widgets)
        with self.assertWarns(DeprecationWarning):
            lbox = urwid.ListBox(walker)
        self.assertIs(lbox.body, walker)
        # non-ListWalker body has no "modified" signal, so caching is disabled
        canvas = lbox.render((4, 2), focus=True)
        self.assertEqual([b"a   ", b"b   "], canvas.text)

    def test_body_setter_duck_typed_warns(self):
        lbox = urwid.ListBox(urwid.SimpleListWalker([urwid.Text("a")]))
        walker = DuckTypedWalker([urwid.Text("x")])
        with self.assertWarns(DeprecationWarning):
            lbox.body = walker
        self.assertIs(lbox.body, walker)

    def test_body_setter_plain_iterable(self):
        lbox = urwid.ListBox(urwid.SimpleListWalker([urwid.Text("a")]))
        lbox.body = [urwid.Text("x"), urwid.Text("y")]
        self.assertIsInstance(lbox.body, urwid.SimpleListWalker)
        self.assertEqual(2, len(lbox.body))

    def test_length_hint_sized(self):
        lbox = urwid.ListBox(urwid.SimpleListWalker([urwid.Text(str(i)) for i in range(3)]))
        self.assertEqual(3, lbox.__length_hint__())

    def test_length_hint_not_sized(self):
        class TestWalker(urwid.ListWalker):
            @property
            def contents(self):
                return self

            @staticmethod
            def next_position(position: int) -> tuple[urwid.Text, int]:
                return urwid.Text(str(position)), position

            @staticmethod
            def prev_position(position: int) -> tuple[urwid.Text, int]:
                return urwid.Text(str(position)), position

        lbox = urwid.ListBox(TestWalker())
        with self.assertRaises(AttributeError):
            lbox.__length_hint__


class ListBoxScrollProtocolTest(unittest.TestCase):
    def test_check_support_scrolling_missing_methods(self):
        class NoGetPrevWalker:
            def __init__(self, widgets):
                self._widgets = widgets
                self._focus = 0

            def get_focus(self):
                return self._widgets[self._focus], self._focus

            def get_next(self, position):
                return None, None

            def set_focus(self, position):
                self._focus = position

        with self.assertWarns(DeprecationWarning):
            lbox = urwid.ListBox(NoGetPrevWalker([urwid.Text("a")]))
        with self.assertRaises(urwid.ListBoxError):
            lbox.rows_max()

    def test_check_support_scrolling_not_sized(self):
        with self.assertWarns(DeprecationWarning):
            lbox = urwid.ListBox(DuckTypedWalker([urwid.Text("a")]))
        with self.assertRaises(urwid.ListBoxError):
            lbox.get_scrollpos()

    def test_check_support_scrolling_wrap_around(self):
        lbox = urwid.ListBox(urwid.SimpleListWalker([urwid.Text("a"), urwid.Text("b")], wrap_around=True))
        with self.assertRaises(urwid.ListBoxError):
            lbox.get_first_visible_pos((4, 5))

    def test_scroll_protocol_empty_body(self):
        lbox = urwid.ListBox(urwid.SimpleListWalker([]))
        self.assertEqual(0, lbox.get_scrollpos((4, 5)))
        self.assertEqual(0, lbox.get_first_visible_pos((4, 5)))
        self.assertEqual(1, lbox.get_visible_amount((4, 5)))

    def test_scroll_protocol_focus_at_top(self):
        # focus at position 0 means nothing is above it, so top.fill is empty
        # and get_scrollpos()/get_first_visible_pos() fall back to focus_pos.
        items = [urwid.Text(str(i)) for i in range(20)]
        lbox = urwid.ListBox(urwid.SimpleListWalker(items))
        size = (4, 5)
        self.assertEqual(0, lbox.get_scrollpos(size))
        self.assertEqual(0, lbox.get_first_visible_pos(size))

    def test_rows_max_no_focus(self):
        lbox = urwid.ListBox(urwid.SimpleListWalker([]))
        self.assertEqual(0, lbox.rows_max((4, 5)))

    def test_scroll_protocol(self):
        items = [urwid.Text(str(i)) for i in range(20)]
        lbox = urwid.ListBox(urwid.SimpleListWalker(items))
        lbox.set_focus(10)
        size = (4, 5)

        pos = lbox.get_scrollpos(size)
        self.assertIsInstance(pos, int)

        rows = lbox.rows_max(size)
        self.assertIsInstance(rows, int)
        # second call without size hits the cached branch
        self.assertEqual(rows, lbox.rows_max())

        first_visible = lbox.get_first_visible_pos(size)
        self.assertIsInstance(first_visible, int)

        visible_amount = lbox.get_visible_amount(size)
        self.assertGreaterEqual(visible_amount, 1)

        self.assertFalse(lbox.require_relative_scroll((4, 10)))
        big_lbox = urwid.ListBox(urwid.SimpleListWalker([urwid.Text(str(i)) for i in range(100)]))
        self.assertTrue(big_lbox.require_relative_scroll((4, 2)))


class ListBoxRenderEmptyTest(unittest.TestCase):
    def test_render_empty_listbox(self):
        lbox = urwid.ListBox(urwid.SimpleListWalker([]))
        canvas = lbox.render((4, 5))
        self.assertEqual([b"    "] * 5, canvas.text)

    def test_render_row_count_mismatch(self):
        class BadRowsText(urwid.Text):
            def rows(self, size, focus=False):
                return super().rows(size, focus) + 1

        lbox = urwid.ListBox(urwid.SimpleListWalker([BadRowsText("a"), urwid.Text("b")]))
        with self.assertRaises(urwid.ListBoxError):
            lbox.render((4, 5), focus=True)

    def test_render_fill_above_row_count_mismatch(self):
        class BadRowsText(urwid.Text):
            def rows(self, size, focus=False):
                return super().rows(size, focus) + 1

        lbox = urwid.ListBox(urwid.SimpleListWalker([BadRowsText("a"), urwid.Text("b")]))
        lbox.set_focus(1)
        lbox.shift_focus((4, 10), 1)
        with self.assertRaises(urwid.ListBoxError):
            lbox.render((4, 5), focus=True)

    def test_render_fill_below_row_count_mismatch(self):
        class BadRowsText(urwid.Text):
            def rows(self, size, focus=False):
                return super().rows(size, focus) + 1

        lbox = urwid.ListBox(urwid.SimpleListWalker([urwid.Text("a"), BadRowsText("b")]))
        with self.assertRaises(urwid.ListBoxError):
            lbox.render((4, 5), focus=True)

    def test_render_cursor_mismatch(self):
        class LyingCursorEdit(urwid.Edit):
            def render(self, size, focus=False):
                canvas = super().render(size, focus)
                if focus:
                    canvas = urwid.CompositeCanvas(canvas)
                    canvas.cursor = (0, 0)
                return canvas

        e = LyingCursorEdit("", "ab")
        lbox = urwid.ListBox(urwid.SimpleListWalker([e]))
        with self.assertRaises(urwid.ListBoxError):
            lbox.render((4, 5), focus=True)

    def test_render_too_short_extra_widget(self):
        class FlakyNextWalker(urwid.ListWalker):
            """A ListWalker that claims there is nothing below the focus while calculate_visible() is filling the view.

            It then reveals a real, non-empty widget when render() double-checks afterwards --
            this simulates a buggy/inconsistent ListWalker implementation.
            """

            def __init__(self, widgets):
                self._widgets = widgets
                self.focus = 0
                self._calls = 0

            def get_focus(self):
                return self._widgets[self.focus], self.focus

            def get_next(self, position):
                self._calls += 1
                if self._calls <= 2:
                    return None, None
                pos = position + 1
                if pos >= len(self._widgets):
                    return None, None
                return self._widgets[pos], pos

            def get_prev(self, position):
                if position <= 0:
                    return None, None
                return self._widgets[position - 1], position - 1

            def set_focus(self, position):
                self.focus = position

        lbox = urwid.ListBox(FlakyNextWalker([urwid.Text("a"), urwid.Text("b")]))
        with self.assertRaises(urwid.ListBoxError):
            lbox.render((4, 5), focus=True)

    def test_render_infinite_next_position_guard(self):
        class LoopingWalker(urwid.ListWalker):
            """Like FlakyNextWalker above,
            it claims there is nothing below the focus while calculate_visible() fills the view.

            On every subsequent call it keeps reporting the very same zero-row widget/position pair --
            simulating a buggy next_position() that never advances.
            """

            def __init__(self, widgets):
                self._widgets = widgets
                self.focus = 0
                self._calls = 0

            def get_focus(self):
                return self._widgets[self.focus], self.focus

            def get_next(self, position):
                self._calls += 1
                if self._calls <= 2:
                    return None, None
                return self._widgets[-1], len(self._widgets) - 1

            def get_prev(self, position):
                if position <= 0:
                    return None, None
                return self._widgets[position - 1], position - 1

            def set_focus(self, position):
                self.focus = position

        zero_rows = urwid.Pile([])
        zero_rows.selectable = lambda: False
        lbox = urwid.ListBox(LoopingWalker([urwid.Text("a"), zero_rows]))
        with self.assertRaises(urwid.ListBoxError):
            lbox.render((4, 5), focus=True)


class ListBoxCalculateVisibleEdgeTest(unittest.TestCase):
    def test_calculate_visible_empty(self):
        lbox = urwid.ListBox(urwid.SimpleListWalker([]))
        self.assertEqual((None, None, None), lbox.calculate_visible((4, 5)))

    def test_calculate_visible_skips_zero_height_above(self):
        body = urwid.SimpleListWalker([urwid.Pile([]), urwid.Text("a")])
        lbox = urwid.ListBox(body)
        lbox.body.set_focus(1)
        lbox.offset_rows = 1
        lbox.inset_fraction = (0, 1)
        middle, top, bottom = lbox.calculate_visible((4, 5))
        self.assertIsNotNone(middle)

    def test_calculate_visible_fill_from_top_partial(self):
        text = "\n".join(str(i) for i in range(8))
        lbox = urwid.ListBox(urwid.SimpleListWalker([urwid.Text(text)]))
        lbox.set_focus_pending = None
        lbox.shift_focus((4, 10), -6)
        canvas = lbox.render((4, 5), focus=True)
        self.assertEqual(5, canvas.rows())


class ListBoxGetCursorCoordsTest(unittest.TestCase):
    def test_empty(self):
        lbox = urwid.ListBox(urwid.SimpleListWalker([]))
        self.assertIsNone(lbox.get_cursor_coords((4, 5)))

    def test_no_cursor(self):
        lbox = urwid.ListBox(urwid.SimpleListWalker([urwid.Text("a")]))
        self.assertIsNone(lbox.get_cursor_coords((4, 5)))

    def test_with_cursor(self):
        e = urwid.Edit("", "ab")
        lbox = urwid.ListBox(urwid.SimpleListWalker([e]))
        self.assertEqual((2, 0), lbox.get_cursor_coords((4, 5)))

    def test_cursor_kept_in_view_by_offset_adjustment(self):
        # calculate_visible() actively re-adjusts the offset/inset so a visible
        # cursor always lands within the rendered rows; get_cursor_coords()'s own
        # out-of-range guard (`y < 0 or y >= maxrow`) is therefore not reachable
        # through this path and is left uncovered as a defensive check.
        e = urwid.Edit("", "ab")
        lbox = urwid.ListBox(urwid.SimpleListWalker([urwid.Text("\n\n\n\n\n"), e]))
        lbox.set_focus(1)
        lbox.shift_focus((4, 20), 10)
        x, y = lbox.get_cursor_coords((4, 5))
        self.assertTrue(0 <= y < 5)


class ListBoxSetFocusErrorsTest(unittest.TestCase):
    def test_invalid_coming_from(self):
        lbox = urwid.ListBox(urwid.SimpleListWalker([urwid.Text("a")]))
        with self.assertRaises(urwid.ListBoxError):
            lbox.set_focus(0, "sideways")

    def test_no_set_focus_method(self):
        class NoSetFocusWalker(urwid.ListWalker):
            def get_focus(self):
                return urwid.Text("a"), 0

        lbox = urwid.ListBox(NoSetFocusWalker())
        with self.assertRaises(TypeError):
            lbox.set_focus(0)

    def test_empty_listbox(self):
        class EmptyWalker(urwid.ListWalker):
            def get_focus(self):
                return None, None

            def set_focus(self, position):
                pass

        lbox = urwid.ListBox(EmptyWalker())
        with self.assertRaises(IndexError):
            lbox.set_focus(0)

    def test_focus_position_empty(self):
        lbox = urwid.ListBox(urwid.SimpleListWalker([]))
        with self.assertRaises(IndexError):
            _ = lbox.focus_position


class ListBoxContentsTest(unittest.TestCase):
    def test_getitem_len_repr(self):
        items = [urwid.Text(str(i)) for i in range(3)]
        lbox = urwid.ListBox(urwid.SimpleListWalker(items))
        contents = lbox.contents

        self.assertEqual(3, len(contents))
        widget, options = contents[1]
        self.assertIs(items[1], widget)
        self.assertIsNone(options)
        self.assertIn("ListBoxContents", repr(contents))

        with self.assertRaises(KeyError):
            contents[100]

    def test_getitem_v1_protocol(self):
        widgets = [urwid.Text(str(i)) for i in range(3)]
        lbox = urwid.ListBox(V1ProtocolWalker(widgets))
        contents = lbox.contents

        widget = contents[1]
        self.assertIs(widgets[1], widget)
        self.assertEqual(0, lbox.body.focus)

        with self.assertRaises(KeyError):
            contents[100]

    def test_getitem_no_set_focus(self):
        class NoGetItemNoSetFocus(urwid.ListWalker):
            def get_focus(self):
                return urwid.Text("a"), 0

        lbox = urwid.ListBox(NoGetItemNoSetFocus())
        with self.assertRaises(TypeError):
            _ = lbox.contents[0]

    def test_options(self):
        lbox = urwid.ListBox(urwid.SimpleListWalker([urwid.Text("a")]))
        self.assertIsNone(lbox.options())


class ListBoxSetFocusValignTest(unittest.TestCase):
    def test_set_focus_valign_middle(self):
        lbox = urwid.ListBox(urwid.SimpleListWalker([urwid.Text(str(i)) for i in range(5)]))
        lbox.set_focus_valign("middle")
        lbox.render((4, 5), focus=True)
        self.assertIsInstance(lbox.offset_rows, int)

    def test_set_focus_valign_empty(self):
        walker = urwid.SimpleListWalker([urwid.Text("a")])
        lbox = urwid.ListBox(walker)
        lbox.render((4, 5), focus=True)  # resolve the initial "first selectable" pending
        walker.clear()
        lbox.set_focus_valign("middle")
        lbox.render((4, 5), focus=True)  # must not raise; body is now empty


class ListBoxFirstSelectableTest(unittest.TestCase):
    def test_focus_already_selectable(self):
        lbox = urwid.ListBox(urwid.SimpleListWalker([SelectableText("a"), urwid.Text("b")]))
        lbox.render((4, 5), focus=True)
        self.assertEqual(0, lbox.focus_position)

    def test_picks_later_selectable_widget(self):
        lbox = urwid.ListBox(urwid.SimpleListWalker([urwid.Text("a"), SelectableText("b"), urwid.Text("c")]))
        lbox.render((4, 5), focus=True)
        self.assertEqual(1, lbox.focus_position)

    def test_no_set_focus_method(self):
        class NoSetFocusWalker(urwid.ListWalker):
            def __init__(self, widgets):
                self._widgets = widgets

            def get_focus(self):
                return self._widgets[0], 0

            def get_next(self, position):
                pos = position + 1
                if pos >= len(self._widgets):
                    return None, None
                return self._widgets[pos], pos

            def get_prev(self, position):
                return None, None

        lbox = urwid.ListBox(NoSetFocusWalker([urwid.Text("a"), urwid.Text("b")]))
        with self.assertRaises(TypeError):
            lbox.render((4, 5), focus=True)


class ListBoxSetFocusCompleteTest(unittest.TestCase):
    def test_type_error_when_body_loses_set_focus(self):
        class FlakyWalker(urwid.ListWalker):
            def __init__(self, widgets):
                self._widgets = widgets
                self.focus = 0
                self.set_focus = self._do_set_focus

            def get_focus(self):
                return self._widgets[self.focus], self.focus

            def _do_set_focus(self, position):
                self.focus = position
                self._modified()

        walker = FlakyWalker([urwid.Text("a"), urwid.Text("b"), urwid.Text("c")])
        lbox = urwid.ListBox(walker)
        lbox.set_focus(1)
        del walker.set_focus
        with self.assertRaises(TypeError):
            lbox.render((4, 5), focus=True)

    def test_middle_none_after_restore(self):
        class ShrinkingWalker(urwid.ListWalker):
            def __init__(self, widgets):
                self._widgets = widgets
                self.focus = 0

            def get_focus(self):
                if 0 <= self.focus < len(self._widgets):
                    return self._widgets[self.focus], self.focus
                return None, None

            def set_focus(self, position):
                self.focus = position
                self._modified()

        walker = ShrinkingWalker([urwid.Text("a"), urwid.Text("b"), urwid.Text("c")])
        lbox = urwid.ListBox(walker)
        lbox.set_focus(2)
        walker._widgets = []
        lbox.render((4, 5), focus=True)  # must not raise

    def test_coming_from_scroll_down_then_up(self):
        items = [urwid.Text(str(i)) for i in range(20)]
        lbox = urwid.ListBox(urwid.SimpleListWalker(items))
        lbox.set_focus(10)
        lbox.render((4, 5), focus=True)
        lbox.set_focus(8, "above")
        lbox.render((4, 5), focus=True)
        self.assertEqual(8, lbox.focus_position)

    def test_coming_from_scroll_visible_below(self):
        items = [urwid.Text(str(i)) for i in range(20)]
        lbox = urwid.ListBox(urwid.SimpleListWalker(items))
        lbox.render((4, 5), focus=True)
        lbox.set_focus(3, "below")
        lbox.render((4, 5), focus=True)
        self.assertEqual(3, lbox.focus_position)

    def test_far_jump_no_coming_from(self):
        items = [urwid.Text(str(i)) for i in range(50)]
        lbox = urwid.ListBox(urwid.SimpleListWalker(items))
        lbox.render((4, 5), focus=True)
        lbox.set_focus(40)
        lbox.render((4, 5), focus=True)
        self.assertEqual(40, lbox.focus_position)

    def test_far_jump_coming_from_above(self):
        items = [urwid.Text(str(i)) for i in range(50)]
        lbox = urwid.ListBox(urwid.SimpleListWalker(items))
        lbox.render((4, 5), focus=True)
        lbox.set_focus(40, "above")
        lbox.render((4, 5), focus=True)
        self.assertEqual(40, lbox.focus_position)

    def test_far_jump_coming_from_below(self):
        items = [urwid.Text(str(i)) for i in range(50)]
        lbox = urwid.ListBox(urwid.SimpleListWalker(items))
        lbox.render((4, 5), focus=True)
        lbox.set_focus(40, "below")
        lbox.render((4, 5), focus=True)
        self.assertEqual(40, lbox.focus_position)


class ListBoxShiftFocusErrorsTest(unittest.TestCase):
    def test_offset_too_large(self):
        lbox = urwid.ListBox(urwid.SimpleListWalker([urwid.Text("a")]))
        with self.assertRaises(urwid.ListBoxError):
            lbox.shift_focus((4, 5), 5)

    def test_negative_offset_too_large(self):
        lbox = urwid.ListBox(urwid.SimpleListWalker([urwid.Text("a")]))
        with self.assertRaises(urwid.ListBoxError):
            lbox.shift_focus((4, 5), -1)


class ListBoxUpdatePrefColTest(unittest.TestCase):
    def test_empty_listbox(self):
        lbox = urwid.ListBox(urwid.SimpleListWalker([]))
        lbox.update_pref_col_from_focus((4, 5))
        self.assertEqual("left", lbox.pref_col)

    def test_from_cursor_coords_only(self):
        class CoordsOnlyWidget(urwid.Text):
            def get_cursor_coords(self, size):
                return (2, 0)

        lbox = urwid.ListBox(urwid.SimpleListWalker([CoordsOnlyWidget("hi")]))
        lbox.update_pref_col_from_focus((4, 5))
        self.assertEqual(2, lbox.pref_col)


class ListBoxChangeFocusErrorsTest(unittest.TestCase):
    def test_no_set_focus(self):
        class NoSetFocus(urwid.ListWalker):
            def get_focus(self):
                return urwid.Text("a"), 0

        lbox = urwid.ListBox(NoSetFocus())
        with self.assertRaises(TypeError):
            lbox.change_focus((4, 5), 0)

    def test_invalid_offset_inset(self):
        lbox = urwid.ListBox(urwid.SimpleListWalker([urwid.Text("a"), urwid.Text("b")]))
        with self.assertRaises(urwid.ListBoxError):
            lbox.change_focus((4, 5), 1, offset_inset=-5)

    def test_cursor_row_unspecified_no_coming_from(self):
        e = urwid.Edit("", "hello")
        lbox = urwid.ListBox(urwid.SimpleListWalker([e]))
        with self.assertRaises(ValueError):
            lbox.change_focus((4, 5), 0, cursor_coords=(2,))

    def test_cursor_row_out_of_range(self):
        e = urwid.Edit("", "hello")
        lbox = urwid.ListBox(urwid.SimpleListWalker([e]))
        with self.assertRaises(urwid.ListBoxError):
            lbox.change_focus((4, 5), 0, cursor_coords=(2, 99))

    def test_cursor_coords_no_coming_from(self):
        e = urwid.Edit("", "hello")
        lbox = urwid.ListBox(urwid.SimpleListWalker([e]))
        lbox.change_focus((4, 5), 0, cursor_coords=(2, 0))
        self.assertEqual((2, 0), e.get_cursor_coords((4,)))


class ListBoxGetFocusOffsetInsetErrorsTest(unittest.TestCase):
    def test_invalid_inset_fraction(self):
        lbox = urwid.ListBox(urwid.SimpleListWalker([urwid.Text("a")]))
        lbox.offset_rows = 0
        lbox.inset_fraction = (5, 3)
        with self.assertRaises(urwid.ListBoxError):
            lbox.get_focus_offset_inset((4, 5))


class ListBoxMakeCursorVisibleTest(unittest.TestCase):
    def test_empty(self):
        lbox = urwid.ListBox(urwid.SimpleListWalker([]))
        lbox.make_cursor_visible((4, 5))  # must not raise

    def test_not_selectable(self):
        lbox = urwid.ListBox(urwid.SimpleListWalker([urwid.Text("a")]))
        lbox.make_cursor_visible((4, 5))  # must not raise

    def test_no_get_cursor_coords(self):
        lbox = urwid.ListBox(urwid.SimpleListWalker([SelectableText("a")]))
        lbox.make_cursor_visible((4, 5))  # must not raise

    def test_cursor_none(self):
        class CursorNoneWidget(SelectableText):
            def get_cursor_coords(self, size):
                return None

        lbox = urwid.ListBox(urwid.SimpleListWalker([CursorNoneWidget("a")]))
        lbox.make_cursor_visible((4, 5))  # must not raise

    def test_already_visible(self):
        e = urwid.Edit("", "ab")
        lbox = urwid.ListBox(urwid.SimpleListWalker([e]))
        lbox.make_cursor_visible((4, 5))
        self.assertEqual(0, lbox.offset_rows)


class ListBoxKeypressEdgeTest(unittest.TestCase):
    def test_keypress_empty_listbox(self):
        lbox = urwid.ListBox(urwid.SimpleListWalker([]))
        self.assertEqual("up", lbox.keypress((4, 5), "up"))

    def test_keypress_unhandled_key(self):
        lbox = urwid.ListBox(urwid.SimpleListWalker([urwid.Text("a")]))
        self.assertEqual("x", lbox.keypress((4, 5), "x"))

    def test_keypress_page_up_middle_none(self):
        class FlakyEmptyWalker(urwid.ListWalker):
            def __init__(self, widget):
                self._widget = widget
                self._calls = 0

            def get_focus(self):
                self._calls += 1
                if self._calls <= 3:
                    return self._widget, 0
                return None, None

            def get_next(self, position):
                return None, None

            def get_prev(self, position):
                return None, None

            def set_focus(self, position):
                pass

        lbox = urwid.ListBox(FlakyEmptyWalker(urwid.Text("a")))
        self.assertEqual("page up", lbox.keypress((4, 5), "page up"))

    def test_keypress_page_down_middle_none(self):
        class FlakyEmptyWalker(urwid.ListWalker):
            def __init__(self, widget):
                self._widget = widget
                self._calls = 0

            def get_focus(self):
                self._calls += 1
                if self._calls <= 3:
                    return self._widget, 0
                return None, None

            def get_next(self, position):
                return None, None

            def get_prev(self, position):
                return None, None

            def set_focus(self, position):
                pass

        lbox = urwid.ListBox(FlakyEmptyWalker(urwid.Text("a")))
        self.assertEqual("page down", lbox.keypress((4, 5), "page down"))

    def test_page_up_all_visible_selectable_at_top(self):
        body = [SelectableText("a"), SelectableText("b"), SelectableText("c")]
        lbox = urwid.ListBox(urwid.SimpleListWalker(body))
        lbox.set_focus(2)
        lbox.keypress((4, 5), "page up")  # must not raise

    def test_page_down_all_visible_selectable_at_bottom(self):
        body = [SelectableText("a"), SelectableText("b"), SelectableText("c")]
        lbox = urwid.ListBox(urwid.SimpleListWalker(body))
        lbox.keypress((4, 5), "page down")  # must not raise

    def test_page_up_zero_row_selectable(self):
        zero = urwid.Pile([])
        zero.selectable = lambda: True
        body = [zero, urwid.Text("\n"), urwid.Text("\n"), SelectableText("\n\n")]
        lbox = urwid.ListBox(urwid.SimpleListWalker(body))
        lbox.set_focus(3)
        lbox.shift_focus((4, 10), 3)
        lbox.keypress((4, 5), "page up")  # must not raise

    def test_page_down_zero_row_selectable(self):
        zero = urwid.Pile([])
        zero.selectable = lambda: True
        body = [SelectableText("\n\n"), urwid.Text("\n"), urwid.Text("\n"), zero]
        lbox = urwid.ListBox(urwid.SimpleListWalker(body))
        lbox.shift_focus((4, 10), 0)
        lbox.keypress((4, 5), "page down")  # must not raise

    def test_keypress_home_end(self):
        items = [urwid.Text(str(i)) for i in range(10)]
        lbox = urwid.ListBox(urwid.SimpleListWalker(items))
        lbox.set_focus(5)
        lbox.keypress((4, 5), "home")
        self.assertEqual(0, lbox.focus_position)
        lbox.keypress((4, 5), "end")
        self.assertEqual(9, lbox.focus_position)

    def test_keypress_max_left_no_positions(self):
        walker, _root = make_tree_walker(3)
        lbox = urwid.ListBox(walker)
        with self.assertRaises(TypeError):
            lbox.keypress((20, 5), "home")

    def test_keypress_max_right_no_positions(self):
        walker, _root = make_tree_walker(3)
        lbox = urwid.ListBox(walker)
        with self.assertRaises(TypeError):
            lbox.keypress((20, 5), "end")

    def test_keypress_up_middle_none(self):
        class FlakyEmptyWalker(urwid.ListWalker):
            def __init__(self, widget):
                self._widget = widget
                self._calls = 0

            def get_focus(self):
                self._calls += 1
                if self._calls <= 3:
                    return self._widget, 0
                return None, None

            def get_next(self, position):
                return None, None

            def get_prev(self, position):
                return None, None

            def set_focus(self, position):
                pass

        lbox = urwid.ListBox(FlakyEmptyWalker(urwid.Text("a")))
        self.assertEqual("up", lbox.keypress((4, 5), "up"))

    def test_keypress_down_middle_none(self):
        class FlakyEmptyWalker(urwid.ListWalker):
            def __init__(self, widget):
                self._widget = widget
                self._calls = 0

            def get_focus(self):
                self._calls += 1
                if self._calls <= 3:
                    return self._widget, 0
                return None, None

            def get_next(self, position):
                return None, None

            def get_prev(self, position):
                return None, None

            def set_focus(self, position):
                pass

        lbox = urwid.ListBox(FlakyEmptyWalker(urwid.Text("a")))
        self.assertEqual("down", lbox.keypress((4, 5), "down"))


class NoMouseEventWidget:
    """A minimal flow widget that does not implement Widget's mouse_event API."""

    _sizing = frozenset([urwid.Sizing.FLOW])

    def __init__(self, text="x"):
        self._text = text

    def selectable(self):
        return False

    def rows(self, size, focus=False):
        return 1

    def render(self, size, focus=False):
        return urwid.Text(self._text).render(size, focus)


class ListBoxMouseEventTest(unittest.TestCase):
    def test_mouse_event_empty(self):
        lbox = urwid.ListBox(urwid.SimpleListWalker([]))
        self.assertFalse(lbox.mouse_event((4, 5), "mouse press", 1, 0, 0, True))

    def test_mouse_event_click_changes_focus(self):
        items = [SelectableText(str(i)) for i in range(5)]
        lbox = urwid.ListBox(urwid.SimpleListWalker(items))
        lbox.mouse_event((4, 5), "mouse press", 1, 0, 2, True)
        self.assertEqual(2, lbox.focus_position)

    def test_mouse_event_no_row_match(self):
        items = [urwid.Text("a")]
        lbox = urwid.ListBox(urwid.SimpleListWalker(items))
        result = lbox.mouse_event((4, 5), "mouse press", 1, 0, 4, True)
        self.assertFalse(result)

    def test_mouse_event_widget_without_mouse_event(self):
        w = NoMouseEventWidget()
        lbox = urwid.ListBox(urwid.SimpleListWalker([w]))
        with self.assertWarns(DeprecationWarning):
            result = lbox.mouse_event((4, 5), "mouse press", 1, 0, 0, True)
        self.assertFalse(result)

    def test_mouse_event_scroll_up(self):
        items = [urwid.Text(str(i)) for i in range(20)]
        lbox = urwid.ListBox(urwid.SimpleListWalker(items))
        lbox.set_focus(10)
        lbox.render((4, 5), focus=True)
        handled = lbox.mouse_event((4, 5), "mouse press", 4, 0, 0, True)
        self.assertTrue(handled)

    def test_mouse_event_scroll_down(self):
        items = [urwid.Text(str(i)) for i in range(20)]
        lbox = urwid.ListBox(urwid.SimpleListWalker(items))
        lbox.render((4, 5), focus=True)
        handled = lbox.mouse_event((4, 5), "mouse press", 5, 0, 0, True)
        self.assertTrue(handled)

    def test_mouse_event_release_no_scroll(self):
        items = [urwid.Text(str(i)) for i in range(5)]
        lbox = urwid.ListBox(urwid.SimpleListWalker(items))
        result = lbox.mouse_event((4, 5), "mouse release", 1, 0, 0, True)
        self.assertFalse(result)

    def test_mouse_event_widget_handles_click(self):
        cb = urwid.CheckBox("opt")
        lbox = urwid.ListBox(urwid.SimpleListWalker([cb]))
        handled = lbox.mouse_event((10, 5), "mouse press", 1, 2, 0, True)
        self.assertTrue(handled)
        self.assertTrue(cb.state)


class ListBoxEndsVisibleTest(unittest.TestCase):
    def test_ends_visible_empty(self):
        lbox = urwid.ListBox(urwid.SimpleListWalker([]))
        self.assertEqual(["top", "bottom"], lbox.ends_visible((4, 5)))

    def test_ends_visible_both(self):
        items = [urwid.Text(str(i)) for i in range(3)]
        lbox = urwid.ListBox(urwid.SimpleListWalker(items))
        result = lbox.ends_visible((4, 5), focus=True)
        self.assertIn("top", result)
        self.assertIn("bottom", result)

    def test_ends_visible_top_only(self):
        items = [urwid.Text(str(i)) for i in range(20)]
        lbox = urwid.ListBox(urwid.SimpleListWalker(items))
        result = lbox.ends_visible((4, 5), focus=True)
        self.assertIn("top", result)
        self.assertNotIn("bottom", result)

    def test_ends_visible_bottom_only(self):
        items = [urwid.Text(str(i)) for i in range(20)]
        lbox = urwid.ListBox(urwid.SimpleListWalker(items))
        lbox.set_focus(19)
        lbox.render((4, 5), focus=True)
        result = lbox.ends_visible((4, 5), focus=True)
        self.assertIn("bottom", result)
        self.assertNotIn("top", result)

    def test_ends_visible_neither(self):
        items = [urwid.Text(str(i)) for i in range(20)]
        lbox = urwid.ListBox(urwid.SimpleListWalker(items))
        lbox.set_focus(10)
        lbox.render((4, 5), focus=True)
        result = lbox.ends_visible((4, 5), focus=True)
        self.assertEqual([], result)

    def test_ends_visible_trim_bottom_nonzero(self):
        lbox = urwid.ListBox(urwid.SimpleListWalker([urwid.Text("1\n2\n3\n4\n5\n6")]))
        result = lbox.ends_visible((4, 5), focus=True)
        self.assertNotIn("bottom", result)

    def test_ends_visible_trim_top_nonzero(self):
        lbox = urwid.ListBox(urwid.SimpleListWalker([urwid.Text("1\n2\n3\n4\n5\n6")]))
        lbox.shift_focus((4, 10), -1)
        result = lbox.ends_visible((4, 5), focus=True)
        self.assertNotIn("top", result)


class ListBoxIterTest(unittest.TestCase):
    def test_iter_with_positions(self):
        items = [urwid.Text(str(i)) for i in range(5)]
        lbox = urwid.ListBox(urwid.SimpleListWalker(items))
        self.assertEqual(list(range(5)), list(iter(lbox)))

    def test_reversed_with_positions(self):
        items = [urwid.Text(str(i)) for i in range(5)]
        lbox = urwid.ListBox(urwid.SimpleListWalker(items))
        self.assertEqual(list(range(4, -1, -1)), list(reversed(lbox)))

    def test_iter_without_positions(self):
        walker, root = make_tree_walker(4, focus_key=1)
        lbox = urwid.ListBox(walker)
        expected = [
            root.get_child_node(1),
            root.get_child_node(2),
            root.get_child_node(3),
            root.get_child_node(0),
            root,
        ]
        self.assertEqual(expected, list(iter(lbox)))

    def test_reversed_without_positions(self):
        walker, root = make_tree_walker(4, focus_key=1)
        lbox = urwid.ListBox(walker)
        expected = [
            root.get_child_node(0),
            root,
            root.get_child_node(1),
            root.get_child_node(2),
            root.get_child_node(3),
        ]
        self.assertEqual(expected, list(reversed(lbox)))

    def test_iter_empty_without_positions(self):
        lbox = urwid.ListBox(EmptyNoPositionsWalker())
        self.assertEqual([], list(iter(lbox)))
        self.assertEqual([], list(reversed(lbox)))

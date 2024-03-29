from __future__ import annotations

import unittest

import urwid
from urwid.util import get_encoding
from urwid.widget import bar_graph


class BarGraphTest(unittest.TestCase):
    def bgtest(self, desc, data, top, widths, maxrow, exp):
        rval = bar_graph.calculate_bargraph_display(data, top, widths, maxrow)
        assert rval == exp, f"{desc} expected {exp!r}, got {rval!r}"

    def test1(self):
        self.bgtest("simplest", [[0]], 5, [1], 1, [(1, [(0, 1)])]),
        self.bgtest(
            "simpler",
            [[0], [0]],
            5,
            [1, 2],
            5,
            [(5, [(0, 3)])],
        )
        self.bgtest(
            "simple",
            [[5]],
            5,
            [1],
            1,
            [(1, [(1, 1)])],
        )
        self.bgtest(
            "2col-1",
            [[2], [0]],
            5,
            [1, 2],
            5,
            [(3, [(0, 3)]), (2, [(1, 1), (0, 2)])],
        )
        self.bgtest(
            "2col-2",
            [[0], [2]],
            5,
            [1, 2],
            5,
            [(3, [(0, 3)]), (2, [(0, 1), (1, 2)])],
        )
        self.bgtest(
            "2col-3",
            [[2], [3]],
            5,
            [1, 2],
            5,
            [(2, [(0, 3)]), (1, [(0, 1), (1, 2)]), (2, [(1, 3)])],
        )
        self.bgtest(
            "3col-1",
            [[5], [3], [0]],
            5,
            [2, 1, 1],
            5,
            [(2, [(1, 2), (0, 2)]), (3, [(1, 3), (0, 1)])],
        )
        self.bgtest(
            "3col-2",
            [[4], [4], [4]],
            5,
            [2, 1, 1],
            5,
            [(1, [(0, 4)]), (4, [(1, 4)])],
        )
        self.bgtest(
            "3col-3",
            [[1], [2], [3]],
            5,
            [2, 1, 1],
            5,
            [(2, [(0, 4)]), (1, [(0, 3), (1, 1)]), (1, [(0, 2), (1, 2)]), (1, [(1, 4)])],
        )
        self.bgtest(
            "3col-4",
            [[4], [2], [4]],
            5,
            [1, 2, 1],
            5,
            [(1, [(0, 4)]), (2, [(1, 1), (0, 2), (1, 1)]), (2, [(1, 4)])],
        )

    def test2(self):
        self.bgtest(
            "simple1a",
            [[2, 0], [2, 1]],
            2,
            [1, 1],
            2,
            [(1, [(1, 2)]), (1, [(1, 1), (2, 1)])],
        )
        self.bgtest(
            "simple1b",
            [[2, 1], [2, 0]],
            2,
            [1, 1],
            2,
            [(1, [(1, 2)]), (1, [(2, 1), (1, 1)])],
        )
        self.bgtest("cross1a", [[2, 2], [1, 2]], 2, [1, 1], 2, [(2, [(2, 2)])])
        self.bgtest("cross1b", [[1, 2], [2, 2]], 2, [1, 1], 2, [(2, [(2, 2)])])
        self.bgtest(
            "mix1a",
            [[3, 2, 1], [2, 2, 2], [1, 2, 3]],
            3,
            [1, 1, 1],
            3,
            [(1, [(1, 1), (0, 1), (3, 1)]), (1, [(2, 1), (3, 2)]), (1, [(3, 3)])],
        )
        self.bgtest(
            "mix1b",
            [[1, 2, 3], [2, 2, 2], [3, 2, 1]],
            3,
            [1, 1, 1],
            3,
            [(1, [(3, 1), (0, 1), (1, 1)]), (1, [(3, 2), (2, 1)]), (1, [(3, 3)])],
        )


class SmoothBarGraphTest(unittest.TestCase):
    def setUp(self) -> None:
        self.old_encoding = get_encoding()
        urwid.set_encoding("utf-8")

    def tearDown(self) -> None:
        urwid.set_encoding(self.old_encoding)

    def sbgtest(self, desc, data, top, exp):
        g = urwid.BarGraph(["black", "red", "blue"], None, {(1, 0): "red/black", (2, 1): "blue/red"})
        g.set_data(data, top)
        rval = g.calculate_display((5, 3))
        assert rval == exp, f"{desc} expected {exp!r}, got {rval!r}"

    def test1(self):
        self.sbgtest(
            "simple",
            [[3]],
            5,
            [(1, [(0, 5)]), (1, [((1, 0, 6), 5)]), (1, [(1, 5)])],
        )
        self.sbgtest(
            "boring",
            [[4, 2]],
            6,
            [(1, [(0, 5)]), (1, [(1, 5)]), (1, [(2, 5)])],
        )
        self.sbgtest(
            "two",
            [[4], [2]],
            6,
            [(1, [(0, 5)]), (1, [(1, 3), (0, 2)]), (1, [(1, 5)])],
        )
        self.sbgtest(
            "twos",
            [[3], [4]],
            6,
            [(1, [(0, 5)]), (1, [((1, 0, 4), 3), (1, 2)]), (1, [(1, 5)])],
        )
        self.sbgtest(
            "twof",
            [[4], [3]],
            6,
            [(1, [(0, 5)]), (1, [(1, 3), ((1, 0, 4), 2)]), (1, [(1, 5)])],
        )

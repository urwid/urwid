"""Tests for :class:`urwid.ProgressBar`."""

from __future__ import annotations

import math
import unittest

import urwid

EMPTY = [("normal", 10)]
FULL = [("complete", 10)]


class ProgressBarOutOfRangeTest(unittest.TestCase):
    """Check that a progress bar renders and labels values outside ``[0, done]`` without raising."""

    def assertBar(self, current: float, done: float, attrs: list[tuple[str, int]], text: str) -> None:
        """Assert the label and the attribute runs of a 10-column bar, with and without smoothing."""
        for satt in (None, "smooth"):
            with self.subTest(satt=satt):
                pb = urwid.ProgressBar("normal", "complete", current, done, satt)  # type: ignore[arg-type]
                self.assertEqual(text, pb.get_text())
                (row,) = pb.render((10,)).content()
                self.assertEqual(attrs, [(attr, len(seg)) for attr, _cs, seg in row])

    def test_in_range(self) -> None:
        """Draw half of the bar complete for half of `done`."""
        self.assertBar(50, 100, [("complete", 5), ("normal", 5)], "50 %")

    def test_done_zero(self) -> None:
        """Draw an empty bar for a zero `done`."""
        self.assertBar(50, 0, EMPTY, "0 %")

    def test_done_negative(self) -> None:
        """Draw an empty bar for a negative `done`."""
        self.assertBar(50, -100, EMPTY, "0 %")

    def test_nan(self) -> None:
        """Draw an empty bar when `current` or `done` is NaN."""
        self.assertBar(math.nan, 100, EMPTY, "0 %")
        self.assertBar(50, math.nan, EMPTY, "0 %")

    def test_infinite(self) -> None:
        """Clamp an infinite `current` like any out-of-range value; draw an empty bar for an infinite `done`."""
        self.assertBar(math.inf, 100, FULL, "100 %")
        self.assertBar(-math.inf, 100, EMPTY, "0 %")
        self.assertBar(50, math.inf, EMPTY, "0 %")

    def test_negative_current(self) -> None:
        """Draw an empty bar for a negative `current`."""
        self.assertBar(-50, 100, EMPTY, "0 %")

    def test_current_above_done(self) -> None:
        """Draw a full bar when `current` exceeds `done`."""
        self.assertBar(150, 100, FULL, "100 %")

    def test_current_too_large_for_float(self) -> None:
        """Draw a full or empty bar when ``current / done`` does not fit in a float."""
        self.assertBar(10**400, 1, FULL, "100 %")
        self.assertBar(-(10**400), 1, EMPTY, "0 %")
        self.assertBar(1.0, 10**400, EMPTY, "0 %")
        self.assertBar(math.inf, 10**400, FULL, "100 %")

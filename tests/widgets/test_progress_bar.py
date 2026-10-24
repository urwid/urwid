"""Tests for :class:`urwid.ProgressBar`."""

from __future__ import annotations

import math
import unittest

import urwid
from urwid.util import set_temporary_encoding

EMPTY = [("normal", 10)]
FULL = [("complete", 10)]


class LabelProgressBar(urwid.ProgressBar):
    label = ""

    def get_text(self) -> str:
        return self.label


class ProgressBarUnicodeLabelTest(unittest.TestCase):
    def test_labels_are_preserved_without_smoothing(self) -> None:
        with set_temporary_encoding("utf-8"):
            for label in ("下載", "café", "e\u0301", "👩\u200d💻"):
                for width in (0, 1, 4, 10):
                    expected = urwid.Text(label, align="center", wrap="clip").render((width,))
                    for current in (0, 25, 50, 75, 100):
                        with self.subTest(label=label, width=width, current=current):
                            bar = LabelProgressBar("normal", "complete", current)
                            bar.label = label
                            rendered = bar.render((width,))
                            self.assertEqual(expected.decoded_text, rendered.decoded_text)
                            self.assertEqual(expected.text, rendered.text)
                            if current in (0, 100):
                                expected_attr = "normal" if current == 0 else "complete"
                                (row,) = rendered.content()
                                self.assertTrue(all(attr == expected_attr for attr, _charset, _text in row))

    def test_wide_character_completion_uses_screen_columns(self) -> None:
        with set_temporary_encoding("utf-8"):
            bar = LabelProgressBar("normal", "complete", 50)
            bar.label = "下載"

            (row,) = bar.render((4,)).content()

            self.assertEqual([("complete", None, "下".encode()), ("normal", None, "載".encode())], row)

    def test_completion_keeps_combining_characters_together(self) -> None:
        with set_temporary_encoding("utf-8"):
            bar = LabelProgressBar("normal", "complete", 2, 3)
            bar.label = "e\u0301"

            (row,) = bar.render((3,)).content()

            self.assertEqual([("complete", None, " e\u0301".encode()), ("normal", None, b" ")], row)

    def test_smoothing_follows_multibyte_label(self) -> None:
        with set_temporary_encoding("utf-8"):
            bar = LabelProgressBar("normal", "complete", 70, satt="smooth")
            bar.label = "é"

            rendered = bar.render((5,))

            self.assertEqual(("  é▌ ",), rendered.decoded_text)
            self.assertEqual(
                [("complete", None, "  é".encode()), ("smooth", None, "▌".encode()), ("normal", None, b" ")],
                list(rendered.content())[0],
            )

    def test_ascii_label_preserves_dec_character_set(self) -> None:
        with set_temporary_encoding("ascii"):
            bar = LabelProgressBar("normal", "complete", 70, satt="smooth")
            bar.label = "─"

            self.assertEqual(
                [("complete", None, b"  "), ("complete", "0", b"q"), ("normal", None, b"  ")],
                list(bar.render((5,)).content())[0],
            )

    def test_smoothing_is_disabled_for_ascii_encoding(self) -> None:
        with set_temporary_encoding("ascii"):
            bar = LabelProgressBar("normal", "complete", 12.5, satt="smooth")

            self.assertEqual(("    ",), bar.render((4,)).decoded_text)

    def test_smoothing_preserves_explicit_dec_character_set(self) -> None:
        with set_temporary_encoding("utf-8"):
            bar = LabelProgressBar("normal", "complete", 70, satt="smooth")
            bar.label = "\x0eq\x0f"

            self.assertEqual(
                [
                    ("complete", None, b"  "),
                    ("complete", "0", b"q"),
                    ("smooth", None, "▌".encode()),
                    ("normal", None, b" "),
                ],
                list(bar.render((5,)).content())[0],
            )

    def test_smoothing_preserves_a_straddled_wide_character(self) -> None:
        with set_temporary_encoding("utf-8"):
            bar = LabelProgressBar("normal", "complete", 37.5, satt="smooth")
            bar.label = "下載"

            rendered = bar.render((4,))

            self.assertEqual(("下載",), rendered.decoded_text)
            self.assertEqual([("normal", None, "下載".encode())], list(rendered.content())[0])

    def test_single_byte_label_uses_target_encoding(self) -> None:
        with set_temporary_encoding("latin-1"):
            bar = LabelProgressBar("normal", "complete", 75)
            bar.label = "café"

            self.assertEqual(
                [("complete", None, b"caf"), ("normal", None, b"\xe9")], list(bar.render((4,)).content())[0]
            )


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


class ProgressBarFiniteScaleTest(unittest.TestCase):
    def test_large_finite_values_keep_their_fraction(self) -> None:
        for current, done, expected in ((1e307, 1e308, "10 %"), (1e308, 1.5e308, "66 %")):
            with self.subTest(current=current, done=done):
                bar = urwid.ProgressBar("normal", "complete", current, done)
                self.assertEqual(bar.get_text(), expected)
                self.assertLess(sum(len(seg) for attr, _charset, seg in list(bar.render((10,)).content())[0] if attr == "complete"), 10)

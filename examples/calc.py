#!/usr/bin/env python3
#
# Urwid example: a calculator with a normal and a programmer mode
#    Copyright (C) 2026 Urwid developers
#
#    This library is free software; you can redistribute it and/or
#    modify it under the terms of the GNU Lesser General Public
#    License as published by the Free Software Foundation; either
#    version 2.1 of the License, or (at your option) any later version.
#
#    This library is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#    Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public
#    License along with this library; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#
# Urwid web site: https://urwid.org/
#
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "urwid>=5.1",
# ]
# ///
"""Example: a calculator with a Normal and a Programmer tab, showing its numbers in big digits.

The module has two parts, so that the user interface can be read on its own:

- The calculator logic: :class:`Calculator` and its two subclasses, plain Python with no urwid in them.
- The user interface: urwid widgets that show a calculator and send it the keys and the button presses.

The program reads only the keyboard and the mouse, and writes only to the terminal.
It exits on :kbd:`F8` or the :guilabel:`Exit` button, with status 0.
"""

from __future__ import annotations

import abc
import dataclasses
import decimal
import operator
import string
import sys
import typing

import urwid
from urwid.command_map import Command

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Hashable, Sequence

    from urwid.widget.popup import PopUpParametersModel

# Calculator logic: plain Python, no urwid.

#: the most significant digits a decimal number has, typed or calculated
MAX_DIGITS: typing.Final = 16
#: the programmer calculator's numbers are limited to this many bits, plus a sign
WORD_BITS: typing.Final = 32
#: the format specification that shows an integer in each base the programmer calculator offers
BASE_FORMATS: typing.Final[dict[int, str]] = {2: "b", 8: "o", 10: "d", 16: "X"}

_N = typing.TypeVar("_N", decimal.Decimal, int)


class Calculator(abc.ABC, typing.Generic[_N]):
    """Pocket calculator state: the number being typed, the result so far, and the operator waiting for its operand.

    Operators are applied in the order they are entered, as on a pocket calculator: ``2 + 3 * 4 =`` gives 20.
    A failed operation, such as a division by zero, shows an error.
    The error stays until the next digit, decimal point, backspace or :meth:`clear`.
    Subclasses decide what a number is: which digits it has, how it is read and shown, and how operators combine two.
    """

    def __init__(self) -> None:
        """Start cleared, showing 0."""
        self._entry = ""  # the number being typed, with a leading "-" when negated
        self._value: _N | None = None  # the result so far; never None while _operator is set
        self._operator: str | None = None  # applied to _value and the next operand
        self._error: str | None = None  # why the last operation failed

    @property
    @abc.abstractmethod
    def digits(self) -> str:
        """The digits a number is typed with, uppercase."""

    @abc.abstractmethod
    def accepts(self, entry: str) -> bool:
        """Return whether *entry* is a number short enough to be typed."""

    @abc.abstractmethod
    def parse(self, text: str) -> _N:
        """Return the number *text* shows."""

    @abc.abstractmethod
    def to_text(self, value: _N) -> str:
        """Return *value* as the display shows it."""

    @abc.abstractmethod
    def convert(self, number: decimal.Decimal | int) -> _N:
        """Return *number*, which another calculator showed, as a number of this calculator.

        :raises ArithmeticError: *number* does not fit; the message says why.
        """

    @abc.abstractmethod
    def calculate(self, left: _N, operator_key: str, right: _N) -> _N:
        """Return *left* combined with *right* by the operator named by *operator_key*.

        :raises ArithmeticError: the result is not defined or does not fit; the message says why.
        """

    @property
    def error(self) -> str | None:
        """Why the last operation failed, or ``None`` after a successful one."""
        return self._error

    @property
    def number(self) -> _N | None:
        """The number shown, or ``None`` while an error is shown."""
        if self._error is not None:
            return None
        if self._entry:
            return self.parse(self._entry)
        return self._value if self._value is not None else self.parse("0")

    @property
    def display(self) -> str:
        """The number to show: the one being typed, else the result so far, else 0."""
        if self._entry:
            return self._entry
        if self._value is not None:
            return self.to_text(self._value)
        return "0"

    @property
    def expression(self) -> str:
        """The result so far and the operator waiting for its operand, such as ``12 +``, or the error."""
        if self._error is not None:
            return self._error
        if self._operator is None or self._value is None:
            return ""
        return f"{self.to_text(self._value)} {self._operator}"

    def clear(self) -> None:
        """Forget everything, including an error."""
        self._entry = ""
        self._value = None
        self._operator = None
        self._error = None

    def load(self, number: decimal.Decimal | int | None) -> None:
        """Forget everything and show *number* as the result, converted by :meth:`convert`.

        ``None``, which :attr:`number` gives while an error is shown, leaves the calculator cleared.
        """
        self.clear()
        if number is None:
            return
        try:
            self._value = self.convert(number)
        except ArithmeticError as exc:
            self._error = str(exc)

    def enter_digit(self, digit: str) -> None:
        """Append *digit* to the number being typed.

        A digit that makes the number too long is ignored.

        :raises ValueError: *digit* is not one of :attr:`digits`.
        """
        if digit not in self.digits:
            raise ValueError(f"{digit!r} is not a digit of this calculator: {self.digits}")
        if self._error is not None:
            self.clear()
        sign = "-" if self._entry.startswith("-") else ""
        typed = self._entry.removeprefix("-")
        self._type(sign + ("" if typed == "0" else typed) + digit)

    def _type(self, entry: str) -> None:
        """Make *entry* the number being typed, unless it is too long."""
        if self.accepts(entry):
            self._entry = entry

    def backspace(self) -> None:
        """Remove the last typed character, or the error."""
        if self._error is not None:
            self.clear()
        self._entry = self._entry[:-1].removesuffix("-")

    def negate(self) -> None:
        """Change the sign of the number being typed, or of the result when nothing is typed and no operator waits."""
        if self._error is not None:
            return
        if self._entry:
            self._entry = self._entry.removeprefix("-") if self._entry.startswith("-") else f"-{self._entry}"
        elif self._value is not None and self._operator is None:
            self._value = -self._value

    def enter_operator(self, operator_key: str) -> None:
        """Apply the waiting operator to the typed number, then wait for an operand of *operator_key*.

        Operators entered one after another replace each other, so the last one is used.
        """
        if self._error is not None:
            return
        if self._entry:
            self._apply(self.parse(self._entry))
        elif self._value is None:
            self._value = self.parse("0")
        if self._error is None:
            self._operator = operator_key

    def equals(self) -> None:
        """Apply the waiting operator.

        With nothing typed, the result so far is the operand, so ``3 * =`` gives 9.
        """
        if self._error is not None:
            return
        if self._entry:
            self._apply(self.parse(self._entry))
        elif self._operator is not None and self._value is not None:
            self._apply(self._value)
        self._operator = None

    def _apply(self, operand: _N) -> None:
        """Combine the result so far with *operand* by the waiting operator, or start with *operand*."""
        self._entry = ""
        if self._operator is None or self._value is None:
            self._value = operand
            return
        try:
            self._value = self.calculate(self._value, self._operator, operand)
        except ArithmeticError as exc:
            self._value = None
            self._operator = None
            self._error = str(exc)


class DecimalCalculator(Calculator[decimal.Decimal]):
    """Calculator on decimal fractions, rounded to :data:`MAX_DIGITS` significant digits.

    Decimal arithmetic keeps decimal fractions exact: ``0.1 + 0.2 =`` gives 0.3, where binary floats give
    0.30000000000000004.

    >>> calculator = DecimalCalculator()
    >>> calculator.enter_point()
    >>> calculator.enter_digit("1")
    >>> calculator.enter_operator("+")
    >>> calculator.enter_point()
    >>> calculator.enter_digit("2")
    >>> calculator.equals()
    >>> calculator.display
    '0.3'
    """

    _context: typing.ClassVar[decimal.Context] = decimal.Context(prec=MAX_DIGITS)
    # E notation keeps 13 significant digits, so a sign, the point and an exponent of up to 7 digits fit one display row
    _scientific_context: typing.ClassVar[decimal.Context] = decimal.Context(prec=MAX_DIGITS - 3)
    _operations: typing.ClassVar[
        dict[str, Callable[[decimal.Context, decimal.Decimal, decimal.Decimal], decimal.Decimal]]
    ] = {
        "+": decimal.Context.add,
        "-": decimal.Context.subtract,
        "*": decimal.Context.multiply,
        "/": decimal.Context.divide,
    }

    @property
    def digits(self) -> str:
        """The decimal digits."""
        return string.digits

    def accepts(self, entry: str) -> bool:
        """Return whether *entry* has at most :data:`MAX_DIGITS` digits."""
        return sum(character.isdigit() for character in entry) <= MAX_DIGITS

    def enter_point(self) -> None:
        """Start the fraction of the number being typed, once."""
        if self._error is not None:
            self.clear()
        if "." not in self._entry:
            self._type(f"{self._entry or '0'}.")

    def parse(self, text: str) -> decimal.Decimal:
        """Return the number *text* shows, which may end in a point, such as ``5.``."""
        return decimal.Decimal(text)

    def to_text(self, value: decimal.Decimal) -> str:
        """Return *value* as text, in E notation when it has more than :data:`MAX_DIGITS` digits."""
        value = value.normalize(self._context) if value else decimal.Decimal(0)  # no "-0" or "0E+2"
        text = f"{value:f}"
        if len(text.removeprefix("-").removeprefix("0.").replace(".", "")) <= MAX_DIGITS:
            return text
        return f"{value.normalize(self._scientific_context):E}"

    def convert(self, number: decimal.Decimal | int) -> decimal.Decimal:
        """Return *number* as a decimal number."""
        return decimal.Decimal(number)

    def calculate(self, left: decimal.Decimal, operator_key: str, right: decimal.Decimal) -> decimal.Decimal:
        """Return *left* combined with *right*, rounded to :data:`MAX_DIGITS` significant digits.

        :raises ZeroDivisionError: *operator_key* is ``/`` and *right* is zero.
        :raises OverflowError: the result is larger than the decimal context allows.
        """
        if operator_key == "/" and not right:
            raise ZeroDivisionError("Division by zero")
        try:
            return self._operations[operator_key](self._context, left, right)
        except decimal.Overflow as exc:
            raise OverflowError("The result is too large") from exc


class IntegerCalculator(Calculator[int]):
    """Calculator on integers of :data:`WORD_BITS` bits and a sign, shown in base 2, 8, 10 or 16.

    Division drops the remainder, rounding towards zero.

    >>> calculator = IntegerCalculator()
    >>> calculator.base = 16
    >>> for digit in "FF":
    ...     calculator.enter_digit(digit)
    >>> calculator.base = 2
    >>> calculator.display
    '11111111'
    """

    _operations: typing.ClassVar[dict[str, Callable[[int, int], int]]] = {
        "+": operator.add,
        "-": operator.sub,
        "*": operator.mul,
    }

    def __init__(self) -> None:
        """Start cleared, in base 10."""
        super().__init__()
        self._base = 10

    @property
    def base(self) -> int:
        """The base numbers are typed and shown in, one of :data:`BASE_FORMATS`.

        Changing it converts the number being typed.
        """
        return self._base

    @base.setter
    def base(self, base: int) -> None:
        if base not in BASE_FORMATS:
            raise ValueError(f"base {base} is not one of {tuple(BASE_FORMATS)}")
        value = self.parse(self._entry) if self._entry else None
        self._base = base
        if value is not None:
            self._entry = self.to_text(value)

    @property
    def digits(self) -> str:
        """The digits of :attr:`base`: 0-1, 0-7, 0-9 or 0-F."""
        return (string.digits + string.ascii_uppercase)[: self._base]

    def accepts(self, entry: str) -> bool:
        """Return whether *entry* fits in :data:`WORD_BITS` bits."""
        return self.parse(entry).bit_length() <= WORD_BITS

    def parse(self, text: str) -> int:
        """Return the number *text* shows in :attr:`base`."""
        return int(text, self._base)

    def to_text(self, value: int) -> str:
        """Return *value* in :attr:`base`, with a leading ``-`` when negative."""
        return format(value, BASE_FORMATS[self._base])

    def convert(self, number: decimal.Decimal | int) -> int:
        """Return *number* without its fraction, rounding towards zero.

        :raises OverflowError: *number* does not fit in :data:`WORD_BITS` bits.
        """
        # compared before int(), which would build every digit of a decimal with a large exponent
        if abs(number) >= 2**WORD_BITS:
            raise OverflowError(f"The number does not fit in {WORD_BITS} bits")
        return int(number)

    def calculate(self, left: int, operator_key: str, right: int) -> int:
        """Return *left* combined with *right*.

        :raises ZeroDivisionError: *operator_key* is ``/`` and *right* is zero.
        :raises OverflowError: the result does not fit in :data:`WORD_BITS` bits.
        """
        if operator_key == "/":
            if not right:
                raise ZeroDivisionError("Division by zero")
            quotient = abs(left) // abs(right)
            result = -quotient if (left < 0) != (right < 0) else quotient
        else:
            result = self._operations[operator_key](left, right)
        if result.bit_length() > WORD_BITS:
            raise OverflowError(f"The result does not fit in {WORD_BITS} bits")
        return result


# User interface: urwid widgets around the calculators.

FONT: typing.Final = urwid.Thin3x3Font()
#: big digits in one row of the display: 24 digits of 3 columns fit an 80-column terminal
DIGITS_PER_ROW: typing.Final = 24
#: rows of big digits in the display: two hold the 32 digits of a number in base 2
DISPLAY_ROWS: typing.Final = 2
#: columns of a button pad: 4 buttons of 9 columns and the gaps between them
PAD_WIDTH: typing.Final = 39
#: keys of the operators, the same on the main keyboard and on the numeric keypad
OPERATOR_KEYS: typing.Final = frozenset("+-*/")


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class Theme:
    """The colors of a theme, named after their role in the Monokai color scheme."""

    background: str
    panel: str  # buttons, bars and dialogs
    text: str
    comment: str
    pink: str
    orange: str
    yellow: str
    green: str
    blue: str
    purple: str


#: the themes, from the Monokai color scheme and a light variant of it
THEMES: typing.Final = {
    "Monokai dark": Theme(
        background="#272822",
        panel="#3e3d32",
        text="#f8f8f2",
        comment="#75715e",
        pink="#f92672",
        orange="#fd971f",
        yellow="#e6db74",
        green="#a6e22e",
        blue="#66d9ef",
        purple="#ae81ff",
    ),
    "Monokai bright": Theme(
        background="#fafafa",
        panel="#e6e6dc",
        text="#272822",
        comment="#8a8670",
        pink="#e0115f",
        orange="#d75f00",
        yellow="#998f00",
        green="#5f8700",
        blue="#0087af",
        purple="#7a4ec4",
    ),
}

#: palette entries: name, foreground and background field of :class:`Theme`, then the 16-color foreground, background
#: and the monochrome setting, which are the same for every theme
ENTRIES: typing.Final = (
    ("body", "text", "background", "light gray", "black", None),
    ("header", "text", "panel", "white", "dark blue", None),
    ("footer", "comment", "panel", "light gray", "dark blue", None),
    ("key", "orange", "panel", "yellow", "dark blue", "bold"),
    ("expression", "comment", "background", "dark gray", "black", None),
    ("display", "purple", "background", "light magenta", "black", None),
    ("error", "pink", "background", "light red", "black", None),
    ("button", "text", "panel", "black", "light gray", None),
    ("button focus", "background", "orange", "white", "brown", "standout"),
    ("operator", "pink", "panel", "dark red", "light gray", None),
    ("operator focus", "background", "pink", "white", "dark red", "standout"),
    ("control", "blue", "panel", "dark blue", "light gray", None),
    ("control focus", "background", "blue", "white", "dark blue", "standout"),
    ("tab", "comment", "panel", "black", "light gray", None),
    ("tab selected", "green", "background", "light green", "black", "bold"),
    ("tab cursor", "background", "green", "black", "light green", "standout"),
    ("disabled", "comment", "panel", "dark gray", "light gray", None),
    ("dialog", "text", "panel", "black", "light gray", None),
)

HELP: typing.Final = """\
Type on the keyboard or on the numeric keypad, or press the buttons with the mouse or with Space.

  0-9, A-F     digits; A-F in base 16
  + - * /      operators, applied from left to right
  Enter, =     result
  . or ,       decimal point, on the Normal tab
  Backspace    remove the last digit
  Esc, Delete  clear
  F9           change the sign
  Alt+Left/Right  switch between the tabs
  F1 help, F2 theme, F8 exit

The Programmer tab calculates with 32-bit integers and a sign."""


def palette(theme: str) -> list[tuple[Hashable, str, str, str | None, str, str]]:
    """Return the palette of *theme*.

    Terminals with 256 colors or more get the colors of the theme, others get the same basic colors for every theme.
    """
    colors = THEMES[theme]
    return [
        (name, foreground, background, mono, getattr(colors, foreground_role), getattr(colors, background_role))
        for name, foreground_role, background_role, foreground, background, mono in ENTRIES
    ]


class Display(urwid.WidgetWrap[urwid.LineBox[urwid.AttrMap[urwid.Pile]]]):
    """The expression line over the calculator's number in big digits, the last digits in the last row."""

    def __init__(self) -> None:
        """Build an empty display with :data:`DISPLAY_ROWS` rows of big digits."""
        self._expression = urwid.Text("", align=urwid.RIGHT)
        self._rows = [urwid.BigText("", FONT) for _ in range(DISPLAY_ROWS)]
        pile = urwid.Pile(
            [
                urwid.AttrMap(self._expression, "expression"),
                *(urwid.Padding(big_text, urwid.RIGHT, urwid.WHSettings.CLIP) for big_text in self._rows),
            ]
        )
        super().__init__(urwid.LineBox(urwid.AttrMap(pile, "display")))

    def show(self, calculator: Calculator[typing.Any]) -> None:
        """Show the state of *calculator*."""
        self._expression.set_text(calculator.expression)
        if calculator.error is not None:
            lines: list[str | tuple[Hashable, str]] = [("error", "E")]
        else:
            text = calculator.display
            lines = [text[max(end - DIGITS_PER_ROW, 0) : end] for end in range(len(text), 0, -DIGITS_PER_ROW)]
            lines.reverse()
        lines = [*([""] * (len(self._rows) - len(lines))), *lines]
        for big_text, line in zip(self._rows, lines, strict=True):
            big_text.set_text(line)


class CalculatorPane(urwid.WidgetWrap[urwid.Filler[urwid.Pile]]):
    """The buttons of one calculator, which show its state on a display shared with the other panes.

    A key is offered to the calculator before the focused widget, so :kbd:`Enter` gives the result
    wherever the focus is in the pane, and :kbd:`Space` presses the focused button.
    A button press goes through :meth:`press` as the key it stands for.
    """

    def __init__(self, calculator: Calculator[typing.Any], display: Display) -> None:
        """Send the presses to *calculator* and show its state on *display*.

        Subclasses add the buttons with :meth:`add_pad`.
        """
        self.calculator = calculator
        self.display = display
        self.pile = urwid.Pile([])
        super().__init__(urwid.Filler(self.pile, valign=urwid.TOP))

    def button(self, label: str, key: str, attr: str = "button") -> urwid.AttrMap[urwid.Widget]:
        """Return a button labelled *label* that presses *key*, drawn in *attr* and in ``"<attr> focus"``."""
        button = urwid.Button(label, on_press=self._on_button, user_data=key, align=urwid.CENTER)
        cell: urwid.AttrMap[urwid.Widget] = urwid.AttrMap(button, attr, f"{attr} focus")
        return cell

    def add_pad(
        self,
        rows: Sequence[Sequence[urwid.Widget | tuple[typing.Literal[urwid.WHSettings.WEIGHT], int, urwid.Widget]]],
    ) -> None:
        """Add *rows* of buttons as a grid of :data:`PAD_WIDTH` columns, and focus it.

        A button with a weight of 2 takes the place of two.
        """
        pad = urwid.Pile([urwid.Columns(row, dividechars=1) for row in rows])
        self.pile.contents.append((urwid.Padding(pad, urwid.CENTER, PAD_WIDTH), self.pile.options()))
        self.pile.focus_position = len(self.pile.contents) - 1

    def press(self, key: str) -> bool:
        """Send *key* to the calculator and show the result.

        :returns: whether the calculator takes *key*.
        """
        calculator = self.calculator
        if len(key) == 1 and key.upper() in calculator.digits:
            calculator.enter_digit(key.upper())
        elif key in OPERATOR_KEYS:
            calculator.enter_operator(key)
        elif key in {"enter", "="}:
            calculator.equals()
        elif key == "backspace":
            calculator.backspace()
        elif key in {"esc", "delete"}:
            calculator.clear()
        elif key == "f9":
            calculator.negate()
        elif key in {".", ","} and isinstance(calculator, DecimalCalculator):
            calculator.enter_point()
        else:
            return False
        self.display.show(calculator)
        return True

    def keypress(self, size: tuple[()] | tuple[int] | tuple[int, int], key: str) -> str | None:
        """Give *key* to the calculator, and the keys it does not take to the focused widget."""
        if self.press(key):
            return None
        return super().keypress(size, key)

    def _on_button(self, _button: urwid.Button, key: str) -> None:
        """Press the key of a clicked button."""
        self.press(key)


class NormalPane(CalculatorPane):
    """A decimal calculator with the buttons laid out as on a numeric keypad."""

    def __init__(self, display: Display) -> None:
        """Build the calculator and its button pad, showing it on *display*."""
        super().__init__(DecimalCalculator(), display)
        self.add_pad(
            [
                [
                    self.button("Clear", "esc", "control"),
                    self.button("←", "backspace", "control"),
                    self.button("±", "f9", "control"),
                    self.button("/", "/", "operator"),
                ],
                *(
                    [*(self.button(digit, digit) for digit in digits), self.button(key, key, "operator")]
                    for digits, key in (("789", "*"), ("456", "-"), ("123", "+"))
                ),
                [(urwid.WEIGHT, 2, self.button("0", "0")), self.button(".", "."), self.button("=", "enter", "control")],
            ]
        )


class ProgrammerPane(CalculatorPane):
    """An integer calculator with a radio button per base over a hexadecimal keypad.

    The keypad keeps every digit in its place: the digits the selected base does not have are greyed out,
    and the focus skips them.
    """

    def __init__(self, display: Display) -> None:
        """Build the calculator, the base selection and the keypad, showing it on *display*."""
        self._integer = IntegerCalculator()
        super().__init__(self._integer, display)
        group: list[urwid.RadioButton] = []
        bases = urwid.GridFlow(
            [
                urwid.Text("Base:"),
                *(
                    urwid.AttrMap(
                        urwid.RadioButton(
                            group,
                            str(base),
                            state=base == self._integer.base,
                            on_state_change=self._on_base,
                            user_data=base,
                        ),
                        None,
                        "button focus",
                    )
                    for base in BASE_FORMATS
                ),
            ],
            cell_width=7,
            h_sep=1,
            v_sep=0,
            align=urwid.CENTER,
        )
        self.pile.contents.append((bases, self.pile.options()))
        self._digit_cells: dict[str, tuple[urwid.AttrMap[urwid.Widget], urwid.Widget]] = {}
        for digit in "0123456789ABCDEF":
            cell = self.button(digit, digit)
            self._digit_cells[digit] = (cell, cell.original_widget)
        self._show_digit_buttons()
        cells = {digit: cell for digit, (cell, _button) in self._digit_cells.items()}
        self.add_pad(
            [
                [cells["D"], cells["E"], cells["F"], self.button("Clear", "esc", "control")],
                [cells["A"], cells["B"], cells["C"], self.button("←", "backspace", "control")],
                *(
                    [*(cells[digit] for digit in digits), self.button(key, key, "operator")]
                    for digits, key in (("789", "/"), ("456", "*"), ("123", "-"))
                ),
                [
                    self.button("±", "f9", "control"),
                    cells["0"],
                    self.button("=", "enter", "control"),
                    self.button("+", "+", "operator"),
                ],
            ]
        )

    def _show_digit_buttons(self) -> None:
        """Enable the buttons of the digits of the selected base, and grey out the others."""
        for digit, (cell, button) in self._digit_cells.items():
            enabled = digit in self._integer.digits
            cell.original_widget = button if enabled else urwid.WidgetDisable(button)
            cell.set_attr_map({None: "button" if enabled else "disabled"})

    def _on_base(self, _radio: urwid.RadioButton, state: bool, base: int) -> None:
        """Switch the calculator to the base of a radio button that was selected."""
        if state:
            self._integer.base = base
            self._show_digit_buttons()
            self.display.show(self._integer)


class ThemeButton(urwid.PopUpLauncher[urwid.Button]):
    """A button that opens a pop-up with a radio button per theme.

    Selecting a radio button shows its theme at once.
    :guilabel:`OK` keeps it; :guilabel:`Cancel`, :kbd:`Esc` and a click outside the pop-up show the saved theme again.
    """

    def __init__(self, screen: urwid.BaseScreen) -> None:
        """Wrap a :guilabel:`Theme` button that changes the palette of *screen*.

        The first theme is the saved one.
        """
        super().__init__(urwid.Button("Theme", on_press=self._on_open), close_on_menu=True, close_on_click_outside=True)
        self._screen = screen
        self.theme = next(iter(THEMES))  # the saved theme
        self._shown = self.theme

    def create_pop_up(self) -> urwid.AttrMap[urwid.LineBox[urwid.Filler[urwid.Pile]]]:
        """Return the theme radio buttons over :guilabel:`OK` and :guilabel:`Cancel`."""
        group: list[urwid.RadioButton] = []
        radios = [
            urwid.AttrMap(
                urwid.RadioButton(
                    group, name, state=name == self.theme, on_state_change=self._on_select, user_data=name
                ),
                None,
                "button focus",
            )
            for name in THEMES
        ]
        buttons = urwid.Columns(
            [
                urwid.AttrMap(urwid.Button(label, on_press=callback, align=urwid.CENTER), None, "button focus")
                for label, callback in (("OK", self._on_ok), ("Cancel", self._on_cancel))
            ],
            dividechars=2,
        )
        body = urwid.Pile([*radios, urwid.Divider(), buttons])
        return urwid.AttrMap(urwid.LineBox(urwid.Filler(body, valign=urwid.TOP), title="Theme"), "dialog")

    def get_pop_up_parameters(self) -> PopUpParametersModel:
        """Place the pop-up under the button, or over it when there is no room below."""
        return {"left": 0, "top": 1, "overlay_width": 26, "overlay_height": len(THEMES) + 4, "anchor_height": 1}

    def close_pop_up(self) -> None:
        """Close the pop-up and show the saved theme.

        :guilabel:`OK` saves the shown theme before it closes the pop-up.
        """
        self._show(self.theme)
        super().close_pop_up()

    def _show(self, theme: str) -> None:
        """Draw the screen in *theme*."""
        if theme != self._shown:
            self._screen.register_palette(palette(theme), replace=True)
            self._shown = theme

    def _on_open(self, _button: urwid.Button) -> None:
        """Open the pop-up when the button is pressed."""
        self.open_pop_up()

    def _on_select(self, _radio: urwid.RadioButton, state: bool, theme: str) -> None:
        """Show the theme of a radio button that was selected."""
        if state:
            self._show(theme)

    def _on_ok(self, _button: urwid.Button) -> None:
        """Save the shown theme and close the pop-up."""
        self.theme = self._shown
        self.close_pop_up()

    def _on_cancel(self, _button: urwid.Button) -> None:
        """Close the pop-up, which shows the saved theme again."""
        self.close_pop_up()


def main() -> int:
    """Build the window, run the main loop until F8 or the Exit button, and return the exit status."""
    screen = urwid.display.raw.Screen()
    theme_button = ThemeButton(screen)
    display = Display()
    panes = (NormalPane(display), ProgrammerPane(display))
    tabs = urwid.Tabs(
        [("Normal", panes[0]), ("Programmer", panes[1])],
        bar_selectable=True,
        attr_map="tab",
        selected_map="tab selected",
        focus_map="tab cursor",
    )
    display.show(panes[0].calculator)

    def on_tab_changed(_tabs: urwid.Tabs, old: int | None, new: int | None) -> None:
        """Move the number shown to the calculator of the selected tab, converted to its kind of number."""
        if old is None or new is None:
            raise ValueError("the calculator tabs are never removed")
        calculator = panes[new].calculator
        calculator.load(panes[old].calculator.number)
        display.show(calculator)

    urwid.connect_signal(tabs, "focus changed", on_tab_changed)

    def show_help(_button: urwid.Button | None = None) -> None:
        if stack.depth == 0 and theme_button.pop_up_widget is None:
            stack.open(help_dialog)

    def exit_program(_button: urwid.Button | None = None) -> typing.NoReturn:
        raise urwid.ExitMainLoop

    header = urwid.Columns(
        [
            *(
                (urwid.PACK, urwid.AttrMap(widget, None, "button focus"))
                for widget in (
                    urwid.Button("Help", on_press=show_help),
                    theme_button,
                    urwid.Button("Exit", on_press=exit_program),
                )
            ),
            urwid.Text("Calculator ", align=urwid.RIGHT),
        ],
        dividechars=1,
    )
    body = urwid.Pile([(urwid.PACK, urwid.AttrMap(header, "header")), (urwid.PACK, display), tabs])
    body.focus_position = 2
    keys = (("F1", "help"), ("F2", "theme"), ("F8", "exit"), ("Esc", "clear"), ("Alt+←/→", "tabs"))
    footer = urwid.Text([part for key, action in keys for part in (("key", f" {key}"), f" {action} ")])
    frame: urwid.Frame[urwid.AttrMap[urwid.Pile], None, urwid.AttrMap[urwid.Text]] = urwid.Frame(
        urwid.AttrMap(body, "body"), footer=urwid.AttrMap(footer, "footer")
    )
    stack = urwid.OverlayStack(frame, close_on_menu=True, close_on_click_outside=True)

    def close_help(_button: urwid.Button) -> None:
        stack.close()

    ok_button = urwid.Button("OK", on_press=close_help, align=urwid.CENTER)
    help_dialog = urwid.AttrMap(
        urwid.LineBox(
            urwid.Pile(
                [
                    urwid.Text(HELP),
                    urwid.Divider(),
                    urwid.Padding(urwid.AttrMap(ok_button, None, "button focus"), urwid.CENTER, 8),
                ]
            ),
            title="Help",
        ),
        "dialog",
    )

    def unhandled_input(key: str | tuple[str, int, int, int]) -> None:
        if key == "f8":
            exit_program()
        elif key == "f1":
            show_help()
        elif stack.depth == 0 and theme_button.pop_up_widget is None:
            if key == "f2":
                theme_button.open_pop_up()
            # the keys the tab bar and the header leave unhandled go to the calculator of the selected tab
            elif isinstance(key, str) and isinstance(tabs.focus, CalculatorPane):
                tabs.focus.press(key)

    urwid.command_map.bind(Command.NEXT_TAB, "meta right")
    urwid.command_map.bind(Command.PREVIOUS_TAB, "meta left")
    loop = urwid.MainLoop(
        stack,
        palette(theme_button.theme),
        screen=screen,
        unhandled_input=unhandled_input,
        pop_ups=True,
    )
    loop.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())

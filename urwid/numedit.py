#
# Urwid basic widget classes
#    Copyright (C) 2004-2012  Ian Ward
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


from __future__ import annotations

import re
from collections.abc import Container
from decimal import Decimal

from urwid import Edit


class NumEdit(Edit):
    """NumEdit - edit numerical types

    based on the characters in 'allowed' different numerical types
    can be edited:
      + regular int: 0123456789
      + regular float: 0123456789.
      + regular oct: 01234567
      + regular hex: 0123456789abcdef
    """
    ALLOWED = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

    def __init__(
        self,
        allowed: Container[str],
        caption,
        default: str | bytes,
        trimLeadingZeros: bool = True,
    ):
        super().__init__(caption, default)
        self._allowed = allowed
        self.trimLeadingZeros = trimLeadingZeros

    def valid_char(self, ch: str) -> bool:
        """
        Return true for allowed characters.
        """
        return len(ch) == 1 and ch.upper() in self._allowed

    def keypress(self, size: tuple[int], key: str) -> str | None:
        """
        Handle editing keystrokes.  Remove leading zeros.

        >>> e, size = NumEdit("0123456789", u"", "5002"), (10,)
        >>> e.keypress(size, 'home')
        >>> e.keypress(size, 'delete')
        >>> assert e.edit_text == "002"
        >>> e.keypress(size, 'end')
        >>> assert e.edit_text == "2"
        >>> # binary only
        >>> e, size = NumEdit("01", u"", ""), (10,)
        >>> assert e.edit_text == ""
        >>> e.keypress(size, '1')
        >>> e.keypress(size, '0')
        >>> e.keypress(size, '1')
        >>> assert e.edit_text == "101"
        """
        (maxcol,) = size
        unhandled = Edit.keypress(self, (maxcol,), key)

        if not unhandled and self.trimLeadingZeros:
            # trim leading zeros
            while self.edit_pos > 0 and self.edit_text[:1] == "0":
                self.set_edit_pos(self.edit_pos - 1)
                self.set_edit_text(self.edit_text[1:])

        return unhandled


class IntegerEdit(NumEdit):
    """Edit widget for integer values"""

    def __init__(
        self,
        caption="",
        default: int | str | Decimal | None = None,
        base: int = 10,
    ) -> None:
        """
        caption -- caption markup
        default -- default edit value

        >>> IntegerEdit(u"", 42)
        <IntegerEdit selectable flow widget '42' edit_pos=2>
        >>> e, size = IntegerEdit(u"", "5002"), (10,)
        >>> e.keypress(size, 'home')
        >>> e.keypress(size, 'delete')
        >>> assert e.edit_text == "002"
        >>> e.keypress(size, 'end')
        >>> assert e.edit_text == "2"
        >>> e.keypress(size, '9')
        >>> e.keypress(size, '0')
        >>> assert e.edit_text == "290"
        >>> e, size = IntegerEdit("", ""), (10,)
        >>> assert e.value() is None
        >>> # binary
        >>> e, size = IntegerEdit(u"", "1010", base=2), (10,)
        >>> e.keypress(size, 'end')
        >>> e.keypress(size, '1')
        >>> assert e.edit_text == "10101"
        >>> assert e.value() == Decimal("21")
        >>> # HEX
        >>> e, size = IntegerEdit(u"", "10", base=16), (10,)
        >>> e.keypress(size, 'end')
        >>> e.keypress(size, 'F')
        >>> e.keypress(size, 'f')
        >>> assert e.edit_text == "10Ff"
        >>> assert e.keypress(size, 'G') == 'G'  # unhandled key
        >>> assert e.edit_text == "10Ff"
        >>> # keep leading 0's when not base 10
        >>> e, size = IntegerEdit(u"", "10FF", base=16), (10,)
        >>> assert e.edit_text == "10FF"
        >>> assert e.value() == Decimal("4351")
        >>> e.keypress(size, 'home')
        >>> e.keypress(size, 'delete')
        >>> e.keypress(size, '0')
        >>> assert e.edit_text == "00FF"
        >>> # test exception on incompatible value for base
        >>> e, size = IntegerEdit(u"", "10FG", base=16), (10,)
        Traceback (most recent call last):
            ...
        ValueError: invalid value: 10FG for base 16
        >>> # test exception on float init value
        >>> e, size = IntegerEdit(u"", 10.0), (10,)
        Traceback (most recent call last):
            ...
        ValueError: default: Only 'str', 'int', 'long' or Decimal input allowed
        >>> e, size = IntegerEdit(u"", Decimal("10.0")), (10,)
        Traceback (most recent call last):
            ...
        ValueError: not an 'integer Decimal' instance
        """
        self.base = base
        val = ""
        allowed_chars = self.ALLOWED[:self.base]
        if default is not None:
            if not isinstance(default, (int, str, Decimal)):
                raise ValueError("default: Only 'str', 'int' or Decimal input allowed")

            # convert to a long first, this will raise a ValueError
            # in case a float is passed or some other error
            if isinstance(default, str) and len(default):
                # check if it is a valid initial value
                validation_re = f"^[{allowed_chars}]+$"
                if not re.match(validation_re, str(default), re.IGNORECASE):
                    raise ValueError(f"invalid value: {default} for base {base}")

            elif isinstance(default, Decimal):
                # a Decimal instance with no fractional part
                if default.as_tuple()[2] != 0:
                    raise ValueError("not an 'integer Decimal' instance")

            # convert possible int, long or Decimal to str
            val = str(default)

        super().__init__(allowed_chars, caption, val, trimLeadingZeros=(self.base == 10))

    def value(self) -> Decimal | None:
        """
        Return the numeric value of self.edit_text.

        >>> e, size = IntegerEdit(), (10,)
        >>> e.keypress(size, '5')
        >>> e.keypress(size, '1')
        >>> assert e.value() == 51
        """
        if self.edit_text:
            return Decimal(int(self.edit_text, self.base))

        return None


class FloatEdit(NumEdit):
    """Edit widget for float values."""

    def __init__(
        self,
        caption="",
        default: str | int | Decimal | None = None,
        preserveSignificance: bool = True,
        decimalSeparator: str = '.',
    ) -> None:
        """
        caption -- caption markup
        default -- default edit value
        preserveSignificance -- return value has the same signif. as default
        decimalSeparator -- use '.' as separator by default, optionally a ','

        >>> FloatEdit(u"",  "1.065434")
        <FloatEdit selectable flow widget '1.065434' edit_pos=8>
        >>> e, size = FloatEdit(u"", "1.065434"), (10,)
        >>> e.keypress(size, 'home')
        >>> e.keypress(size, 'delete')
        >>> assert e.edit_text == ".065434"
        >>> e.keypress(size, 'end')
        >>> e.keypress(size, 'backspace')
        >>> assert e.edit_text == ".06543"
        >>> e, size = FloatEdit(), (10,)
        >>> e.keypress(size, '5')
        >>> e.keypress(size, '1')
        >>> e.keypress(size, '.')
        >>> e.keypress(size, '5')
        >>> e.keypress(size, '1')
        >>> assert e.value() == Decimal("51.51"), e.value()
        >>> e, size = FloatEdit(decimalSeparator=":"), (10,)
        Traceback (most recent call last):
            ...
        ValueError: invalid decimalSeparator: :
        >>> e, size = FloatEdit(decimalSeparator=","), (10,)
        >>> e.keypress(size, '5')
        >>> e.keypress(size, '1')
        >>> e.keypress(size, ',')
        >>> e.keypress(size, '5')
        >>> e.keypress(size, '1')
        >>> assert e.edit_text == "51,51"
        >>> e, size = FloatEdit("", "3.1415", preserveSignificance=True), (10,)
        >>> e.keypress(size, 'end')
        >>> e.keypress(size, 'backspace')
        >>> e.keypress(size, 'backspace')
        >>> assert e.edit_text == "3.14"
        >>> assert e.value() == Decimal("3.1400")
        >>> e.keypress(size, '1')
        >>> e.keypress(size, '5')
        >>> e.keypress(size, '9')
        >>> assert e.value() == Decimal("3.1416"), e.value()
        >>> e, size = FloatEdit("", ""), (10,)
        >>> assert e.value() is None
        >>> e, size = FloatEdit(u"", 10.0), (10,)
        Traceback (most recent call last):
            ...
        ValueError: default: Only 'str', 'int', 'long' or Decimal input allowed
        """
        self.significance = None
        self._decimalSeparator = decimalSeparator
        if decimalSeparator not in ['.', ',']:
            raise ValueError(f"invalid decimalSeparator: {decimalSeparator}")

        val = ""
        if default is not None and default != "":
            if not isinstance(default, (int, str, Decimal)):
                raise ValueError("default: Only 'str', 'int' or Decimal input allowed")

            if isinstance(default, str) and default:
                # check if it is a float, raises a ValueError otherwise
                float(default)
                default = Decimal(default)

            if preserveSignificance and isinstance(default, Decimal):
                self.significance = default

            val = str(default)

        super().__init__(self.ALLOWED[0:10] + decimalSeparator,
                                        caption, val)

    def value(self) -> Decimal | None:
        """
        Return the numeric value of self.edit_text.
        """
        if self.edit_text:
            normalized = Decimal(self.edit_text.replace(self._decimalSeparator, '.'))
            if self.significance is not None:
                return normalized.quantize(self.significance)
            return normalized

        return None

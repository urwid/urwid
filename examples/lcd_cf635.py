#!/usr/bin/env python

"""
The crystalfontz 635 has these characters in ROM:

....X. ...... ......
...XX. .XXXXX ..XXX.
..XXX. .XXXXX .XXXXX
.XXXX. .XXXXX .XXXXX
..XXX. .XXXXX .XXXXX
...XX. .XXXXX ..XXX.
....X. ...... ......
...... ...... ......
  0x11   0xd0   0xbb

By adding the characters in CGRAM below we can use them as part of a
horizontal slider control, selected check box and selected radio button
respectively.
"""

from __future__ import annotations

import sys
import typing

import urwid

if typing.TYPE_CHECKING:
    from collections.abc import Callable

    from typing_extensions import Literal, TypeAlias

    from urwid.display.lcd import CF635Screen

    MenuWidget: TypeAlias = "MenuOption | urwid.Text | urwid.Columns | LCDRadioButton"
    MenuStructureItem: TypeAlias = "tuple[str, list[MenuStructureItem]] | MenuWidget"

CGRAM = """
...... ...... ...... ...... ..X... ...... ...... ......
XXXXXX XXXXXX XXXXXX XXXXXX X.XX.. .XXXXX ..XXX. .....X
...... XX.... XXXX.. XXXXXX X.XXX. .X...X .X...X ....XX
...... XX.... XXXX.. XXXXXX X.XXXX .X...X .X...X .X.XX.
...... XX.... XXXX.. XXXXXX X.XXX. .X...X .X...X .XXX..
XXXXXX XXXXXX XXXXXX XXXXXX X.XX.. .XXXXX ..XXX. ..X...
...... ...... ...... ...... ..X... ...... ...... ......
...... ...... ...... ...... ...... ...... ...... ......
"""


def program_cgram(screen_inst: CF635Screen) -> None:
    """Load the character data."""
    # convert .'s and X's above into integer data
    cbuf: list[list[int]] = [[] for x in range(8)]
    for row in CGRAM.strip().split("\n"):
        rowsegments = row.strip().split()
        for num, r in enumerate(rowsegments):
            accum = 0
            for c in r:
                accum = (accum << 1) + (c == "X")
            cbuf[num].append(accum)

    for num, cdata in enumerate(cbuf):
        screen_inst.program_cgram(num, cdata)


class LCDCheckBox(urwid.CheckBox):
    """
    A check box+label that uses only one character for the check box,
    including custom CGRAM character
    """

    states: typing.ClassVar[dict[bool | Literal["mixed"], urwid.SelectableIcon]] = {
        True: urwid.SelectableIcon("\xd0"),
        False: urwid.SelectableIcon("\x05"),
    }
    reserve_columns = 1


class LCDRadioButton(urwid.RadioButton):
    """
    A radio button+label that uses only one character for the radio button,
    including custom CGRAM character
    """

    states: typing.ClassVar[dict[bool | Literal["mixed"], urwid.SelectableIcon]] = {
        True: urwid.SelectableIcon("\xbb"),
        False: urwid.SelectableIcon("\x06"),
    }
    reserve_columns = 1


class LCDProgressBar(urwid.Widget):
    """
    The "progress bar" used by the horizontal slider for this device,
    using custom CGRAM characters
    """

    segments = "\x00\x01\x02\x03"

    _sizing = frozenset([urwid.Sizing.FLOW])

    def __init__(self, data_range: int, value: int) -> None:
        super().__init__()
        self.range = data_range
        self.value = value

    def rows(self, size: tuple[int], focus: bool = False) -> int:
        return 1

    def render(self, size: tuple[int], focus: bool = False) -> urwid.Canvas:  # type: ignore[override]
        """Draw the bar with ``self.segments`` where index 0 is empty and index -1 is completely full."""
        (maxcol,) = size
        steps = self.get_steps(size)
        filled = urwid.int_scale(self.value, self.range, steps)
        full_segments = int(filled / (len(self.segments) - 1))
        last_char = filled % (len(self.segments) - 1) + 1
        s = (
            self.segments[-1] * full_segments
            + self.segments[last_char]
            + self.segments[0] * (maxcol - full_segments - 1)
        )
        return urwid.Text(s).render(size)

    def move_position(self, size: tuple[int], direction: int) -> int:
        """
        Update and return the value one step +ve or -ve, based on
        the size of the displayed bar.

        :param direction: 1 for +ve, 0 for -ve
        """
        steps = self.get_steps(size)
        filled = urwid.int_scale(self.value, self.range, steps)
        filled += 2 * direction - 1
        value = urwid.int_scale(filled, steps, self.range)
        value = max(0, min(self.range - 1, value))
        if value != self.value:
            self.value = value
            self._invalidate()
        return value

    def get_steps(self, size: tuple[int]) -> int:
        """
        Return the number of steps available given size for rendering
        the bar and number of segments we can draw.
        """
        (maxcol,) = size
        return maxcol * (len(self.segments) - 1)


class LCDHorizontalSlider(urwid.WidgetWrap[urwid.Columns]):
    """
    A slider control using custom CGRAM characters
    """

    def __init__(self, data_range: int, value: int, callback: Callable[[int], None]) -> None:
        self.bar = LCDProgressBar(data_range, value)
        cols = urwid.Columns(
            [
                (1, urwid.SelectableIcon("\x11")),
                self.bar,
                (1, urwid.SelectableIcon("\x04")),
            ]
        )
        super().__init__(cols)
        self.callback = callback

    def keypress(self, size: tuple[int], key: str) -> str | None:
        # move the slider based on which arrow is focused
        if key == "enter":
            # use the correct size for adjusting the bar
            self.bar.move_position((self._w.column_widths(size)[1],), self._w.focus_position != 0)
            self.callback(self.bar.value)
            return None

        return typing.cast("str | None", super().keypress(size, key))


class MenuOption(urwid.Button):
    """
    A menu option, indicated with a single arrow character
    """

    def __init__(self, label: str, submenu: Menu) -> None:
        super().__init__("")
        # use a Text widget for label, we want the cursor
        # on the arrow not the label. Button types self._label as SelectableIcon; a Text works
        # equally well here since only its set_text()/text interface is used.
        self._label = urwid.Text("")  # type: ignore[assignment]
        self.set_label(label)

        self._w = urwid.Columns([(1, urwid.SelectableIcon("\xdf")), self._label])

        urwid.connect_signal(self, "click", lambda option: show_menu(submenu))

    def keypress(self, size: tuple[int], key: str) -> str | None:
        if key == "right":
            key = "enter"
        return super().keypress(size, key)


class Menu(urwid.ListBox[int]):
    """A submenu of :class:`MenuOption` widgets that can return to its parent menu."""

    def __init__(self, widgets: list[MenuWidget]) -> None:
        self.menu_parent: Menu | None = None
        super().__init__(urwid.SimpleListWalker(widgets))

    def keypress(self, size: tuple[int, int], key: str) -> str | None:  # type: ignore[override]
        """Go back to the previous menu when :kbd:`left` or :kbd:`esc` is pressed."""
        parsed_key = super().keypress(size, key)
        if parsed_key in {"left", "esc"} and self.menu_parent:
            show_menu(self.menu_parent)
            return None

        return parsed_key


def build_menus() -> Menu:
    """Build and return the top-level settings menu for the LCD display."""
    cursor_option_group: list[urwid.RadioButton] = []

    def cursor_option(label: str, style: Literal[1, 2, 3, 4]) -> LCDRadioButton:
        """Build a radio button that sets the cursor style when selected."""

        def on_change(b: urwid.RadioButton, state: bool) -> None:
            if state:
                screen.set_cursor_style(style)

        b = LCDRadioButton(cursor_option_group, label, screen.cursor_style == style)
        urwid.connect_signal(b, "change", on_change)
        return b

    def display_setting(label: str, data_range: int, fn: Callable[[int], None]) -> urwid.Columns:
        slider = LCDHorizontalSlider(data_range, data_range // 2, fn)
        return urwid.Columns(
            [
                urwid.Text(label),
                (10, slider),
            ]
        )

    def led_custom(index: Literal[0, 1, 2, 3]) -> urwid.Columns:
        def exp_scale_led(rg: Literal[0, 1]) -> Callable[[int], None]:
            """Apply an exponential transformation so apparent brightness increases in a natural way."""
            return lambda value: screen.set_led_pin(
                index,
                rg,
                [0, 1, 2, 3, 4, 5, 6, 8, 11, 14, 18, 23, 29, 38, 48, 61, 79, 100][value],
            )

        return urwid.Columns(
            [
                (2, urwid.Text(f"{index:d}R")),
                LCDHorizontalSlider(18, 0, exp_scale_led(0)),
                (2, urwid.Text(" G")),
                LCDHorizontalSlider(18, 0, exp_scale_led(1)),
            ]
        )

    menu_structure: list[MenuStructureItem] = [
        (
            "Display Settings",
            [
                display_setting("Brightness", 101, screen.set_backlight),
                display_setting("Contrast", 76, lambda x: screen.set_lcd_contrast(x + 75)),
            ],
        ),
        (
            "Cursor Settings",
            [
                cursor_option("Block", screen.CURSOR_BLINKING_BLOCK),
                cursor_option("Underscore", screen.CURSOR_UNDERSCORE),
                cursor_option("Block + Underscore", screen.CURSOR_BLINKING_BLOCK_UNDERSCORE),
                cursor_option("Inverting Block", screen.CURSOR_INVERTING_BLINKING_BLOCK),
            ],
        ),
        (
            "LEDs",
            [
                led_custom(0),
                led_custom(1),
                led_custom(2),
                led_custom(3),
            ],
        ),
        (
            "About this Demo",
            [
                urwid.Text(
                    "This is a demo of Urwid's CF635Display "
                    "module. If you need an interface for a limited "
                    "character display device this should serve as a "
                    "good example for implementing your own display "
                    "module and menu-driven application."
                ),
            ],
        ),
    ]

    def build_submenu(ms: list[MenuStructureItem]) -> Menu:
        """Recursively build a :class:`Menu` from a list of menu-structure items."""
        options: list[MenuWidget] = []
        submenus: list[Menu] = []
        for opt in ms:
            # shortform for MenuOptions
            if isinstance(opt, tuple):
                name, sub = opt
                submenu = build_submenu(sub)
                opt = MenuOption(name, submenu)  # noqa: PLW2901
                submenus.append(submenu)
            options.append(opt)
        menu = Menu(options)
        for s in submenus:
            s.menu_parent = menu
        return menu

    return build_submenu(menu_structure)


screen = urwid.display.lcd.CF635Screen(sys.argv[1])
# set up our font
program_cgram(screen)
loop = urwid.MainLoop(build_menus(), screen=screen)
# FIXME: want screen to know it is in narrow mode, or better yet,
# do the unicode conversion for us
urwid.set_encoding("narrow")


def show_menu(menu: Menu) -> None:
    """Replace the main loop's displayed widget with *menu*."""
    loop.widget = menu


loop.run()

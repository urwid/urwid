#!/usr/bin/env python

"""Example: a chart drawn with terminal escape sequences, shown in a TerminalOutput widget.

The chart is drawn again for the new size whenever the window is resized, and the chart drawn before scrolls into
the scrollback: Page Up and Page Down, or the mouse wheel, scroll through it, and q exits.
"""

from __future__ import annotations

import math

import urwid

# A cell filled from the bottom in eighths, from empty to full.
EIGHTHS = " ▁▂▃▄▅▆▇█"


def chart(columns: int, rows: int) -> str:
    """Return the escape sequences and text that draw the chart on a screen of *columns* by *rows*."""
    parts = [
        # move the chart drawn before into the scrollback, then start again at the top-left corner
        f"\x1b[{rows};1H" + "\n" * rows + "\x1b[H",
        f"\x1b[1mTerminalOutput {columns}x{rows}\x1b[0m",
        # a strip of the 216 colors of the 256-color cube
        "\x1b[2;1H" + "".join(f"\x1b[48;5;{16 + column * 216 // columns}m " for column in range(columns)) + "\x1b[0m",
    ]
    height = rows - 2
    for row in range(height):
        level = (height - 1 - row) * 8
        line = []
        for column in range(columns):
            value = (math.sin(4 * math.pi * column / columns) + 1) / 2 * height * 8
            red, blue = 255 * column // columns, 255 - 255 * column // columns
            line.append(f"\x1b[38;2;{red};96;{blue}m{EIGHTHS[min(8, max(0, round(value) - level))]}")
        parts.append(f"\x1b[{row + 3};1H" + "".join(line) + "\x1b[0m")
    return "".join(parts)


def main() -> None:
    """Show the chart, drawn again on each resize, with the key handling."""
    # a size no window has, so the first render resizes and draws the chart for the real size
    output = urwid.TerminalOutput(size=(1, 1))

    def draw_for(widget: urwid.TerminalOutput, size: tuple[int, int]) -> None:
        widget.write(chart(*size))

    urwid.connect_signal(output, "resize", draw_for)

    def unhandled(key: str | tuple[str, int, int, int]) -> None:
        if key == "q":
            raise urwid.ExitMainLoop

    frame: urwid.Frame[urwid.TerminalOutput, None, urwid.Text] = urwid.Frame(
        output,
        footer=urwid.Text("Page Up/Page Down or the mouse wheel: scroll back  q: quit"),
    )
    urwid.MainLoop(frame, unhandled_input=unhandled).run()


if __name__ == "__main__":
    main()

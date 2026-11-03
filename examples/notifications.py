#!/usr/bin/env python

"""Example: messages of each severity in the footer of a window, each shown for five seconds.

i, w and e post an info, a warning and an error message, s posts one that stays until it is dismissed,
d dismisses the newest message, c clears them all, and q exits. The keys work in either case.
"""

from __future__ import annotations

import itertools

import urwid


def main() -> None:
    """Build the window with the notifications footer and the key handling, and run the main loop."""
    notifications = urwid.Notifications(
        max_count=5,
        severity_attr={
            urwid.Severity.INFO: "info",
            urwid.Severity.WARNING: "warning",
            urwid.Severity.ERROR: "error",
        },
        default="i: info  w: warning  e: error  s: sticky  d: dismiss  c: clear  q: quit",
        default_attr="help",
    )
    numbers = itertools.count(1)
    severities = {"i": urwid.Severity.INFO, "w": urwid.Severity.WARNING, "e": urwid.Severity.ERROR}

    def unhandled(key: str | tuple[str, int, int, int]) -> None:
        if not isinstance(key, str):
            return
        # Shift or Caps Lock sends the upper-case key
        key = key.lower()
        if key == "q":
            raise urwid.ExitMainLoop
        if key in severities:
            severity = severities[key]
            notifications.notify(f"{severity.name.lower()} message {next(numbers)}", severity=severity)
        elif key == "s":
            notifications.notify(f"sticky message {next(numbers)}, d dismisses it", timeout=None)
        elif key == "d" and notifications.notifications:
            notifications.dismiss(notifications.notifications[-1])
        elif key == "c":
            notifications.clear()

    body = urwid.Filler(urwid.Text("Messages appear in the footer, oldest at the top.", align="center"))
    frame: urwid.Frame[urwid.Filler[urwid.Text], None, urwid.Notifications] = urwid.Frame(body, footer=notifications)
    palette: list[tuple[str, str, str]] = [
        ("help", "black", "light gray"),
        ("info", "white", "dark blue"),
        ("warning", "black", "brown"),
        ("error", "white", "dark red"),
    ]
    urwid.MainLoop(frame, palette, unhandled_input=unhandled).run()


if __name__ == "__main__":
    main()

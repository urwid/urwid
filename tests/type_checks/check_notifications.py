"""Type checker fixture for the Notifications widget.

mypy and Pyrefly check this module; nothing in it runs.
"""

from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    from collections.abc import Hashable
    from typing import assert_type

    import urwid

    def notifications(loop: urwid.MainLoop) -> None:
        """Type the handle notify() returns and the properties."""
        widget = urwid.Notifications(
            max_count=1,
            severity_attr={urwid.Severity.ERROR: "error"},
            default=("dim", "ready"),
            loop=loop,
        )
        notification = widget.notify("saved", severity=urwid.Severity.WARNING, timeout=None)
        assert_type(notification, urwid.Notification)
        assert_type(notification.widget, urwid.Text)
        assert_type(notification.severity, urwid.Severity)
        assert_type(notification.timeout, float | None)
        assert_type(widget.dismiss(notification), bool)
        assert_type(widget.notifications, tuple[urwid.Notification, ...])
        assert_type(widget.loop, urwid.MainLoop | None)
        assert_type(widget.timeout, float | None)
        assert_type(widget.max_count, int | None)
        assert_type(widget.severity_attr, dict[urwid.Severity, dict[Hashable, Hashable]])
        assert_type(widget.default_attr, dict[Hashable, Hashable] | None)
        urwid.Frame(urwid.SolidFill(), footer=widget)

"""Type checker fixture for the Spinner widget.

mypy and Pyrefly check this module; nothing in it runs.
"""

from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    from typing import assert_type

    import urwid

    def spinner(loop: urwid.MainLoop) -> None:
        """Type the frame sets, the methods and the properties."""
        widget = urwid.Spinner(urwid.SpinnerFrames.ARC, interval=0.2, idle=("dim", "done"), loop=loop)
        urwid.Spinner(["a", "b"])
        urwid.Spinner(("a", "b"), align=urwid.RIGHT)
        assert_type(widget.start(), None)
        assert_type(widget.step(), None)
        assert_type(widget.stop(), None)
        assert_type(widget.running, bool)
        assert_type(widget.frames, tuple[str, ...])
        assert_type(widget.interval, float)
        assert_type(widget.idle, urwid.util._TagMarkup | None)
        assert_type(widget.loop, urwid.MainLoop | None)
        widget.interval = 1
        widget.idle = None
        urwid.Columns([(urwid.PACK, widget), urwid.Text("working")])

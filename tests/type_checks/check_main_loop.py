"""Type checker fixture for the running-loop lookup.

mypy and Pyrefly check this module; nothing in it runs.
"""

from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    from typing import assert_type

    import urwid

    def running_loop() -> None:
        """Type the running loop as a MainLoop, or None from the lookup that does not raise."""
        assert_type(urwid.get_running_loop(), urwid.MainLoop)
        assert_type(urwid.get_running_loop_or_none(), urwid.MainLoop | None)

"""Package with EventLoop implementations for urwid."""

from __future__ import annotations

import sys

from .abstract_loop import EventLoop, ExitMainLoop
from .asyncio_loop import AsyncioEventLoop
from .main_loop import MainLoop, get_running_loop, get_running_loop_or_none
from .select_loop import SelectEventLoop

__all__ = (
    "AsyncioEventLoop",
    "EventLoop",
    "ExitMainLoop",
    "MainLoop",
    "SelectEventLoop",
    "get_running_loop",
    "get_running_loop_or_none",
)

try:
    from .twisted_loop import TwistedEventLoop

    __all__ += ("TwistedEventLoop",)  # type: ignore[assignment]
except ImportError:
    pass

try:
    from .tornado_loop import TornadoEventLoop

    __all__ += ("TornadoEventLoop",)  # type: ignore[assignment]
except ImportError:
    pass

try:
    from .glib_loop import GLibEventLoop

    __all__ += ("GLibEventLoop",)  # type: ignore[assignment]
except ImportError:
    pass

try:
    from .trio_loop import TrioEventLoop

    __all__ += ("TrioEventLoop",)  # type: ignore[assignment]
except ImportError:
    pass

if sys.platform != "win32":
    # ZMQEventLoop cause interpreter crash on windows
    try:
        from .zmq_loop import ZMQEventLoop

        __all__ += ("ZMQEventLoop",)  # type: ignore[assignment]
    except ImportError:
        pass

"""Package with EventLoop implementations for urwid."""

from __future__ import annotations

from .abstract_loop import EventLoop, ExitMainLoop
from .asyncio_loop import AsyncioEventLoop
from .main_loop import MainLoop
from .select_loop import SelectEventLoop

__all__ = ("EventLoop", "ExitMainLoop", "AsyncioEventLoop", "MainLoop", "SelectEventLoop")

try:
    from .twisted_loop import TwistedEventLoop

    __all__ += ("TwistedEventLoop",)
except ImportError:
    pass

try:
    from .tornado_loop import TornadoEventLoop

    __all__ += ("TornadoEventLoop",)
except ImportError:
    pass

try:
    from .glib_loop import GLibEventLoop

    __all__ += ("GLibEventLoop",)
except ImportError:
    pass

try:
    from .trio_loop import TrioEventLoop

    __all__ += ("TrioEventLoop",)
except ImportError:
    pass

try:
    from .zmq_loop import ZMQEventLoop

    __all__ += ("ZMQEventLoop",)
except ImportError:
    pass

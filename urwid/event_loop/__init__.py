"""Package with EventLoop implementations for urwid."""

from __future__ import annotations

from .abstract_loop import EventLoop, ExitMainLoop
from .asyncio_loop import AsyncioEventLoop
from .main_loop import MainLoop
from .select_loop import SelectEventLoop

try:
    from .twisted_loop import TwistedEventLoop
except ImportError:
    pass

try:
    from .tornado_loop import TornadoEventLoop
except ImportError:
    pass

try:
    from .glib_loop import GLibEventLoop
except ImportError:
    pass

try:
    from .twisted_loop import TwistedEventLoop
except ImportError:
    pass

try:
    from .trio_loop import TrioEventLoop
except ImportError:
    pass

try:
    from .zmq_loop import ZMQEventLoop
except ImportError:
    pass

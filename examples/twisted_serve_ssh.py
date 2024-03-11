"""
Twisted integration for Urwid.

This module allows you to serve Urwid applications remotely over ssh.

The idea is that the server listens as an SSH server, and each connection is
routed by Twisted to urwid, and the urwid UI is routed back to the console.
The concept was a bit of a head-bender for me, but really we are just sending
escape codes and the what-not back to the console over the shell that ssh has
created. This is the same service as provided by the UI components in
twisted.conch.insults.window, except urwid has more features, and seems more
mature.

This module is not highly configurable, and the API is not great, so
don't worry about just using it as an example and copy-pasting.

Process
-------


TODO:

- better gpm tracking: there is no place for os.Popen in a Twisted app I
  think.

Copyright: 2010, Ali Afshar <aafshar@gmail.com>
License:   MIT <https://www.opensource.org/licenses/mit-license.php>

Portions Copyright: 2010, Ian Ward <ian@excess.org>
Licence:   LGPL <https://opensource.org/licenses/lgpl-2.1.php>
"""

from __future__ import annotations

import typing

from twisted.application.internet import TCPServer
from twisted.application.service import Application
from twisted.conch.insults.insults import ServerProtocol, TerminalProtocol
from twisted.conch.interfaces import IConchUser, ISession
from twisted.conch.manhole_ssh import (
    ConchFactory,
    TerminalRealm,
    TerminalSession,
    TerminalSessionTransport,
    TerminalUser,
)
from twisted.cred.portal import Portal
from twisted.python.components import Adapter, Componentized
from zope.interface import Attribute, Interface, implementer

import urwid
from urwid.display.raw import Screen

if typing.TYPE_CHECKING:
    from twisted.cred.checkers import ICredentialsChecker


class IUrwidUi(Interface):
    """Toplevel urwid widget"""

    toplevel = Attribute("Urwid Toplevel Widget")
    palette = Attribute("Urwid Palette")
    screen = Attribute("Urwid Screen")
    loop = Attribute("Urwid Main Loop")

    def create_urwid_toplevel():
        """Create a toplevel widget."""

    def create_urwid_mainloop():
        """Create the urwid main loop."""


class IUrwidMind(Interface):
    ui = Attribute("")
    terminalProtocol = Attribute("")
    terminal = Attribute("")
    checkers = Attribute("")
    avatar = Attribute("The avatar")

    def push(data):
        """Push data"""

    def draw():
        """Refresh the UI"""


class UrwidUi:
    def __init__(self, urwid_mind):
        self.mind = urwid_mind
        self.toplevel = self.create_urwid_toplevel()
        self.palette = self.create_urwid_palette()
        self.screen = TwistedScreen(self.mind.terminalProtocol)
        self.loop = self.create_urwid_mainloop()

    def create_urwid_toplevel(self):
        raise NotImplementedError

    def create_urwid_palette(self):
        return

    def create_urwid_mainloop(self):
        evl = urwid.TwistedEventLoop(manage_reactor=False)
        loop = urwid.MainLoop(
            self.toplevel,
            screen=self.screen,
            event_loop=evl,
            unhandled_input=self.mind.unhandled_key,
            palette=self.palette,
        )
        self.screen.loop = loop
        loop.run()
        return loop


class UnhandledKeyHandler:
    def __init__(self, mind):
        self.mind = mind

    def push(self, key):
        if isinstance(key, tuple):
            return None

        f = getattr(self, f"key_{key.replace(' ', '_')}", None)
        if f is None:
            return None

        return f(key)

    def key_ctrl_c(self, key):
        self.mind.terminal.loseConnection()


@implementer(IUrwidMind)
class UrwidMind(Adapter):
    cred_checkers: typing.ClassVar[list[ICredentialsChecker]] = []
    ui = None

    ui_factory = None
    unhandled_key_factory = UnhandledKeyHandler

    @property
    def avatar(self):
        return IConchUser(self.original)

    def set_terminalProtocol(self, terminalProtocol):
        self.terminalProtocol = terminalProtocol
        self.terminal = terminalProtocol.terminal
        self.unhandled_key_handler = self.unhandled_key_factory(self)
        self.unhandled_key = self.unhandled_key_handler.push
        self.ui = self.ui_factory(self)

    def push(self, data):
        self.ui.screen.push(data)

    def draw(self):
        self.ui.loop.draw_screen()


class TwistedScreen(Screen):
    """A Urwid screen which knows about the Twisted terminal protocol that is
    driving it.

    A Urwid screen is responsible for:

    1. Input
    2. Output

    Input is achieved in normal urwid by passing a list of available readable
    file descriptors to the event loop for polling/selecting etc. In the
    Twisted situation, this is not necessary because Twisted polls the input
    descriptors itself. Urwid allows this by being driven using the main loop
    instance's `process_input` method which is triggered on Twisted protocol's
    standard `dataReceived` method.
    """

    def __init__(self, terminalProtocol):
        # We will need these later
        self.terminalProtocol = terminalProtocol
        self.terminal = terminalProtocol.terminal
        super().__init__()
        self.colors = 16
        self._pal_escape = {}
        self.bright_is_bold = True
        self.register_palette_entry(None, "black", "white")
        urwid.signals.connect_signal(self, urwid.UPDATE_PALETTE_ENTRY, self._on_update_palette_entry)
        # Don't need to wait for anything to start
        self._started = True

    # Urwid Screen API

    def get_cols_rows(self) -> tuple[int, int]:
        """Get the size of the terminal as (cols, rows)"""
        return self.terminalProtocol.width, self.terminalProtocol.height

    def draw_screen(self, size: tuple[int, int], canvas: urwid.Canvas) -> None:
        """Render a canvas to the terminal.

        The canvas contains all the information required to render the Urwid
        UI. The content method returns a list of rows as (attr, cs, text)
        tuples. This very simple implementation iterates each row and simply
        writes it out.
        """
        (_maxcol, _maxrow) = size
        # self.terminal.eraseDisplay()
        lasta = None
        for i, row in enumerate(canvas.content()):
            self.terminal.cursorPosition(0, i)
            for attr, _cs, text in row:
                if attr != lasta:
                    text = f"{self._attr_to_escape(attr)}{text}"  # noqa: PLW2901
                lasta = attr
                # if cs or attr:
                #    print(cs, attr)
                self.write(text)
        cursor = canvas.get_cursor()
        if cursor is not None:
            self.terminal.cursorPosition(*cursor)

    # XXX from base screen
    def set_mouse_tracking(self, enable=True):
        """
        Enable (or disable) mouse tracking.

        After calling this function get_input will include mouse
        click events along with keystrokes.
        """
        if enable:
            self.write(urwid.escape.MOUSE_TRACKING_ON)
        else:
            self.write(urwid.escape.MOUSE_TRACKING_OFF)

    # twisted handles polling, so we don't need the loop to do it, we just
    # push what we get to the loop from dataReceived.
    def hook_event_loop(self, event_loop, callback):
        self._urwid_callback = callback
        self._evl = event_loop

    def unhook_event_loop(self, event_loop):
        pass

    # Do nothing here either. Not entirely sure when it gets called.
    def get_input(self, raw_keys=False):
        return

    def get_available_raw_input(self):
        data = self._data
        self._data = []
        return data

    # Twisted driven
    def push(self, data):
        """Receive data from Twisted and push it into the urwid main loop.

        We must here:

        1. filter the input data against urwid's input filter.
        2. Calculate escapes and other clever things using urwid's
        `escape.process_keyqueue`.
        3. Pass the calculated keys as a list to the Urwid main loop.
        4. Redraw the screen
        """
        self._data = list(map(ord, data))
        self.parse_input(self._evl, self._urwid_callback)
        self.loop.draw_screen()

    # Convenience
    def write(self, data):
        self.terminal.write(data)

    # Private
    def _on_update_palette_entry(self, name, *attrspecs):
        # copy the attribute to a dictionary containing the escape sequences
        self._pal_escape[name] = self._attrspec_to_escape(attrspecs[{16: 0, 1: 1, 88: 2, 256: 3}[self.colors]])

    def _attr_to_escape(self, a):
        if a in self._pal_escape:
            return self._pal_escape[a]
        if isinstance(a, urwid.AttrSpec):
            return self._attrspec_to_escape(a)
        # undefined attributes use default/default
        # TODO: track and report these
        return self._attrspec_to_escape(urwid.AttrSpec("default", "default"))

    def _attrspec_to_escape(self, a):
        """
        Convert AttrSpec instance a to an escape sequence for the terminal

        >>> s = Screen()
        >>> s.set_terminal_properties(colors=256)
        >>> a2e = s._attrspec_to_escape
        >>> a2e(s.AttrSpec('brown', 'dark green'))
        '\\x1b[0;33;42m'
        >>> a2e(s.AttrSpec('#fea,underline', '#d0d'))
        '\\x1b[0;38;5;229;4;48;5;164m'
        """
        if a.foreground_high:
            fg = f"38;5;{a.foreground_number:d}"
        elif a.foreground_basic:
            if a.foreground_number > 7:
                if self.bright_is_bold:
                    fg = f"1;{a.foreground_number - 8 + 30:d}"
                else:
                    fg = f"{a.foreground_number - 8 + 90:d}"
            else:
                fg = f"{a.foreground_number + 30:d}"
        else:
            fg = "39"
        st = "1;" * a.bold + "4;" * a.underline + "7;" * a.standout
        if a.background_high:
            bg = f"48;5;{a.background_number:d}"
        elif a.background_basic:
            if a.background_number > 7:
                # this doesn't work on most terminals
                bg = f"{a.background_number - 8 + 100:d}"
            else:
                bg = f"{a.background_number + 40:d}"
        else:
            bg = "49"
        return f"{urwid.escape.ESC}[0;{fg};{st}{bg}m"


class UrwidTerminalProtocol(TerminalProtocol):
    """A terminal protocol that knows to proxy input and receive output from
    Urwid.

    This integrates with the TwistedScreen in a 1:1.
    """

    def __init__(self, urwid_mind):
        self.urwid_mind = urwid_mind
        self.width = 80
        self.height = 24

    def connectionMade(self):
        self.urwid_mind.set_terminalProtocol(self)
        self.terminalSize(self.height, self.width)

    def terminalSize(self, height, width):
        """Resize the terminal."""
        self.width = width
        self.height = height
        self.urwid_mind.ui.loop.screen_size = None
        self.terminal.eraseDisplay()
        self.urwid_mind.draw()

    def dataReceived(self, data):
        """Received data from the connection.

        This overrides the default implementation which parses and passes to
        the keyReceived method. We don't do that here, and must not do that so
        that Urwid can get the right juice (which includes things like mouse
        tracking).

        Instead we just pass the data to the screen instance's dataReceived,
        which handles the proxying to Urwid.
        """
        self.urwid_mind.push(data)

    def _unhandled_input(self, data):
        # evil
        proceed = True
        if hasattr(self.urwid_toplevel, "app"):
            proceed = self.urwid_toplevel.app.unhandled_input(self, data)
        if not proceed:
            return
        if data == "ctrl c":
            self.terminal.loseConnection()


class UrwidServerProtocol(ServerProtocol):
    def dataReceived(self, data):
        self.terminalProtocol.dataReceived(data)


class UrwidUser(TerminalUser):
    """A terminal user that remembers its avatarId

    The default implementation doesn't
    """

    def __init__(self, original, avatarId):
        super().__init__(original, avatarId)
        self.avatarId = avatarId


class UrwidTerminalSession(TerminalSession):
    """A terminal session that remembers the avatar and chained protocol for
    later use. And implements a missing method for changed Window size.

    Note: This implementation assumes that each SSH connection will only
    request a single shell, which is not an entirely safe assumption, but is
    by far the most common case.
    """

    def openShell(self, proto):
        """Open a shell."""
        self.chained_protocol = UrwidServerProtocol(UrwidTerminalProtocol, IUrwidMind(self.original))
        TerminalSessionTransport(proto, self.chained_protocol, IConchUser(self.original), self.height, self.width)

    def windowChanged(self, dimensions):
        """Called when the window size has changed."""
        (h, w, _x, _y) = dimensions
        self.chained_protocol.terminalProtocol.terminalSize(h, w)


class UrwidRealm(TerminalRealm):
    """Custom terminal realm class-configured to use our custom Terminal User
    Terminal Session.
    """

    def __init__(self, mind_factory):
        super().__init__()
        self.mind_factory = mind_factory

    def _getAvatar(self, avatarId):
        comp = Componentized()
        user = UrwidUser(comp, avatarId)
        comp.setComponent(IConchUser, user)
        sess = UrwidTerminalSession(comp)
        comp.setComponent(ISession, sess)
        mind = self.mind_factory(comp)
        comp.setComponent(IUrwidMind, mind)
        return user

    def requestAvatar(self, avatarId, mind, *interfaces):
        for i in interfaces:
            if i is IConchUser:
                return (IConchUser, self._getAvatar(avatarId), lambda: None)
        raise NotImplementedError()


def create_server_factory(urwid_mind_factory):
    """Convenience to create a server factory with a portal that uses a realm
    serving a given urwid widget against checkers provided.
    """
    rlm = UrwidRealm(urwid_mind_factory)
    ptl = Portal(rlm, urwid_mind_factory.cred_checkers)
    return ConchFactory(ptl)


def create_service(urwid_mind_factory, port, *args, **kw):
    """Convenience to create a service for use in tac-ish situations."""
    f = create_server_factory(urwid_mind_factory)
    return TCPServer(port, f, *args, **kw)


def create_application(application_name, urwid_mind_factory, port, *args, **kw):
    """Convenience to create an application suitable for tac file"""
    application = Application(application_name)
    svc = create_service(urwid_mind_factory, 6022)
    svc.setServiceParent(application)
    return application

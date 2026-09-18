# Urwid web (CGI/Asynchronous Javascript) display module
#    Copyright (C) 2004-2007  Ian Ward
#
#    This library is free software; you can redistribute it and/or
#    modify it under the terms of the GNU Lesser General Public
#    License as published by the Free Software Foundation; either
#    version 2.1 of the License, or (at your option) any later version.
#
#    This library is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#    Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public
#    License along with this library; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#
# Urwid web site: https://urwid.org/


"""
Urwid web application display module
"""

from __future__ import annotations

import dataclasses
import functools
import glob
import html
import os
import pathlib
import secrets
import selectors
import signal
import socket
import string
import sys
import tempfile
import typing
from contextlib import suppress
from email.message import Message

from urwid.str_util import calc_text_pos, calc_width, move_next_char
from urwid.util import StoppingContext, get_encoding

from .common import AttrSpec, BaseScreen

if typing.TYPE_CHECKING:
    from types import FrameType

    from typing_extensions import Literal

    from urwid.canvas import Canvas

TEMP_DIR = tempfile.gettempdir()
CURRENT_DIR = pathlib.Path(__file__).parent

_js_code = CURRENT_DIR.joinpath("_web.js").read_text("utf-8")

ALARM_DELAY = 60
POLL_CONNECT = 3
MAX_COLS = 200
MAX_ROWS = 100
MAX_READ = 4096
BUF_SZ = 16384

# Characters that may appear in an id produced by secrets.token_urlsafe():
# the URL-safe base64 alphabet. Used to validate client-supplied ids before
# they are interpolated into pipe file names.
_URWID_ID_CHARS = frozenset(string.ascii_letters + string.digits + "-_")
_URWID_ID_MAX_LEN = 43  # len(secrets.token_urlsafe(32)); generous upper bound

# replace control characters with ?'s
_trans_table = "?" * 32 + "".join([chr(x) for x in range(32, 256)])

_css_style = CURRENT_DIR.joinpath("_web.css").read_text("utf-8")

# HTML Initial Page
_html_page = [
    """<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN"
 "http://www.w3.org/TR/html4/loose.dtd">
<html>
<head>
<title>Urwid Web Display - """,
    """</title>
<style type="text/css">
"""
    + _css_style
    + r"""
</style>
</head>
<body id="body" onload="load_web_display()">
<div style="position:absolute; visibility:hidden;">
<br id="br"\>
<pre>The quick brown fox jumps over the lazy dog.<span id="testchar">X</span>
<span id="testchar2">Y</span></pre>
</div>
Urwid Web Display - <b>""",
    """</b> -
Status: <span id="status">Set up</span>
<script type="text/javascript">
//<![CDATA[
"""
    + _js_code
    + """
//]]>
</script>
<pre id="text"></pre>
</body>
</html>
""",
]


#: index into the (basic, mono, high_88, high_256, high_true) tuple stored per palette entry,
#: selected by the ``colors`` value passed to :meth:`Screen.set_terminal_properties`
_COLOUR_INDEX = {1: 1, 16: 0, 88: 2, 256: 3, 2**24: 4}

_default_foreground = "black"
_default_background = "light gray"


class Screen(BaseScreen):
    def __init__(self) -> None:
        super().__init__()
        self.has_color = True
        self._started = False
        self.colors = 2**24  # browsers render arbitrary RGB, so default to true color
        self.bright_is_bold = False  # ignored: the browser renders bold as requested
        self.has_underline = True  # ignored: the browser renders underline as requested
        self._colour_index = _COLOUR_INDEX[self.colors]
        self.register_palette_entry(None, _default_foreground, _default_background)

    @property
    def started(self) -> bool:
        return self._started

    def set_terminal_properties(
        self,
        colors: int | None = None,
        bright_is_bold: bool | None = None,
        has_underline: bool | None = None,
    ) -> None:
        """Set the number of colors used to resolve named palette entries.

        :param colors: one of 1, 16, 88, 256 or 2**24 (2**24, true color, is the default,
            since a browser can render any RGB color directly)
        :param bright_is_bold: ignored, kept for API parity with the other display modules
        :param has_underline: ignored, kept for API parity with the other display modules
        :raises KeyError: *colors* is not one of the supported palette sizes.
        """
        if colors is not None:
            self._colour_index = _COLOUR_INDEX[colors]
            self.colors = colors
        if bright_is_bold is not None:
            self.bright_is_bold = bright_is_bold
        if has_underline is not None:
            self.has_underline = has_underline

    def _handle_resize_request(self, request: str) -> bool:
        """Apply the screen size from a "window resize <cols> <rows>" request.

        :param request: single input line without the trailing newline.
        :returns: True if the request was a valid resize command and the screen size was updated.
        """
        if not request.startswith("window resize "):
            return False

        input_resize = request.removeprefix("window resize ").split(" ")
        if len(input_resize) != 2:
            self.logger.debug("Invalid resize input format: %r", request)
            return False

        x, y = input_resize
        if not x.isdecimal() or not y.isdecimal():
            self.logger.debug("Invalid resize input format: %r", request)
            return False

        self._set_screen_size(int(x), int(y))
        return True

    def set_mouse_tracking(self, enable: bool = True) -> None:
        """Not yet implemented"""

    def tty_signal_keys(self, *args: typing.Any, **vargs: typing.Any) -> None:
        """Do nothing."""

    def start(self, *args: typing.Any, **kwargs: typing.Any) -> StoppingContext:
        """
        This function reads the initial screen size, generates a unique id and handles cleanup when fn exits.

        web_display.set_preferences(..) must be called before calling this function for the preferences to take effect

        :raises RuntimeError: the ``HTTP_X_URWID_METHOD`` environment variable is not set.
        """
        if self._started:
            return StoppingContext(self)

        self.update_method = os.environ.get("HTTP_X_URWID_METHOD", "")
        if not self.update_method:
            raise RuntimeError("'HTTP_X_URWID_METHOD' environment vairable is not set")

        if self.update_method not in {"multipart", "polling"}:
            self.logger.debug("Unsupported update method requested: %r", self.update_method)
            sys.stdout.write("Status: 400 Bad Request\r\n\r\n")
            sys.exit(0)

        if self.update_method == "polling" and not _prefs.allow_polling:
            sys.stdout.write("Status: 403 Forbidden\r\n\r\n")
            sys.exit(0)

        client_init = sys.stdin.read(50)
        if not self._handle_resize_request(client_init.split("\n", 1)[0].strip()):
            self.logger.debug("Invalid initial client request: %r", client_init)
            sys.stdout.write("Status: 400 Bad Request\r\n\r\n")
            sys.exit(0)

        self.last_screen: dict[tuple[tuple[AttrSpec | str | None, str] | int | None, ...], list[int]] = {}
        self.last_screen_width = 0

        clients = glob.glob(os.path.join(_prefs.pipe_dir, "urwid*.in"))
        if len(clients) >= _prefs.max_clients:
            sys.stdout.write("Status: 503 Sever Busy\r\n\r\n")
            sys.exit(0)

        urwid_id = secrets.token_urlsafe(16)
        self.pipe_name = os.path.join(_prefs.pipe_dir, f"urwid_{urwid_id}")
        os.mkfifo(f"{self.pipe_name}.in", 0o600)
        signal.signal(signal.SIGTERM, self._cleanup_pipe)

        self.input_fd = os.open(f"{self.pipe_name}.in", os.O_NONBLOCK | os.O_RDONLY)
        self.input_tail = ""
        self.content_head = (
            f"Content-type: multipart/x-mixed-replace;boundary=ZZ\r\nX-Urwid-ID: {urwid_id}\r\n\r\n\r\n--ZZ\r\n"
        )
        if self.update_method == "polling":
            self.content_head = f"Content-type: text/plain\r\nX-Urwid-ID: {urwid_id}\r\n\r\n\r\n"

        signal.signal(signal.SIGALRM, self._handle_alarm)
        signal.alarm(ALARM_DELAY)
        self._started = True

        return StoppingContext(self)

    def stop(self) -> None:
        """
        Restore settings and clean up.
        """
        if not self._started:
            return

        # XXX which exceptions does this actually raise? EnvironmentError?
        with suppress(Exception):
            self._close_connection()
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        with suppress(Exception):
            os.close(self.input_fd)
        self._cleanup_pipe()
        self._started = False

    def set_input_timeouts(self, *args: typing.Any) -> None:
        """Not supported for web display."""

    def _close_connection(self) -> None:
        if self.update_method == "polling child":
            self.server_socket.settimeout(0)
            sock, _addr = self.server_socket.accept()
            sock.sendall(b"Z")
            sock.close()

        if self.update_method == "multipart":
            sys.stdout.write("\r\nZ\r\n--ZZ--\r\n")
            sys.stdout.flush()

    def _cleanup_pipe(self, *args: typing.Any) -> None:
        if not self.pipe_name:
            return
        # XXX which exceptions does this actually raise? EnvironmentError?
        with suppress(Exception):
            os.remove(f"{self.pipe_name}.in")
            os.remove(f"{self.pipe_name}.update")

    def _set_screen_size(self, cols: int, rows: int) -> None:
        """Set the screen size (within max size)."""

        cols = min(cols, MAX_COLS)
        rows = min(rows, MAX_ROWS)
        self.screen_size = cols, rows

    def draw_screen(self, size: tuple[int, int], canvas: Canvas) -> None:
        """Send a screen update to the client.

        :raises ValueError: *canvas* does not have the number of rows given by *size*.
        """

        (cols, rows) = size
        encoding = get_encoding()

        if cols != self.last_screen_width:
            self.last_screen = {}

        sendq = [self.content_head]

        if self.update_method == "polling":
            send = sendq.append
        elif self.update_method == "polling child":
            signal.alarm(0)
            try:
                s, _addr = self.server_socket.accept()
            except socket.timeout:
                sys.exit(0)
            send = s.sendall  # type: ignore[assignment]  # use default flags
        else:
            signal.alarm(0)
            send = sendq.append
            send("\r\n")
            self.content_head = ""

        if canvas.rows() != rows:
            raise ValueError(rows)

        if canvas.cursor is not None:
            cx, cy = canvas.cursor
        else:
            cx = cy = None

        new_screen: dict[tuple[tuple[AttrSpec | str | None, str] | int | None, ...], list[int]] = {}

        y = -1
        for row in canvas.content():
            y += 1
            l_row = tuple((attr_, line.decode(encoding)) for attr_, _, line in row)

            line = []

            sig: tuple[tuple[AttrSpec | str | None, str] | int | None, ...] = l_row
            if y == cy:
                sig = (*sig, cx)
            new_screen.setdefault(sig, []).append(y)

            if (old_line_numbers := self.last_screen.get(sig, None)) is not None:
                if y in old_line_numbers:
                    old_line = y
                else:
                    old_line = old_line_numbers[0]
                send(f"<{old_line:d}\n")
                continue

            col = 0
            for a, run in l_row:
                t_run = run.translate(_trans_table)
                if isinstance(a, AttrSpec):
                    aspec = a
                else:
                    aspec = self._palette[a][self._colour_index]
                if y == cy and col <= cx:
                    run_width = calc_width(t_run, 0, len(t_run))
                    if col + run_width > cx:
                        line.append(code_span(t_run, aspec, cx - col))
                    else:
                        line.append(code_span(t_run, aspec))
                    col += run_width
                else:
                    line.append(code_span(t_run, aspec))

            send(f"{''.join(line)}\n")
        self.last_screen = new_screen
        self.last_screen_width = cols

        if self.update_method == "polling":
            sys.stdout.write("".join(sendq))
            sys.stdout.flush()
            sys.stdout.close()
            self._fork_child()
        elif self.update_method == "polling child":
            s.close()
        else:  # update_method == "multipart"
            send("\r\n--ZZ\r\n")
            sys.stdout.write("".join(sendq))
            sys.stdout.flush()

        signal.alarm(ALARM_DELAY)

    def clear(self) -> None:
        """
        Force the screen to be completely repainted on the next
        call to draw_screen().

        (does nothing for web_display)
        """

    def _fork_child(self) -> None:
        """
        Fork a child to run CGI disconnected for polling update method.
        Force parent process to exit.
        """
        daemonize(f"{self.pipe_name}.err")
        self.input_fd = os.open(f"{self.pipe_name}.in", os.O_NONBLOCK | os.O_RDONLY)
        self.update_method = "polling child"
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.bind(f"{self.pipe_name}.update")
        s.listen(1)
        s.settimeout(POLL_CONNECT)
        self.server_socket = s

    def _handle_alarm(self, sig: int, frame: FrameType | None) -> None:
        """
        Handle the periodic alarm that keeps the browser connection alive.

        :raises ValueError: the update method is neither multipart nor a polling child.
        """
        if self.update_method not in {"multipart", "polling child"}:
            raise ValueError(self.update_method)
        if self.update_method == "polling child":
            # send empty update
            try:
                s, _addr = self.server_socket.accept()
                s.close()
            except socket.timeout:
                sys.exit(0)
        else:
            # send empty update
            sys.stdout.write("\r\n\r\n--ZZ\r\n")
            sys.stdout.flush()
        signal.alarm(ALARM_DELAY)

    def get_cols_rows(self) -> tuple[int, int]:
        """Return the screen size."""
        return self.screen_size

    @typing.overload
    def get_input(self, raw_keys: Literal[False]) -> list[str]: ...

    @typing.overload
    def get_input(self, raw_keys: Literal[True]) -> tuple[list[str], list[int]]: ...

    def get_input(self, raw_keys: bool = False) -> list[str] | tuple[list[str], list[int]]:
        """Return pending input as a list."""
        pending_input = []
        resized = False
        with selectors.DefaultSelector() as selector:
            selector.register(self.input_fd, selectors.EVENT_READ)

            iready = [event.fd for event, _ in selector.select(0.5)]

        if not iready:
            if raw_keys:
                return [], []
            return []

        keydata = os.read(self.input_fd, MAX_READ).decode(get_encoding())
        os.close(self.input_fd)
        self.input_fd = os.open(f"{self.pipe_name}.in", os.O_NONBLOCK | os.O_RDONLY)
        # sys.stderr.write( repr((keydata,self.input_tail))+"\n" )
        keys = keydata.split("\n")
        keys[0] = self.input_tail + keys[0]
        self.input_tail = keys[-1]

        for k in keys[:-1]:
            if self._handle_resize_request(k):
                resized = True
            else:
                pending_input.append(k)
        if resized:
            pending_input.append("window resize")

        if raw_keys:
            return pending_input, []
        return pending_input


#: default RGB values substituted for a palette entry's 'default' foreground/background,
#: matching the black-on-light-gray page background declared in _web.css
_default_aspec = AttrSpec(_default_foreground, _default_background)
_d_fg_rgb = _default_aspec.get_rgb_values()[:3]
_d_bg_rgb = _default_aspec.get_rgb_values()[3:]

# the separator between a span's inline CSS and its text content in the wire format;
# safe because control characters in the text have already been replaced by _trans_table
_STYLE_SEP = "\x01"


@functools.cache
def _span_style(aspec: AttrSpec) -> tuple[str, str, str]:
    """Return the (foreground, background, extra CSS) for *aspec*, with standout applied."""
    fg_r, fg_g, fg_b, bg_r, bg_g, bg_b = aspec.get_rgb_values()
    if fg_r is None:
        fg_r, fg_g, fg_b = _d_fg_rgb
    if bg_r is None:
        bg_r, bg_g, bg_b = _d_bg_rgb
    fg = f"#{fg_r:02x}{fg_g:02x}{fg_b:02x}"
    bg = f"#{bg_r:02x}{bg_g:02x}{bg_b:02x}"
    if aspec.standout:
        fg, bg = bg, fg

    decoration = [name for name, on in (("underline", aspec.underline), ("line-through", aspec.strikethrough)) if on]

    extra = ""
    if decoration:
        extra += f";text-decoration:{' '.join(decoration)}"
    if aspec.bold:
        extra += ";font-weight:bold"
    if aspec.italics:
        extra += ";font-style:italic"
    if aspec.blink:
        extra += ";animation:urwid-blink 1s step-start infinite"
    if aspec.faint:
        extra += ";opacity:0.5"
    return fg, bg, extra


def code_span(s: str, aspec: AttrSpec, cursor: int = -1) -> str:
    fg, bg, extra = _span_style(aspec)

    def _piece(fg_: str, bg_: str, text: str) -> str:
        return f"color:{fg_};background-color:{bg_}{extra}{_STYLE_SEP}{text}\n"

    if cursor >= 0:
        c_off, _ign = calc_text_pos(s, 0, len(s), cursor)
        c2_off = move_next_char(s, c_off, len(s))

        return _piece(fg, bg, s[:c_off]) + _piece(bg, fg, s[c_off:c2_off]) + _piece(fg, bg, s[c2_off:])

    return _piece(fg, bg, s)


def is_web_request() -> bool:
    """
    Return True if this is a CGI web request.
    """
    return "REQUEST_METHOD" in os.environ


def _request_charset() -> str:
    content_type = Message()
    content_type["content-type"] = os.environ.get("CONTENT_TYPE", "")
    return content_type.get_content_charset() or "utf-8"


def handle_short_request() -> bool:
    """
    Handle short requests such as passing keystrokes to the application
    or sending the initial HTML page.  If returns True, then this
    function recognized and handled a short request, and the calling
    script should immediately exit.

    web_display.set_preferences(..) should be called before calling this
    function for the preferences to take effect
    """
    if not is_web_request():
        return False

    if os.environ["REQUEST_METHOD"] == "GET":
        # Initial request, send the HTML and javascript.
        sys.stdout.write("Content-type: text/html\r\n\r\n" + html.escape(_prefs.app_name).join(_html_page))
        return True

    if os.environ["REQUEST_METHOD"] != "POST":
        # Don't know what to do with head requests etc.
        return False

    if "HTTP_X_URWID_ID" not in os.environ:
        # If no urwid id, then the application should be started.
        return False

    urwid_id = os.environ["HTTP_X_URWID_ID"]
    if len(urwid_id) > _URWID_ID_MAX_LEN:
        # invalid. handle by ignoring
        # assert 0, "urwid id too long!"
        sys.stdout.write("Status: 414 URI Too Long\r\n\r\n")
        return True
    if any(c not in _URWID_ID_CHARS for c in urwid_id):
        # invalid. handle by ignoring
        # assert 0, "invalid chars in id!"
        sys.stdout.write("Status: 403 Forbidden\r\n\r\n")
        return True

    if os.environ.get("HTTP_X_URWID_METHOD", None) == "polling":
        # this is a screen update request
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.connect(os.path.join(_prefs.pipe_dir, f"urwid_{urwid_id}.update"))
                chunks = []
                while data := s.recv(BUF_SZ):
                    chunks.append(data)
        except OSError:
            sys.stdout.write("Status: 404 Not Found\r\n\r\n")
            return True

        try:
            decoded = b"".join(chunks).decode("utf-8")
        except UnicodeDecodeError:
            sys.stdout.write("Status: 502 Bad Gateway\r\n\r\n")
            return True

        sys.stdout.write(f"Content-type: text/plain; charset=utf-8\r\n\r\n{decoded}")
        return True

    # this is a keyboard input request
    try:
        fd = os.open((os.path.join(_prefs.pipe_dir, f"urwid_{urwid_id}.in")), os.O_WRONLY)
    except OSError:
        sys.stdout.write("Status: 404 Not Found\r\n\r\n")
        return True

    try:
        try:
            keydata = sys.stdin.read(MAX_READ)
            encoded_keydata = keydata.encode(_request_charset())
        except (LookupError, UnicodeError):
            sys.stdout.write("Status: 400 Bad Request\r\n\r\n")
            return True
        os.write(fd, encoded_keydata)
    finally:
        with suppress(OSError):
            os.close(fd)
    sys.stdout.write("Content-type: text/plain\r\n\r\n")

    return True


@dataclasses.dataclass
class _Preferences:
    app_name: str = "Unnamed Application"
    pipe_dir: str = TEMP_DIR
    allow_polling: bool = True
    max_clients: int = 20


_prefs = _Preferences()


def set_preferences(
    app_name: str,
    pipe_dir: str = TEMP_DIR,
    allow_polling: bool = True,
    max_clients: int = 20,
) -> None:
    """
    Set web_display preferences.

    :param app_name: application name to appear in html interface
    :param pipe_dir: directory for input pipes, daemon update sockets and daemon error logs
    :param allow_polling: allow creation of daemon processes for browsers without multipart support
    :param max_clients: maximum concurrent client connections. This pool is shared by all urwid applications using the
        same pipe_dir
    """
    _prefs.app_name = app_name
    _prefs.pipe_dir = pipe_dir
    _prefs.allow_polling = allow_polling
    _prefs.max_clients = max_clients


class ErrorLog:
    def __init__(self, errfile: str | pathlib.PurePath) -> None:
        self.errfile = errfile

    def write(self, err: str) -> None:
        with open(self.errfile, "a", encoding="utf-8") as f:
            f.write(err)


def daemonize(errfile: str) -> None:
    """
    Detach process and become a daemon.
    """
    if os.fork():
        os._exit(0)

    os.setsid()
    signal.signal(signal.SIGHUP, signal.SIG_IGN)
    os.umask(0)

    if os.fork():
        os._exit(0)

    os.chdir("/")
    for fd in range(20):
        with suppress(OSError):
            os.close(fd)

    sys.stdin = open("/dev/null", encoding="utf-8")  # noqa: SIM115  # pylint: disable=consider-using-with
    sys.stdout = open("/dev/null", "w", encoding="utf-8")  # noqa: SIM115  # pylint: disable=consider-using-with
    sys.stderr = ErrorLog(errfile)

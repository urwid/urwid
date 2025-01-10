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
import glob
import html
import os
import pathlib
import random
import selectors
import signal
import socket
import string
import sys
import tempfile
import typing
from contextlib import suppress

from urwid.str_util import calc_text_pos, calc_width, move_next_char
from urwid.util import StoppingContext, get_encoding

from .common import BaseScreen

if typing.TYPE_CHECKING:
    from typing_extensions import Literal

    from urwid import Canvas

TEMP_DIR = tempfile.gettempdir()
CURRENT_DIR = pathlib.Path(__file__).parent

_js_code = CURRENT_DIR.joinpath("_web.js").read_text("utf-8")

ALARM_DELAY = 60
POLL_CONNECT = 3
MAX_COLS = 200
MAX_ROWS = 100
MAX_READ = 4096
BUF_SZ = 16384

_code_colours = {
    "black": "0",
    "dark red": "1",
    "dark green": "2",
    "brown": "3",
    "dark blue": "4",
    "dark magenta": "5",
    "dark cyan": "6",
    "light gray": "7",
    "dark gray": "8",
    "light red": "9",
    "light green": "A",
    "yellow": "B",
    "light blue": "C",
    "light magenta": "D",
    "light cyan": "E",
    "white": "F",
}

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


class Screen(BaseScreen):
    def __init__(self) -> None:
        super().__init__()
        self.palette = {}
        self.has_color = True
        self._started = False

    @property
    def started(self) -> bool:
        return self._started

    def register_palette(self, palette) -> None:
        """Register a list of palette entries.

        palette -- list of (name, foreground, background) or
                   (name, same_as_other_name) palette entries.

        calls self.register_palette_entry for each item in l
        """

        for item in palette:
            if len(item) in {3, 4}:
                self.register_palette_entry(*item)
                continue
            if len(item) != 2:
                raise ValueError(f"Invalid register_palette usage: {item!r}")
            name, like_name = item
            if like_name not in self.palette:
                raise KeyError(f"palette entry '{like_name}' doesn't exist")
            self.palette[name] = self.palette[like_name]

    def register_palette_entry(
        self,
        name: str | None,
        foreground: str,
        background: str,
        mono: str | None = None,
        foreground_high: str | None = None,
        background_high: str | None = None,
    ) -> None:
        """Register a single palette entry.

        name -- new entry/attribute name
        foreground -- foreground colour
        background -- background colour
        mono -- monochrome terminal attribute

        See curses_display.register_palette_entry for more info.
        """
        if foreground == "default":
            foreground = "black"
        if background == "default":
            background = "light gray"
        self.palette[name] = (foreground, background, mono)

    def set_mouse_tracking(self, enable: bool = True) -> None:
        """Not yet implemented"""

    def tty_signal_keys(self, *args, **vargs):
        """Do nothing."""

    def start(self) -> StoppingContext:
        """
        This function reads the initial screen size, generates a
        unique id and handles cleanup when fn exits.

        web_display.set_preferences(..) must be called before calling
        this function for the preferences to take effect
        """
        if self._started:
            return StoppingContext(self)

        client_init = sys.stdin.read(50)
        if not client_init.startswith("window resize "):
            raise ValueError(client_init)
        _ignore1, _ignore2, x, y = client_init.split(" ", 3)
        x = int(x)
        y = int(y)
        self._set_screen_size(x, y)
        self.last_screen = {}
        self.last_screen_width = 0

        self.update_method = os.environ["HTTP_X_URWID_METHOD"]
        if self.update_method not in {"multipart", "polling"}:
            raise ValueError(self.update_method)

        if self.update_method == "polling" and not _prefs.allow_polling:
            sys.stdout.write("Status: 403 Forbidden\r\n\r\n")
            sys.exit(0)

        clients = glob.glob(os.path.join(_prefs.pipe_dir, "urwid*.in"))
        if len(clients) >= _prefs.max_clients:
            sys.stdout.write("Status: 503 Sever Busy\r\n\r\n")
            sys.exit(0)

        urwid_id = f"{random.randrange(10**9):09d}{random.randrange(10**9):09d}"  # noqa: S311
        self.pipe_name = os.path.join(_prefs.pipe_dir, f"urwid{urwid_id}")
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
        self._cleanup_pipe()
        self._started = False

    def set_input_timeouts(self, *args: typing.Any) -> None:
        pass

    def _close_connection(self) -> None:
        if self.update_method == "polling child":
            self.server_socket.settimeout(0)
            sock, _addr = self.server_socket.accept()
            sock.sendall(b"Z")
            sock.close()

        if self.update_method == "multipart":
            sys.stdout.write("\r\nZ\r\n--ZZ--\r\n")
            sys.stdout.flush()

    def _cleanup_pipe(self, *args) -> None:
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
        """Send a screen update to the client."""

        (cols, rows) = size

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
            send = s.sendall
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

        new_screen = {}

        y = -1
        for row in canvas.content():
            y += 1
            l_row = tuple((attr_, line.decode(get_encoding())) for attr_, _, line in row)

            line = []

            sig = l_row
            if y == cy:
                sig = (*sig, cx)
            new_screen[sig] = [*new_screen.get(sig, []), y]

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
                if a is None:
                    fg, bg, _mono = "black", "light gray", None
                else:
                    fg, bg, _mono = self.palette[a]
                if y == cy and col <= cx:
                    run_width = calc_width(t_run, 0, len(t_run))
                    if col + run_width > cx:
                        line.append(code_span(t_run, fg, bg, cx - col))
                    else:
                        line.append(code_span(t_run, fg, bg))
                    col += run_width
                else:
                    line.append(code_span(t_run, fg, bg))

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

    def _handle_alarm(self, sig, frame) -> None:
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
            if k.startswith("window resize "):
                _ign1, _ign2, x, y = k.split(" ", 3)
                x = int(x)
                y = int(y)
                self._set_screen_size(x, y)
                resized = True
            else:
                pending_input.append(k)
        if resized:
            pending_input.append("window resize")

        if raw_keys:
            return pending_input, []
        return pending_input


def code_span(s, fg, bg, cursor=-1) -> str:
    code_fg = _code_colours[fg]
    code_bg = _code_colours[bg]

    if cursor >= 0:
        c_off, _ign = calc_text_pos(s, 0, len(s), cursor)
        c2_off = move_next_char(s, c_off, len(s))

        return (
            code_fg
            + code_bg
            + s[:c_off]
            + "\n"
            + code_bg
            + code_fg
            + s[c_off:c2_off]
            + "\n"
            + code_fg
            + code_bg
            + s[c2_off:]
            + "\n"
        )

    return f"{code_fg + code_bg + s}\n"


def is_web_request() -> bool:
    """
    Return True if this is a CGI web request.
    """
    return "REQUEST_METHOD" in os.environ


def handle_short_request() -> bool:
    """
    Handle short requests such as passing keystrokes to the application
    or sending the initial html page.  If returns True, then this
    function recognised and handled a short request, and the calling
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
    if len(urwid_id) > 20:
        # invalid. handle by ignoring
        # assert 0, "urwid id too long!"
        sys.stdout.write("Status: 414 URI Too Long\r\n\r\n")
        return True
    for c in urwid_id:
        if c not in string.digits:
            # invald. handle by ignoring
            # assert 0, "invalid chars in id!"
            sys.stdout.write("Status: 403 Forbidden\r\n\r\n")
            return True

    if os.environ.get("HTTP_X_URWID_METHOD", None) == "polling":
        # this is a screen update request
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            s.connect(os.path.join(_prefs.pipe_dir, f"urwid{urwid_id}.update"))
            data = f"Content-type: text/plain\r\n\r\n{s.recv(BUF_SZ)}"
            while data:
                sys.stdout.write(data)
                data = s.recv(BUF_SZ)
        except OSError:
            sys.stdout.write("Status: 404 Not Found\r\n\r\n")
            return True
        return True

    # this is a keyboard input request
    try:
        fd = os.open((os.path.join(_prefs.pipe_dir, f"urwid{urwid_id}.in")), os.O_WRONLY)
    except OSError:
        sys.stdout.write("Status: 404 Not Found\r\n\r\n")
        return True

    # FIXME: use the correct encoding based on the request
    keydata = sys.stdin.read(MAX_READ)
    os.write(fd, keydata.encode("ascii"))
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

    app_name -- application name to appear in html interface
    pipe_dir -- directory for input pipes, daemon update sockets
                and daemon error logs
    allow_polling -- allow creation of daemon processes for
                     browsers without multipart support
    max_clients -- maximum concurrent client connections. This
               pool is shared by all urwid applications
               using the same pipe_dir
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
    for fd in range(0, 20):
        with suppress(OSError):
            os.close(fd)

    sys.stdin = open("/dev/null", encoding="utf-8")  # noqa: SIM115  # pylint: disable=consider-using-with
    sys.stdout = open("/dev/null", "w", encoding="utf-8")  # noqa: SIM115  # pylint: disable=consider-using-with
    sys.stderr = ErrorLog(errfile)

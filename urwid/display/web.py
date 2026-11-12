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


"""Urwid web application display module."""

from __future__ import annotations

import codecs
import dataclasses
import glob
import hashlib
import html
import os
import pathlib
import secrets
import selectors
import signal
import socket
import stat
import string
import sys
import tempfile
import typing
from contextlib import suppress
from email.message import Message

from urwid.util import StoppingContext

from ._web_common import (  # pylint: disable=unused-import  # code_span is a public name of this module
    MAX_COLS,
    MAX_ROWS,
    BrowserScreen,
    code_span,  # noqa: F401  # a public name of this module
    is_key_name,
)

if typing.TYPE_CHECKING:
    from types import FrameType
    from typing import Literal

    from urwid.canvas import Canvas

TEMP_DIR = tempfile.gettempdir()
CURRENT_DIR = pathlib.Path(__file__).parent

# the page script: the shared row rendering and key names, then the CGI transport
_js_code = CURRENT_DIR.joinpath("_web_common.js").read_text("utf-8") + CURRENT_DIR.joinpath("_web.js").read_text(
    "utf-8"
)

ALARM_DELAY = 60
POLL_CONNECT = 3
MAX_READ = 4096
#: the longest keyboard input line, in characters
MAX_LINE_LENGTH: typing.Final = 256
# encoding of the keyboard input pipe, written by handle_short_request() and read by Screen.get_input()
_PIPE_ENCODING: typing.Final = "utf-8"
BUF_SZ = 16384

# Characters that may appear in an id produced by secrets.token_urlsafe():
# the URL-safe base64 alphabet. Used to reject malformed client-supplied ids before any session file lookup.
_URWID_ID_CHARS = frozenset(string.ascii_letters + string.digits + "-_")
_URWID_ID_MAX_LEN = 43  # len(secrets.token_urlsafe(32)); generous upper bound

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


class Screen(BrowserScreen):
    """Screen backend that renders to a browser client over the web server's polling/streaming connection."""

    def __init__(self) -> None:
        """Initialize an unstarted screen defaulting to true color."""
        super().__init__()
        self._started = False
        self.update_method = ""
        self.pipe_name = ""
        self.input_fd: int | None = None
        self.input_tail = ""
        # the rest of an over-long input line is still to be dropped, up to and including its newline
        self._dropping_line = False
        # keeps a character split between two reads of the input pipe until its last byte arrives
        self._input_decoder = codecs.getincrementaldecoder(_PIPE_ENCODING)("replace")
        self.content_head = ""
        self.screen_size: tuple[int, int] | None = None
        self.server_socket: socket.socket | None = None

    @property
    def started(self) -> bool:
        """Return whether this screen has been started."""
        return self._started

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
        """Not yet implemented."""

    def tty_signal_keys(self, *args: typing.Any, **vargs: typing.Any) -> None:
        """Do nothing."""

    def start(self, *args: typing.Any, **kwargs: typing.Any) -> StoppingContext:
        """Read the initial screen size, generate a unique id and handle cleanup when fn exits.

        web_display.set_preferences(..) must be called before calling this function for the preferences to take effect

        :raises RuntimeError: the ``HTTP_X_URWID_METHOD`` environment variable is not set.
        :raises PermissionError: the session directory is not private, see :func:`_session_dir`.
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

        self.last_screen = {}
        self.last_screen_width = 0

        urwid_id = secrets.token_urlsafe(16)
        pipe_name = _session_path(urwid_id)
        clients = glob.glob("*.in", root_dir=os.path.dirname(pipe_name))
        if len(clients) >= _prefs.max_clients:
            sys.stdout.write("Status: 503 Sever Busy\r\n\r\n")
            sys.exit(0)

        self.pipe_name = pipe_name
        os.mkfifo(f"{self.pipe_name}.in", 0o600)
        signal.signal(signal.SIGTERM, self._cleanup_pipe)

        self.input_fd = os.open(f"{self.pipe_name}.in", os.O_NONBLOCK | os.O_RDONLY)
        self.input_tail = ""
        self._dropping_line = False
        self._input_decoder.reset()
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
        """Restore settings and clean up."""
        if not self._started:
            return

        # XXX which exceptions does this actually raise? EnvironmentError?
        with suppress(Exception):
            self._close_connection()
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        if self.input_fd is not None:
            with suppress(Exception):
                os.close(self.input_fd)
        self._cleanup_pipe()
        self._started = False

    def set_input_timeouts(self, *args: typing.Any) -> None:
        """Not supported for web display."""

    def _close_connection(self) -> None:
        if self.update_method == "polling child" and self.server_socket is not None:
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
        sendq: list[str] = [self.content_head]

        if self.update_method == "polling child":
            signal.alarm(0)
            try:
                s, _addr = typing.cast("socket.socket", self.server_socket).accept()
            except TimeoutError:
                sys.exit(0)
            sendq = []
        elif self.update_method != "polling":
            signal.alarm(0)
            sendq.append("\r\n")
            self.content_head = ""

        sendq.extend(self._render_rows(size, canvas))

        if self.update_method == "polling":
            sys.stdout.write("".join(sendq))
            sys.stdout.flush()
            sys.stdout.close()
            self._fork_child()
        elif self.update_method == "polling child":
            s.sendall("".join(sendq).encode("utf-8"))  # handle_short_request() decodes UTF-8
            s.close()
        else:  # update_method == "multipart"
            sendq.append("\r\n--ZZ\r\n")
            sys.stdout.write("".join(sendq))
            sys.stdout.flush()

        signal.alarm(ALARM_DELAY)

    def clear(self) -> None:
        """Force the screen to be completely repainted on the next call to draw_screen().

        (does nothing for web_display)
        """

    def _fork_child(self) -> None:
        """Fork a child to run CGI disconnected for polling update method.

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
                s, _addr = typing.cast("socket.socket", self.server_socket).accept()
                s.close()
            except TimeoutError:
                sys.exit(0)
        else:
            # send empty update
            sys.stdout.write("\r\n\r\n--ZZ\r\n")
            sys.stdout.flush()
        signal.alarm(ALARM_DELAY)

    def get_cols_rows(self) -> tuple[int, int]:
        """Return the screen size."""
        return typing.cast("tuple[int, int]", self.screen_size)

    @typing.overload
    def get_input(self, raw_keys: Literal[False]) -> list[str]: ...

    @typing.overload
    def get_input(self, raw_keys: Literal[True]) -> tuple[list[str], list[int]]: ...

    def get_input(self, raw_keys: bool = False) -> list[str] | tuple[list[str], list[int]]:
        """Return pending input as a list.

        An input line longer than :data:`MAX_LINE_LENGTH` is dropped whole, up to and including its newline.
        A line that is neither a key name the page script sends nor a valid resize request is dropped too.
        """
        pending_input = []
        resized = False
        input_fd = typing.cast("int", self.input_fd)
        with selectors.DefaultSelector() as selector:
            selector.register(input_fd, selectors.EVENT_READ)

            iready = [event.fd for event, _ in selector.select(0.5)]

        if not iready:
            if raw_keys:
                return [], []
            return []

        keydata = self._input_decoder.decode(os.read(input_fd, MAX_READ))
        os.close(input_fd)
        self.input_fd = os.open(f"{self.pipe_name}.in", os.O_NONBLOCK | os.O_RDONLY)
        lines = (self.input_tail + keydata).split("\n")
        if self._dropping_line:
            # input_tail is empty here, so the first piece is the rest of the over-long line
            del lines[0]
            self._dropping_line = not lines
        self.input_tail = lines.pop() if lines else ""
        if len(self.input_tail) > MAX_LINE_LENGTH:
            self.logger.debug("Dropped an input line longer than %d characters", MAX_LINE_LENGTH)
            self.input_tail = ""
            self._dropping_line = True

        not_keys = 0
        for k in lines:
            if len(k) > MAX_LINE_LENGTH:
                self.logger.debug("Dropped an input line of %d characters", len(k))
            elif self._handle_resize_request(k):
                resized = True
            elif is_key_name(k):
                pending_input.append(k)
            else:
                not_keys += 1
        if not_keys:
            self.logger.debug("Dropped %d input lines that are not key names", not_keys)
        if resized:
            pending_input.append("window resize")

        if raw_keys:
            return pending_input, []
        return pending_input


def is_web_request() -> bool:
    """Return True if this is a CGI web request."""
    return "REQUEST_METHOD" in os.environ


def _request_charset() -> str:
    content_type = Message()
    content_type["content-type"] = os.environ.get("CONTENT_TYPE", "")
    return content_type.get_content_charset() or "utf-8"


def _session_dir() -> str:
    """Return the private directory for the session files of the effective user.

    The directory is ``urwid-web-<uid>`` under the configured ``pipe_dir``, created when missing.
    It keeps the session files of one user out of reach of every other local user.

    :raises PermissionError: the path is not a directory owned by the effective user,
        or the group or other users have any access to it.
    """
    uid = os.geteuid()
    path = os.path.join(_prefs.pipe_dir, f"urwid-web-{uid}")
    with suppress(FileExistsError):
        pathlib.Path(path).mkdir(mode=0o700)
    # lstat: a symbolic link planted at the path is refused rather than followed
    st = os.lstat(path)
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != uid or stat.S_IMODE(st.st_mode) & 0o077:
        raise PermissionError(f"{path!r} must be a directory owned by uid {uid} with no group or other access")
    return path


def _session_path(urwid_id: str) -> str:
    """Return the path prefix of the input pipe, update socket and error log of a session.

    The file name is a hash of the session id, so a directory listing does not reveal the id.

    :raises PermissionError: the session directory is not private, see :func:`_session_dir`.
    """
    # 128 bits of SHA-256: hashlib.blake2b with a custom digest size is not available on GraalPy
    digest = hashlib.sha256(urwid_id.encode("ascii")).hexdigest()[:32]
    return os.path.join(_session_dir(), digest)


def handle_short_request() -> bool:
    """Handle short requests such as passing keystrokes to the application or sending the initial HTML page.

    If returns True, then this function recognized and handled a short request, and the calling
    script should immediately exit.

    web_display.set_preferences(..) should be called before calling this
    function for the preferences to take effect.

    :raises PermissionError: the session directory is not private, see :func:`_session_dir`.
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

    pipe_name = _session_path(urwid_id)

    if os.environ.get("HTTP_X_URWID_METHOD", None) == "polling":
        # this is a screen update request
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.connect(f"{pipe_name}.update")
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
        fd = os.open(f"{pipe_name}.in", os.O_WRONLY)
    except OSError:
        sys.stdout.write("Status: 404 Not Found\r\n\r\n")
        return True

    try:
        try:
            keydata = sys.stdin.buffer.read(MAX_READ)
            encoded_keydata = keydata.decode(_request_charset()).encode(_PIPE_ENCODING)
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
    :param pipe_dir: parent of the private per-user directory ``urwid-web-<uid>``
        that holds the input pipes, daemon update sockets and daemon error logs.
        Other users must not be able to rename its entries: use a private directory or a sticky one such as ``/tmp``.
    :param allow_polling: allow creation of daemon processes for browsers without multipart support
    :param max_clients: maximum concurrent client connections. This pool is shared by all urwid applications that
        run as the same user with the same pipe_dir
    """
    _prefs.app_name = app_name
    _prefs.pipe_dir = pipe_dir
    _prefs.allow_polling = allow_polling
    _prefs.max_clients = max_clients


class ErrorLog:
    """File-like object that appends written text to the given error log file."""

    def __init__(self, errfile: str | pathlib.PurePath) -> None:
        """Wrap the error log file at `errfile`."""
        self.errfile = errfile

    def write(self, err: str) -> None:
        """Append `err` to the error log file."""
        with open(self.errfile, "a", encoding="utf-8") as f:
            f.write(err)


def daemonize(errfile: str) -> None:
    """Detach process and become a daemon."""
    if os.fork():
        os._exit(0)

    os.setsid()
    signal.signal(signal.SIGHUP, signal.SIG_IGN)
    # the daemon creates the polling update socket and the error log: keep them private to the owner
    os.umask(0o077)

    if os.fork():
        os._exit(0)

    os.chdir("/")
    for fd in range(20):
        with suppress(OSError):
            os.close(fd)

    sys.stdin = open("/dev/null", encoding="utf-8")  # noqa: SIM115  # pylint: disable=consider-using-with
    sys.stdout = open("/dev/null", "w", encoding="utf-8")  # noqa: SIM115  # pylint: disable=consider-using-with
    sys.stderr = ErrorLog(errfile)

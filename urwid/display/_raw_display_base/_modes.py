# Urwid raw display module
#    Copyright (C) 2004-2009  Ian Ward
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


"""Mode negotiation, terminal reports, the window title and the clipboard of the raw display :class:`Screen`."""

from __future__ import annotations

import base64
import re
import typing

from urwid import util
from urwid.display import escape
from urwid.display._raw_display_base._attributes import _AttributesScreen
from urwid.display._raw_display_base._base import _ColorProbe
from urwid.display._raw_display_base._detection import (
    _PROBE_RGB,
    _QUERIED_CAPABILITIES,
    _colors_from_rendition,
    _colors_from_version,
    _is_linux_console,
    _properties_from_capabilities,
    _rejects_osc,
    _underline_styles_from_version,
)
from urwid.display.common import (
    AttrSpec,
)

if typing.TYPE_CHECKING:
    from collections.abc import Mapping

    _MouseInput = tuple[str, int, int, int]
    _CursorPosition = tuple[typing.Literal["cursor position"], int, int]
    _PrivateModeReport = tuple[typing.Literal["private mode report"], str, int]
    _KeyboardProtocolReport = tuple[typing.Literal["keyboard protocol report"], int]
    _ModifyKeysReport = tuple[typing.Literal["modify keys report"], int, int | None]
    _DeviceAttributesReport = tuple[typing.Literal["device attributes"], tuple[int, ...]]
    _TerminalVersionReport = tuple[typing.Literal["terminal version"], str]
    _TerminalCapabilitiesReport = tuple[typing.Literal["terminal capabilities"], tuple[tuple[str, str | None], ...]]
    _DefaultColorReport = tuple[typing.Literal["default color"], int, str]
    _SettingReport = tuple[typing.Literal["setting report"], bool, str]
    _TerminalReport = (
        _PrivateModeReport
        | _KeyboardProtocolReport
        | _ModifyKeysReport
        | _DeviceAttributesReport
        | _TerminalVersionReport
        | _TerminalCapabilitiesReport
        | _DefaultColorReport
        | _SettingReport
    )
    _WindowSizeReport = tuple[typing.Literal["window size report"], int, int]
    _DecodedInput = list[str | _MouseInput | _CursorPosition]


# the DECRPM states of a mode that is set: set (1) and permanently set (3)
_DECRQM_SET_VALUES: typing.Final = frozenset((escape.ModeReportState.SET, escape.ModeReportState.PERMANENTLY_SET))
# the background the rendition probe sets, in the colon form a terminal that does not know ignores as a whole
_PROBE_BACKGROUND: typing.Final = f"{escape.CSI}48:2::{':'.join(map(str, _PROBE_RGB))}m"


# C0 and C1 control characters and DEL: in a window title, BEL, ESC or ST would end the title and start a sequence
_TITLE_CONTROLS = re.compile("[\x00-\x1f\x7f-\x9f]")
# bytes a terminal reading 8-bit controls takes as C1 controls, such as 0x9c (ST) and 0x9b (CSI)
_C1_BYTES = re.compile(rb"[\x80-\x9f]")


class _ModesScreen(_AttributesScreen):  # pylint: disable=abstract-method  # a platform screen completes it
    """Negotiate the modes of the terminal of a raw display :class:`Screen`, and set its title and clipboard."""

    __slots__ = ()

    def set_mouse_tracking(self, enable: bool = True) -> None:
        """
        Enable (or disable) mouse tracking.

        After calling this function get_input will include mouse click events along with keystrokes.
        """
        if enable == self._mouse_tracking_enabled:
            return

        self._mouse_tracking(enable)

    def _mouse_tracking(self, enable: bool) -> None:
        """Write the mouse tracking escape sequences and track `_mouse_tracking_enabled`.

        A no-op when *enable* is True but mouse reporting was detected unsupported -- there is
        nothing to enable, and the tracked state has to agree.
        """
        if enable and self.modes.mouse_reporting is False:
            self._mouse_tracking_enabled = False
            return
        self.write(escape.MOUSE_TRACKING_ON if enable else escape.MOUSE_TRACKING_OFF)
        self._mouse_tracking_enabled = enable

    # TermModes field -> the sequence that enables it, once confirmed supported from a sentinel.
    _PRIVATE_MODE_ENABLE_SEQUENCE: typing.ClassVar[Mapping[str, str]] = {
        "bracketed_paste": escape.PrivateMode.BRACKETED_PASTE.enable_seq,
        "focus_reporting": escape.PrivateMode.FOCUS_REPORTING.enable_seq,
    }

    def _detect_terminal_modes(self) -> None:
        """Send DECRQM queries for the private modes still at their sentinel; does not wait for a reply.

        Replies are recognized later, during normal `parse_input()`
        (see `escape.KeyqueueTrie.read_private_mode_report`, `_apply_terminal_reports()`).
        With ``extended_keys``, the kitty keyboard protocol and modifyOtherKeys are queried as well, once.
        Until the terminal has answered them, the terminal's version (XTVERSION), its colour and underline style
        capabilities (XTGETTCAP) and its default foreground and background colours (OSC 10 and OSC 11) are queried as
        well, unless the application set both properties itself or the terminal is the Linux console.

        Each call starts a run of the screen: the rendition probe may be sent again, unless an earlier reply to it
        confirmed the colour count, and the rendition and the alternate screen report of an earlier run are forgotten.
        """
        self._color_probe = _ColorProbe.FINISHED if self._colors_confirmed else _ColorProbe.UNSENT
        self._alternate_buffer_reported = False
        self._rendition = None
        if not self._is_real_terminal():
            return

        modes = [
            escape.PrivateMode.SYNCHRONIZED_OUTPUT,
            escape.PrivateMode.GRAPHEME_CLUSTERING,
            escape.PrivateMode.ALTERNATE_SCREEN_BUFFER,
            escape.PrivateMode.MOUSE_REPORTING,
            escape.PrivateMode.MOUSE_SGR_MODE,
        ]
        if self.modes.bracketed_paste is None:
            modes.append(escape.PrivateMode.BRACKETED_PASTE)
        if self.modes.focus_reporting is None:
            modes.append(escape.PrivateMode.FOCUS_REPORTING)
        if self.modes.in_band_resize is None:
            modes.append(escape.PrivateMode.IN_BAND_RESIZE)
        if self.modes.alternate_scroll is not None and self._alternate_scroll_reported is None:
            modes.append(escape.PrivateMode.ALTERNATE_SCROLL)

        # a late reply to a query of an earlier start describes the same terminal, so it may answer the new query
        self._mode_queries_pending = set(modes)
        queries = "".join(mode.query for mode in modes)
        # A terminal ignores a query it does not know, and answers Primary DA in the order it reads the queries,
        # so a query that has no reply by the time the Primary DA reply arrives is one the terminal does not answer.
        ends_with_device_attributes = False
        if self.extended_keys and self.modes.kitty_keyboard is None and not self._keyboard_query_pending:
            queries += escape.KITTY_KEYBOARD_QUERY + escape.MODIFY_OTHER_KEYS_QUERY
            self._keyboard_query_pending = True
            ends_with_device_attributes = True
        # the Linux console answers neither query, and nothing it draws depends on them
        if (
            not (self._capabilities_answered or self._capability_query_pending)
            and not self._properties_set.issuperset(("colors", "underline_styles"))
            and not _is_linux_console(self.term)
        ):
            queries += escape.REPORT_DEFAULT_COLORS + escape.REPORT_TERMINAL_VERSION
            queries += "".join(escape.request_capability(name) for name in _QUERIED_CAPABILITIES)
            self._capability_query_pending = True
            ends_with_device_attributes = True
        if ends_with_device_attributes:
            queries += escape.REPORT_DEVICE_ATTRIBUTES
        self.write(queries)
        self.flush()

    def _write_alternate_scroll(self, *, restore: bool) -> None:
        """Set the alternate scroll mode the screen asked for, or with *restore* the state the terminal reported.

        Nothing is written when the screen leaves the mode to the terminal,
        and nothing is set back when the screen did not set the mode, such as after a start that failed before it,
        or when the terminal reported no state, also when its reply was not read yet: the mode then stays as the screen
        set it, rather than a guess replacing the user's own setting.
        The caller flushes the output.
        """
        if self.modes.alternate_scroll is None or (restore and not self._alternate_scroll_written):
            return
        self._alternate_scroll_written = not restore
        if restore and self._alternate_scroll_reported is None:
            return
        enable = self._alternate_scroll_reported if restore else self.modes.alternate_scroll
        mode = escape.PrivateMode.ALTERNATE_SCROLL
        self.write(mode.enable_seq if enable else mode.disable_seq)

    def _set_in_band_resize(self, enable: bool) -> None:
        """Switch the terminal's in-band resize notifications (DEC private mode 2048) on or off.

        `_in_band_resize` follows the mode, so the reports count exactly while this screen has it on.
        The caller flushes the output.
        """
        mode = escape.PrivateMode.IN_BAND_RESIZE
        # before the write, which can fail on a terminal that hung up, so a stop still counts no report after it
        self._in_band_resize = enable
        self.write(mode.enable_seq if enable else mode.disable_seq)

    def _cols_rows_before_report(self) -> tuple[int, int] | None:
        """Return the size a window size report is compared with, to tell whether it changes the size.

        It is the size the application last read, rather than the system's,
        which the terminal set before it sent the report.

        :returns: the size, or None when none is known yet, so that any report changes it.
        """
        return self._last_cols_rows

    def _apply_window_size_reports(
        self,
        decoded_codes: list[str | _MouseInput | _CursorPosition | _WindowSizeReport],
    ) -> _DecodedInput:
        """Replace the window size reports among *decoded_codes* with ``"window resize"`` at their place among the keys.

        A report counts only on a screen whose input carries such reports, see `_in_band_resize`.
        Elsewhere it is dropped, so input that only looks like one cannot cause a redraw.
        A report that counts:

        - becomes the size `get_cols_rows()` returns;
        - is a resize only when its size differs from the one the application last read,
          so the report a terminal sends when the mode is turned on, or after a ``SIGWINCH`` already reported,
          does not redraw the screen again;
        - is merged with an adjacent resize.

        A ``SIGWINCH`` still pending is reported on its own:
        it can come from a later change that sends no report, such as a session attached to another terminal.
        """
        logger = self.logger.getChild("terminal_reports")
        filtered: _DecodedInput = []
        for item in decoded_codes:
            match item:
                case ("window size report", int() as cols, int() as rows) if self._in_band_resize:
                    resized = self._cols_rows_before_report() != (cols, rows)
                    self._reported_cols_rows = cols, rows
                    if not resized:
                        continue
                    self.screen_buf = None
                    # adjacent resizes are one, as the resize flag merges them, so get_input can throttle them
                    if filtered[-1:] != ["window resize"]:
                        filtered.append("window resize")
                case ("window size report", *_):
                    logger.debug(f"Dropped a window size report this screen did not send: {item!r}")
                case _:
                    filtered.append(item)
        return filtered

    def _apply_terminal_reports(
        self,
        decoded_codes: list[str | _MouseInput | _CursorPosition | _TerminalReport | _WindowSizeReport],
    ) -> list[str | _MouseInput | _CursorPosition | _WindowSizeReport]:
        """Apply the query replies among *decoded_codes* to the modes and terminal properties, and strip them out.

        A reply counts only as the answer to a query urwid sent and has no answer for yet.
        Any other reply is dropped without effect, so input that only looks like a reply cannot change the modes.

        - A private mode report counts once for each mode queried.
        - A keyboard protocol reply counts between the keyboard protocol queries and the Primary DA reply sent
          after them.
        - A terminal version or capabilities reply counts the same way after the capability queries.
          It only raises the colour count and turns the underline styles on, see `_raise_terminal_properties()`.
        - A default colour reply counts the same way, and sets `terminal_default_colors`.
        - A DECRPSS reply counts while the rendition probe waits for its Primary DA reply,
          and sets the colour count it confirms.

        The rendition probe is sent once the whole of *decoded_codes* is applied, when it can be, see
        `_send_color_probe()`.
        """
        logger = self.logger.getChild("terminal_reports")
        filtered: list[str | _MouseInput | _CursorPosition | _WindowSizeReport] = []
        reports: list[tuple[str, int]] = []
        for item in decoded_codes:
            match item:
                case ("private mode report", escape.PrivateMode.ALTERNATE_SCROLL, int() as value) if (
                    escape.PrivateMode.ALTERNATE_SCROLL in self._mode_queries_pending
                ):
                    self._mode_queries_pending.discard(escape.PrivateMode.ALTERNATE_SCROLL)
                    # 0, not recognised, leaves nothing to set back
                    if value in escape.DECRQM_RECOGNIZED_VALUES:
                        self._alternate_scroll_reported = value in _DECRQM_SET_VALUES
                case ("private mode report", str() as mode, int() as value) if mode in self._mode_queries_pending:
                    self._mode_queries_pending.discard(mode)
                    reports.append((mode, value))
                    if mode == escape.PrivateMode.ALTERNATE_SCREEN_BUFFER:
                        self._alternate_buffer_reported = value in _DECRQM_SET_VALUES
                case ("private mode report", *_):
                    logger.debug(f"Dropped a reply to a query urwid has no answer pending for: {item!r}")
                case ("keyboard protocol report" | "modify keys report", *_) if not self._keyboard_query_pending:
                    logger.debug(f"Dropped a reply to a query urwid has no answer pending for: {item!r}")
                case ("terminal version" | "terminal capabilities" | "default color", *_) if (
                    not self._capability_query_pending
                ):
                    logger.debug(f"Dropped a reply to a query urwid has no answer pending for: {item!r}")
                case ("device attributes", *_) if not (
                    self._keyboard_query_pending
                    or self._capability_query_pending
                    or self._color_probe is _ColorProbe.PENDING
                ):
                    logger.debug(f"Dropped a reply to a query urwid has no answer pending for: {item!r}")
                case ("setting report", *_) if self._color_probe is not _ColorProbe.PENDING:
                    logger.debug(f"Dropped a reply to a query urwid has no answer pending for: {item!r}")
                case ("setting report", bool() as valid, str() as setting):
                    if valid and (colors := _colors_from_rendition(setting)) is not None:
                        self._raise_terminal_properties(colors, False, confirmed=True)
                case ("terminal version", str() as version):
                    self._raise_terminal_properties(
                        _colors_from_version(version),
                        _underline_styles_from_version(version),
                    )
                case ("terminal capabilities", capabilities):
                    self._raise_terminal_properties(*_properties_from_capabilities(capabilities))
                case ("default color", number, color):
                    self._terminal_default_colors[number] = color
                case ("keyboard protocol report", _flags):
                    self.modes.kitty_keyboard = True
                case ("modify keys report", escape.MODIFY_OTHER_KEYS_RESOURCE, value):
                    self.modes.modify_other_keys = True
                    self._modify_other_keys_reported = value
                case ("modify keys report", *_):
                    pass  # another key modifier resource, which urwid did not query
                case ("device attributes", _attributes):
                    # the Primary DA reply that ends the answers to the queries sent before it;
                    # the probe is sent after the startup reply was read, so a reply with no startup query pending is
                    # the probe's own
                    if not (self._capability_query_pending or self._keyboard_query_pending):
                        self._color_probe = _ColorProbe.FINISHED
                    if self._capability_query_pending:
                        self._capability_query_pending = False
                        self._capabilities_answered = True
                    if self._keyboard_query_pending:
                        self._keyboard_query_pending = False
                        self.modes.kitty_keyboard = bool(self.modes.kitty_keyboard)
                        self.modes.modify_other_keys = bool(self.modes.modify_other_keys)
                        self._enable_keyboard_protocol()
                case _:
                    filtered.append(item)

        if reports:
            newly_supported = self.modes.set_from_codes(*reports)
            enable = [code for field in newly_supported if (code := self._PRIVATE_MODE_ENABLE_SEQUENCE.get(field, ""))]
            # a stopped screen turns the mode on at its next start, from self.modes
            enable_in_band_resize = "in_band_resize" in newly_supported and self._started
            if enable:
                self.write("".join(enable))
            if enable_in_band_resize:
                self._set_in_band_resize(True)
            if enable or enable_in_band_resize:
                self.flush()

        self._send_color_probe()
        return filtered

    def _send_color_probe(self) -> None:
        """Ask the terminal how it stores a 24-bit background, once per run, when nothing else decides the colours.

        The probe sets a background, asks for the rendition with DECRQSS and for Primary DA, and then writes the SGR
        sequence the last frame left the terminal in, so the terminal is back in the rendition it was in.
        It is sent only when all of these hold:

        - it was not sent in this run, and no reply to it confirmed the colour count before;
        - the terminal reported, in this run, that the alternate screen the screen switched to is set,
          so a terminal that ignores the switch does not get the probe on its normal screen;
        - neither the application nor the environment decided the colour count;
        - the Primary DA replies of the startup queries were read, so the next one is the probe's;
        - the rendition a frame left is known;
        - the terminal is not the Linux console, which is never queried.

        :raises OSError: the terminal could not be written to; the probe is not sent again in this run.
        """
        if self._color_probe is not _ColorProbe.UNSENT or self._rendition is None or _is_linux_console(self.term):
            return
        if not (self._alternate_buffer_reported and self._alternate_buffer and self._started):
            return
        colors_decided = "colors" in self._properties_set or self._colors_from_environment
        if colors_decided or self._capability_query_pending or self._keyboard_query_pending:
            return
        # before the write: a write that fails part way may still have sent it
        self._color_probe = _ColorProbe.PENDING
        self.write(
            f"{_PROBE_BACKGROUND}{escape.REQUEST_RENDITION}{escape.CSI}49m"
            f"{escape.REPORT_DEVICE_ATTRIBUTES}{self._rendition}"
        )
        self.flush()

    def _enable_keyboard_protocol(self) -> None:
        """Turn on the keyboard protocol the terminal answered for, preferring kitty's to modifyOtherKeys.

        Only for ``extended_keys``, and once per start of the screen: the kitty flags are pushed on the stack of the
        screen in use, so they are popped before the alternate screen is left (see `_disable_keyboard_protocol()`).
        """
        if not self.extended_keys or not self._started or self._keyboard_protocol_enabled is not None:
            return
        if self.modes.kitty_keyboard:
            self.write(escape.KITTY_KEYBOARD_PUSH)
            self._keyboard_protocol_enabled = "kitty"
        elif self.modes.modify_other_keys:
            self.write(escape.MODIFY_OTHER_KEYS_ON)
            self._keyboard_protocol_enabled = "modify other keys"
        else:
            return
        self.flush()

    def _disable_keyboard_protocol(self) -> None:
        """Restore the keyboard protocol state `_enable_keyboard_protocol()` changed, as the screen stops.

        Replies not read by then can be lost, as a POSIX stop discards the pending input, so queries still waiting for
        them, the capability queries included, are sent again on the next start.
        The rendition probe ends with the run, and a reply to it that arrives later is dropped.
        """
        if self._keyboard_protocol_enabled == "kitty":
            self.write(escape.KITTY_KEYBOARD_POP)
        elif self._keyboard_protocol_enabled == "modify other keys":
            self.write(escape.set_modify_other_keys(self._modify_other_keys_reported))
        self._keyboard_protocol_enabled = None
        self._keyboard_query_pending = False
        self._capability_query_pending = False
        self._color_probe = _ColorProbe.FINISHED

    def _drop_past_end_mouse_events(self, codes: _DecodedInput) -> _DecodedInput:
        """Drop the mouse events at a position an X10 report cannot carry, when the terminal has no SGR reports.

        Without SGR reports every mouse report is in the X10 encoding, and xterm sends a column or row past its limit
        as a NUL byte. That byte decodes as the limit itself, so the event would arrive at a wrong position.
        A release is kept, since it ends a press or a drag the application tracks.
        """
        if self.modes.mouse_sgr_mode is not False:
            return codes
        return [
            code
            for code in codes
            if not (
                isinstance(code, tuple)
                and len(code) == 4
                and escape.MOUSE_X10_PAST_END in code[2:]
                # a release ends a press or a drag the application tracks, wherever it happens
                and not code[0].endswith("mouse release")
            )
        ]

    def _stop_mouse_restore_buffer(self) -> None:
        """Stop mouse tracking and restore the screen."""
        # Keep the state the application requested: _start() restores it on a restart.
        mouse_tracking_requested = self._mouse_tracking_enabled
        try:
            self._mouse_tracking(False)
        finally:
            self._mouse_tracking_enabled = mouse_tracking_requested

        move_cursor = ""
        # a start that failed drew nothing, so the cursor stays where it is
        if self.maxrow is not None and self._start_complete:
            move_cursor = escape.set_cursor_position(0, self.maxrow)
        if self._alternate_buffer:
            # Below the last frame first: the move lands on its last row and the line feed goes past it.
            # A terminal without an alternate screen drew the frames on its main screen and ignores the switch back,
            # and one with it scrolls only the alternate screen and restores the cursor saved by the switch.
            if move_cursor:
                move_cursor += "\n"
            move_cursor += escape.PrivateMode.ALTERNATE_SCREEN_BUFFER.disable_seq
        # an application's own "U" run, or a partly written frame, can leave a hyperlink open
        close = escape.HYPERLINK_CLOSE if self._terminal_properties.hyperlinks else ""
        self.write(close + self._attrspec_to_escape(AttrSpec("", "")) + escape.SI + move_cursor + escape.SHOW_CURSOR)
        self.flush()
        # a later start that fails before switching screens has no alternate screen to leave, and drew nothing
        self._alternate_buffer = False
        self._start_complete = False
        # leaving the alternate screen restores the G1 the terminal had before, and whatever runs before the next
        # start can reset the character sets, so G1 is designated again then
        self._setup_G1_done = False

    def _forget_stop_state(self) -> None:
        """Clear the state the stop steps clear, for a stop whose output failed before they all ran.

        A later stop then writes nothing for the run that ended, and a later start begins as after a full stop.
        A step added to the stop clears its state here too.
        """
        self._in_band_resize = False
        self._alternate_scroll_written = False
        self._keyboard_protocol_enabled = None
        self._keyboard_query_pending = False
        self._capability_query_pending = False
        self._color_probe = _ColorProbe.FINISHED
        self._modified_palette_entries.clear()
        self._title_saved = False
        self._alternate_buffer = False
        self._start_complete = False
        self._setup_G1_done = False

    def _stop_restore_palette(self) -> None:
        """Reset any palette entries modify_terminal_palette() changed this session.

        The entries go back to the terminal's default, not to what they were before the screen started.
        OSC 104 resets the changed entries only.
        The Linux console can only reset all 16 entries at once.
        Its reset sequence has no terminator, so a terminal that only claims ``TERM=linux`` reads it as an
        unterminated OSC string: call this before other escape sequences are written, which end that string.
        """
        if not self._modified_palette_entries:
            return
        if _is_linux_console(self.term):
            self.write(escape.LINUX_RESET_PALETTE)
            self.flush()
            self._modified_palette_entries.clear()
            return
        if self.term.lower() == "fbterm":
            # fbterm's palette-modification escape (used in modify_terminal_palette) has no
            # known reset counterpart, so there is nothing safe to send here.
            self._modified_palette_entries.clear()
            return

        indexes = ";".join(str(index) for index in sorted(self._modified_palette_entries))
        self.write(f"{escape.OSC}104;{indexes}{escape.ST}")
        self.flush()
        self._modified_palette_entries.clear()

    def set_title(self, title: str | None) -> None:
        """Set the window title of the terminal.

        The title is shown while the screen runs.
        One set before :meth:`start` is shown when the screen starts.
        Each start saves the title the terminal had, and stopping the screen gives it back,
        so the shell's title is back while :meth:`MainLoop.paused` runs another program.

        Control characters are removed from *title*: a title built from data could otherwise end the title
        and send the rest of the text as terminal commands.
        Characters the terminal encoding cannot represent are replaced with ``?``.
        So are characters a single-byte encoding writes with a byte from 0x80 to 0x9f,
        which a terminal can read as C1 controls.

        The previous title is saved on the terminal's title stack (xterm ``XTWINOPS`` 22 and 23).
        A terminal without the stack ignores it, and keeps the application's title after the screen stops.
        On a Windows console the title is set and saved through the console API instead.
        Nothing is sent to the Linux virtual console or fbterm, which have no window title.
        Nothing is sent to a ``dumb`` terminal outside Windows either, which would print the title as text.

        :param title: the new window title, or None to give the terminal back the title it had before.
        """
        self._title = None if title is None else _TITLE_CONTROLS.sub("", title)
        if self._started:
            self._show_title()

    def _show_title(self) -> None:
        """Show the title :meth:`set_title` asked for, saving the terminal's own title first."""
        if self._title is None:
            self._restore_title()
            return
        if _rejects_osc(self.term):
            return
        if not self._title_saved:
            self._save_title()
            self._title_saved = True
        self._write_title(self._title)
        self.flush()

    def _restore_title(self) -> None:
        """Give the terminal back the title it had before :meth:`_show_title` saved it."""
        if not self._title_saved:
            return
        self._title_saved = False
        self._restore_saved_title()
        self.flush()

    def _save_title(self) -> None:
        """Save the terminal's current window title; :meth:`_restore_saved_title` gives it back."""
        self.write(escape.TITLE_PUSH)

    def _restore_saved_title(self) -> None:
        """Give the terminal back the window title :meth:`_save_title` saved."""
        self.write(escape.TITLE_POP)

    def _write_title(self, title: str) -> None:
        """Write *title*, which has no control characters, as the terminal's window title."""
        encoding = util.get_encoding()
        if util.get_encoding_mode() == "narrow":
            title = "".join("?" if _C1_BYTES.search(char.encode(encoding, "replace")) else char for char in title)
        self.write(f"{escape.SET_TITLE}{title.encode(encoding, 'replace').decode(encoding)}{escape.BEL}")

    def copy_to_clipboard(self, text: str) -> None:
        """Copy text to the system clipboard through the terminal.

        The text is sent as UTF-8 in base64 inside OSC 52,
        so no character of it can reach the terminal as a command.
        A lone surrogate, as in a file name that did not decode, is sent as ``?``.
        The sequence travels with the screen output, so it also reaches the user's terminal over SSH.
        What happens next is up to the terminal:

        - many terminal emulators copy the text;
        - some ask the user first, or copy only after the feature is turned on in their settings;
        - tmux passes the text on with its ``set-clipboard`` option on;
        - a terminal without OSC 52 ignores the sequence.

        No reply tells the application which case it was.
        Terminals and multiplexers also drop a sequence longer than their own limit, so a long text may not arrive.
        The whole text is written at once, and a long one holds up the main loop until the terminal has read it.

        Nothing is sent to the Linux virtual console or fbterm, which have no clipboard.
        Nothing is sent to a ``dumb`` terminal outside Windows either, which would print the sequence as text.

        :param text: the text to copy.
        :raises RuntimeError: the screen is not running.
            A console that reads escape sequences only while the screen runs, such as the Windows console,
            would print the sequence as text.
        """
        if not self._started:
            raise RuntimeError("Start the screen before copying to the clipboard")
        if _rejects_osc(self.term):
            return
        data = base64.b64encode(text.encode("utf-8", "replace")).decode("ascii")
        self.write(f"{escape.SET_CLIPBOARD}{data}{escape.BEL}")
        self.flush()

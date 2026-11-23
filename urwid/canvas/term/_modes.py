# Urwid terminal emulation canvas
#    Copyright (C) 2010  aszlig
#    Copyright (C) 2011  Ian Ward
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

"""Mode setting and mode report control functions of :class:`~urwid.canvas.term.TermCanvas`."""

from __future__ import annotations

import copy
import types
import typing

from urwid.canvas.term._editing import _EditingCanvas
from urwid.canvas.term._screen import _LEFT_RIGHT_MARGIN_LEVEL
from urwid.canvas.term._state import TermCharset
from urwid.display.escape import (
    CSI,
    KittyKeyboardFlag,
    ModeReportState,
    PrivateMode,
    window_size_report,
)

if typing.TYPE_CHECKING:
    from collections.abc import Iterable, Sequence


#: the cursor styles DECSCUSR sets: 1 and 2 a blinking and a steady block, 3 and 4 underline, 5 and 6 a bar
_CURSOR_STYLES: typing.Final = range(1, 7)


#: the states the DEC private modes this canvas keeps no flag for are reported in, by DECRQM:
#: permanently reset, as setting them has no effect: smooth scrolling (DECSCLM, 4) and autorepeat (DECARM, 8),
#: which the display decides, printing (DECPFF 18, DECPEX 19), as no printer is attached, and the national replacement
#: character sets (DECNRCM, 42) and DECKBUM (68), which are not implemented;
#: and so are cursor blinking (12), which the cursor drawn is never shown with, and the urxvt mouse encoding (1015),
#: which is never used;
#: permanently set, for ANSI mode (DECANM, 2), as VT52 mode is not implemented, and for Meta and Alt sending ESC
#: (1036, 1039), as the keys are always sent that way;
#: reset, for 132 columns (DECCOLM, 3), as xterm reports it without its c132 resource
_FIXED_PRIVATE_MODE_STATES: typing.Final = types.MappingProxyType(
    {
        2: ModeReportState.PERMANENTLY_SET,
        3: ModeReportState.RESET,
        **dict.fromkeys((4, 8, 12, 18, 19, 42, 68, 1015), ModeReportState.PERMANENTLY_RESET),
        **dict.fromkeys((1036, 1039), ModeReportState.PERMANENTLY_SET),
    },
)


#: the states the ANSI modes this canvas keeps no flag for are reported in, by DECRQM: permanently reset, for KAM
#: (keyboard locked) and the ECMA-48 modes of a VT320 that keep their reset state, as xterm reports them, and
#: permanently set, for SRM (no local echo)
_FIXED_ANSI_MODE_STATES: typing.Final = types.MappingProxyType(
    {
        2: ModeReportState.PERMANENTLY_RESET,
        12: ModeReportState.PERMANENTLY_SET,
        **dict.fromkeys((1, 5, 7, 10, 11, 13, 14, 15, 16, 17, 18, 19), ModeReportState.PERMANENTLY_RESET),
    },
)


#: the mouse tracking modes that replace each other: reports for presses and releases, highlight tracking, reports
#: also for drags, also for any motion
_MOUSE_TRACKING_MODES: typing.Final = frozenset(
    (
        PrivateMode.MOUSE_REPORTING,
        PrivateMode.MOUSE_HIGHLIGHT_TRACKING,
        PrivateMode.MOUSE_BUTTON_TRACKING,
        PrivateMode.MOUSE_ANY_EVENT_TRACKING,
    )
)

#: the modes that change the encoding of a mouse report from X10: UTF-8 coordinates, SGR parameters
_MOUSE_ENCODING_MODES: typing.Final = frozenset((PrivateMode.MOUSE_UTF8_MODE, PrivateMode.MOUSE_SGR_MODE))

#: the DEC private modes a Terminal recognises and ignores
_RECOGNISED_IGNORED_MODES: typing.Final = frozenset(
    (
        PrivateMode.CURSOR_BLINK,
        PrivateMode.MOUSE_URXVT_MODE,
        PrivateMode.META_SENDS_ESCAPE,
        PrivateMode.ALT_SENDS_ESCAPE,
    )
)

#: the modes that switch to the alternate screen when set and back to the main one when reset
_ALTERNATE_SCREEN_MODES: typing.Final = frozenset(
    (
        PrivateMode.ALTERNATE_SCREEN,
        PrivateMode.ALTERNATE_SCREEN_CLEARED_ON_EXIT,
        PrivateMode.ALTERNATE_SCREEN_BUFFER,
    )
)


#: the flags a Terminal accepts, all the protocol defines; others are dropped, so a query shows they are not set
_KITTY_KEYBOARD_ALL_FLAGS: typing.Final = ~KittyKeyboardFlag(0)

#: the entries a screen's keyboard flag stack keeps, as in kitty; a push onto a full stack drops the oldest entry
_KITTY_KEYBOARD_STACK_LIMIT: typing.Final = 8


class _ModesCanvas(_EditingCanvas):
    """Set and report the modes of a :class:`~urwid.canvas.term.TermCanvas`."""

    __slots__ = ()

    def set_mode(
        self,
        mode: int,
        flag: bool,
        qmark: bool,
        reset: bool,
    ) -> None:
        """Set a single mode, as a helper for csi_set_modes."""
        if qmark:
            # DEC private mode
            private_mode = str(mode)
            if private_mode == PrivateMode.APPLICATION_CURSOR_KEYS:
                # cursor keys send an ESC O prefix, rather than ESC [
                self.modes.keys_decckm = flag
            elif private_mode == PrivateMode.COLUMNS_132:
                # deccolm just clears the screen
                self.clear()
            elif private_mode == PrivateMode.REVERSE_VIDEO:
                # content() applies the mode, so a change touches no cell
                self.modes.reverse_video = flag
            elif private_mode == PrivateMode.ORIGIN_MODE:
                self.modes.constrain_scrolling = flag
                self.set_term_cursor(0, 0)
                self.is_rotten_cursor = False
            elif private_mode == PrivateMode.AUTO_WRAP:
                self.modes.autowrap = flag
            elif private_mode == PrivateMode.CURSOR_VISIBLE:
                self.modes.visible_cursor = flag
                self.set_term_cursor()
            elif private_mode == PrivateMode.MOUSE_X10:
                # X10 compatibility is a last resort: it does not replace a tracking mode the child turned on,
                # and its reset ends only itself.
                if flag and self.modes.mouse_tracking is None:
                    self.modes.mouse_tracking = PrivateMode(private_mode)
                elif not flag and self.modes.mouse_tracking == PrivateMode.MOUSE_X10:
                    self.modes.mouse_tracking = None
            elif private_mode in _MOUSE_TRACKING_MODES:
                # As in xterm, the tracking modes replace each other, and resetting any of them stops tracking.
                self.modes.mouse_tracking = PrivateMode(private_mode) if flag else None
            elif private_mode in _MOUSE_ENCODING_MODES:
                # As in xterm, the encodings replace each other, and a reset only ends the encoding it names.
                if flag:
                    self.modes.mouse_encoding = PrivateMode(private_mode)
                elif self.modes.mouse_encoding == private_mode:
                    self.modes.mouse_encoding = None
            elif private_mode in _RECOGNISED_IGNORED_MODES:
                pass  # for the reason given at each member of PrivateMode
            elif private_mode in _ALTERNATE_SCREEN_MODES:
                self.set_alternate_screen(PrivateMode(private_mode), flag)
            elif private_mode == PrivateMode.SAVE_CURSOR:
                # set saves the cursor as DECSC does, and reset restores it as DECRC does
                if flag:
                    self.save_cursor(with_attrs=True)
                else:
                    self.restore_cursor(with_attrs=True)
            elif private_mode == PrivateMode.LEFT_RIGHT_MARGIN:
                # a VT420 mode, as in xterm; resetting it returns the margins to the screen's edges
                if self.conformance_level >= _LEFT_RIGHT_MARGIN_LEVEL:
                    self.modes.left_right_margins = flag
                    if not flag:
                        self.reset_margins()
            elif private_mode == PrivateMode.NUMERIC_KEYPAD:
                self.modes.keypad_application = flag
            elif private_mode == PrivateMode.BACKARROW_KEY:
                self.modes.backarrow_sends_backspace = flag
            elif private_mode == PrivateMode.BRACKETED_PASTE:
                self.modes.bracketed_paste = flag
            elif private_mode == PrivateMode.FOCUS_REPORTING:
                self.modes.focus_reporting = flag
            elif private_mode == PrivateMode.ALTERNATE_SCROLL:
                self.modes.alternate_scroll = flag
            elif private_mode == PrivateMode.IN_BAND_RESIZE:
                self.modes.in_band_resize = flag
                # the mode asks for a report of the current size on each set, also when it was already set
                if flag:
                    self.widget.respond(window_size_report(self.width, self.height))
            elif private_mode == PrivateMode.SYNCHRONIZED_OUTPUT:
                # Synchronized output (https://gist.github.com/christianparpart/d8a62cc1ab659194337d73e399004036):
                # the child program is asking that its writes not be displayed until it closes the
                # block with CSI ?2026l.
                # Terminal.feed() reads that flag to keep draining the pty instead of handing a mid-update canvas
                # back to the next render() pass.
                self.modes.synchronized_output = flag
        else:  # noqa: PLR5501  # pylint: disable=else-if-used  # readability
            # ECMA-48
            if mode == 3 and self.linux_console:
                self.modes.display_ctrl = flag
            elif mode == 4:
                self.modes.insert = flag
            elif mode == 20:
                self.modes.lfnl = flag

    def private_mode_state(self, mode: str) -> bool | None:
        """Return whether DEC private *mode* is set.

        :returns: the state, or None for a mode this canvas keeps no state for.
        """
        modes = self.modes
        match mode:
            case PrivateMode.APPLICATION_CURSOR_KEYS:
                return modes.keys_decckm
            case PrivateMode.REVERSE_VIDEO:
                return modes.reverse_video
            case PrivateMode.ORIGIN_MODE:
                return modes.constrain_scrolling
            case PrivateMode.AUTO_WRAP:
                return modes.autowrap
            case PrivateMode.CURSOR_VISIBLE:
                return modes.visible_cursor
            case PrivateMode.LEFT_RIGHT_MARGIN:
                # below the VT400 level the mode is not recognised, as in xterm
                return modes.left_right_margins if self.conformance_level >= _LEFT_RIGHT_MARGIN_LEVEL else None
            case PrivateMode.NUMERIC_KEYPAD:
                return modes.keypad_application
            case PrivateMode.BACKARROW_KEY:
                return modes.backarrow_sends_backspace
            case PrivateMode.BRACKETED_PASTE:
                return modes.bracketed_paste
            case PrivateMode.FOCUS_REPORTING:
                return modes.focus_reporting
            case PrivateMode.ALTERNATE_SCROLL:
                return modes.alternate_scroll
            case PrivateMode.SYNCHRONIZED_OUTPUT:
                return modes.synchronized_output
            case PrivateMode.IN_BAND_RESIZE:
                return modes.in_band_resize
            case _ if mode == PrivateMode.MOUSE_X10 or mode in _MOUSE_TRACKING_MODES:
                return modes.mouse_tracking == mode
            case _ if mode in _MOUSE_ENCODING_MODES:
                return modes.mouse_encoding == mode
            case _ if mode in _ALTERNATE_SCREEN_MODES:
                return modes.alternate_screen
        return None

    def csi_report_private_mode(self, mode: int) -> None:
        """Answer a DECRQM query for DEC private *mode* with a DECRPM reply (CSI ? mode ; state $ y).

        The state is 1 for a set mode, 2 for a reset one, and 0 for a mode this canvas keeps no state for.
        The modes in :data:`_FIXED_PRIVATE_MODE_STATES` are reported in the state it gives them.
        """
        state = self.private_mode_state(str(mode))
        if mode in _FIXED_PRIVATE_MODE_STATES:
            value = _FIXED_PRIVATE_MODE_STATES[mode]
        else:
            value = (
                ModeReportState.NOT_RECOGNIZED
                if state is None
                else ModeReportState.SET
                if state
                else ModeReportState.RESET
            )
        self.widget.respond(f"{CSI}?{mode:d};{value:d}$y")

    def csi_report_mode(self, mode: int) -> None:
        """Answer a DECRQM query for ANSI *mode* with a DECRPM reply (CSI mode ; state $ y).

        The state is 1 for a set mode and 2 for a reset one.
        KAM (2) is reported as permanently reset (4), and SRM (12) as permanently set (3), since neither changes, and
        so are the ECMA-48 modes of a VT320 that keep their reset state (1, 5, 7, 10, 11 and 13 to 19), as in xterm.
        Any other mode this canvas keeps no state for is reported as 0.
        Display control mode (3) is always reset while the canvas follows xterm, as xterm reports it.
        """
        modes = self.modes
        match mode:
            case 3:
                value = ModeReportState.SET if modes.display_ctrl else ModeReportState.RESET
            case 4:
                value = ModeReportState.SET if modes.insert else ModeReportState.RESET
            case 20:
                value = ModeReportState.SET if modes.lfnl else ModeReportState.RESET
            case _:
                value = _FIXED_ANSI_MODE_STATES.get(mode, ModeReportState.NOT_RECOGNIZED)
        self.widget.respond(f"{CSI}{mode:d};{value:d}$y")

    def soft_reset(self) -> None:
        """Reset the modes, margins, attributes and character sets DECSTR resets, as xterm does.

        The cursor is shown with the startup style, insert, origin, cursor key, keypad application and left and right
        margin modes are reset, and autowrap is set.
        The scrolling region and the left and right margins are the whole screen again, without moving the cursor.
        The attributes are reset as by SGR 0, DECSCA and SPA stop protecting characters, ED, EL and ECH erase the
        protected ones again, and the character sets are the startup ones.
        The cursor saved by DECSC is the home position with these attributes and character sets, origin mode off and no
        pending autowrap.
        While the canvas follows xterm, the palette colors OSC 4 set are set back too.
        """
        modes = self.modes
        modes.visible_cursor = True
        modes.insert = False
        modes.constrain_scrolling = False
        modes.autowrap = True
        modes.keys_decckm = False
        modes.keypad_application = False
        modes.cursor_style = None
        modes.left_right_margins = False
        self.reset_scroll()
        self.reset_margins()
        self.csi_set_attr([0])
        self.protected = False
        self.modes.iso_protection = False
        self.charset = TermCharset(g1_graphics=self.linux_console)
        if not self.linux_console:
            # as in xterm; the Linux console has no DECSTR
            self._palette.clear()
        self.saved_cursor = (0, 0)
        self.saved_attrs = (copy.copy(self.attrspec), TermCharset(g1_graphics=self.linux_console))
        self.saved_flags = (False, False, False)
        self.set_term_cursor()

    def csi_select_protection(self, params: Sequence[int | None]) -> None:
        """Protect the characters written from now on from the selective erases, or stop (DECSCA, CSI Ps " q).

        1 protects them, and 0, 2 or no parameter stops; any other value is ignored, as in xterm.
        Any value ends the ISO protection SPA selected, so ED, EL and ECH erase the protected characters again.
        """
        self.modes.iso_protection = False
        if params[0] in {None, 0, 1, 2}:
            self.protected = params[0] == 1

    def csi_set_cursor_style(self, params: Sequence[int | None]) -> None:
        """Set the cursor style DECSCUSR (``CSI Ps SP q``) selects.

        0 selects 1, as in xterm, and any value past 6 is ignored.
        From then on :meth:`content` draws the cursor cell itself, see :attr:`TermModes.cursor_style`.
        """
        style = params[0] or 1
        if style in _CURSOR_STYLES:
            self.modes.cursor_style = style
            self.set_term_cursor()

    def csi_set_modes(
        self,
        modes: Iterable[int],
        qmark: bool,
        reset: bool = False,
    ) -> None:
        """Set (DECSET/ECMA-48) or reset modes (DECRST/ECMA-48) if reset is True."""
        flag = not reset

        for mode in modes:
            self.set_mode(mode, flag, qmark, reset)

    def csi_keyboard_flags(self, marker: bytes, params: Sequence[int | None]) -> None:
        """Act on a kitty keyboard protocol sequence for the flag stack of the screen shown.

        An empty stack means no flags. The sequences are:

        - ``CSI ? u``, answered with ``CSI ? flags u``.
        - ``CSI > flags u``, which pushes *flags*.
        - ``CSI < number u``, which pops *number* entries, 1 by default.
        - ``CSI = flags ; mode u``, which changes the entry on top, or adds one to an empty stack. *mode* 1, the
          default, sets *flags*. *mode* 2 adds them. *mode* 3 removes them.

        :param marker: the private marker that selects the sequence: ``?``, ``>``, ``<`` or ``=``.
        :param params: the parameters after it, None for an empty one.
        :raises ValueError: *marker* is none of these.
        """
        stack = self.modes.keyboard_flags
        flags = int((params[0] or 0) & _KITTY_KEYBOARD_ALL_FLAGS)
        current = stack[-1] if stack else 0
        if marker == b"?":
            self.widget.respond(f"{CSI}?{current:d}u")
        elif marker == b">":
            stack.append(flags)
            del stack[:-_KITTY_KEYBOARD_STACK_LIMIT]
        elif marker == b"<":
            del stack[-(params[0] or 1) :]
        elif marker == b"=":
            mode = params[1] if len(params) > 1 and params[1] is not None else 1
            if mode == 1:
                current = flags
            elif mode == 2:
                current |= flags
            elif mode == 3:
                current &= ~flags
            else:
                return
            if stack:
                stack[-1] = current
            else:
                stack.append(current)
        else:
            msg = f"Not a kitty keyboard protocol marker: {marker!r}"
            raise ValueError(msg)

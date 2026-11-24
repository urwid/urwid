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

"""Status reports, device attributes and DCS requests of :class:`~urwid.canvas.term.TermCanvas`."""

from __future__ import annotations

import types
import typing

from urwid.ansi_parser import led_state
from urwid.canvas.term._cells import _RENDITION_BITS
from urwid.canvas.term._editing import _EditingCanvas
from urwid.canvas.term._screen import _LEFT_RIGHT_MARGIN_LEVEL
from urwid.display import _sgr
from urwid.display.escape import CSI, DCS, ST

if typing.TYPE_CHECKING:
    from collections.abc import Sequence

    from urwid.display import AttrSpec


#: the Primary DA reply: a VT420 (64) with selective erase (6), horizontal scrolling (21), ANSI colour (22) and
#: rectangular editing (28); xterm sends it at every conformance level
_PRIMARY_DEVICE_ATTRIBUTES: typing.Final = f"{CSI}?64;6;21;22;28c"
#: the Secondary DA reply, as a VT420 sends it: the VT420 (41), firmware version 1.0 (10), no ROM cartridge (0)
_SECONDARY_DEVICE_ATTRIBUTES: typing.Final = f"{CSI}>41;10;0c"

#: the Tertiary DA reply (DECRPTUI): the unit ID, zero as in xterm
_TERTIARY_DEVICE_ATTRIBUTES: typing.Final = f"{DCS}!|00000000{ST}"


#: the cursor style DECRQSS reports before a DECSCUSR, a steady block, as xterm reports its startup one
_DEFAULT_CURSOR_STYLE: typing.Final = 2


#: the colors of the palette SGR 38;5 and 48;5 select from
_PALETTE_COLORS: typing.Final = 256


#: the DECCIR flag bits: origin mode, a pending SS2, a pending SS3, and a pending autowrap
_FLAG_ORIGIN: typing.Final = 1
_FLAG_SS2: typing.Final = 2
_FLAG_SS3: typing.Final = 4
_FLAG_WRAP: typing.Final = 8


#: the TermCharset name of each designated final byte; any other final byte is drawn as the default set
_DESIGNATED_CHARSETS: typing.Final = types.MappingProxyType({b"0": "vt100", b"U": "ibmpc", b"K": "user"})


#: the replies to the DEC status reports of a VT220 that are not about the cursor, by mode: no printer (15), the
#: user-defined keys unlocked (25), and a North American keyboard (1) that is ready (0) and an LK201 (0) (26)
_PRIVATE_STATUS_REPORTS: typing.Final = types.MappingProxyType({15: "13", 25: "20", 26: "27;1;0;0"})


def _sgr_parameters(attrspec: AttrSpec | None) -> str:
    """Return the SGR parameters that select *attrspec* from the default attributes.

    The parameters start with ``0``, then come the flags, the underline colour and the colours, in the semicolon form
    a :class:`TermCanvas` reads back.
    The hyperlink is not part of SGR and is left out.

    >>> from urwid import AttrSpec
    >>> _sgr_parameters(None)
    '0'
    >>> _sgr_parameters(AttrSpec("light red,bold", "h100", 256))
    '0;1;91;48;5;100'
    >>> _sgr_parameters(AttrSpec("default,curly underline", "default", underline_color="h196"))
    '0;4:3;58:5:196'
    """
    if attrspec is None:
        return "0"
    parameters = ["0", *(f"{code:d}" for name, code in _sgr.FLAGS if getattr(attrspec, name))]
    if attrspec.underline:
        parameters[parameters.index("4")] = _sgr.underline_style_parameter(attrspec)
    if (color := _sgr.underline_color_parameter(attrspec)) is not None:
        parameters.append(color)
    parameters.extend(
        colors for background in (False, True) if (colors := _sgr.color_parameters(attrspec, background=background))
    )
    return ";".join(parameters)


class _ReportsCanvas(_EditingCanvas):
    """Answer the status, attribute and setting requests sent to a :class:`~urwid.canvas.term.TermCanvas`."""

    __slots__ = ()

    def csi_report_window(self, operation: int) -> None:
        """Answer the XTWINOPS size reports: the text area in pixels (14) and in characters (18).

        The size in pixels is reported as 0 by 0, which stands for unknown, as the pty the child reads its size from
        gives no pixels.
        The other window operations are ignored, since the size of the canvas is set by the widget it belongs to.
        """
        match operation:
            case 14:
                self.widget.respond(f"{CSI}4;0;0t")
            case 18:
                self.widget.respond(f"{CSI}8;{self.height:d};{self.width:d}t")

    def dcs_request_setting(self, request: bytes) -> None:
        """Answer a DECRQSS query for the setting *request* names with a DECRPSS reply (DCS Ps $ r Pt ST).

        The reply follows xterm:

        - a valid request gets Ps 1, and Pt is the control sequence that restores the setting;
        - a setting this canvas does not report gets Ps 0 and an empty Pt.

        The settings reported are SGR (``m``), DECSTBM (``r``), DECSCL (``"p``), DECSCA (``"q``), DECSCPP (``$|``),
        DECSLRM (``s``), DECSNLS (``*|``), DECSLPP (``t``), DECSACE (``*x``) and DECSCUSR (`` q``).
        """
        match request:
            case b"m":
                setting = f"{_sgr_parameters(self.attrspec)}m"
            case b"r":
                setting = f"{self.scrollregion_start + 1:d};{self.scrollregion_end + 1:d}r"
            case b'"p':
                # 7-bit controls (1), the only ones sent
                setting = f'{self.conformance_level:d};1"p'
            case b'"q':
                # as in xterm, the characters SPA protects are not reported
                setting = f'{self.protected and not self.modes.iso_protection:d}"q'
            case b"$|":
                # DECSCPP: the columns per page
                setting = f"{self.width:d}$|"
            case b"s" if self.conformance_level >= _LEFT_RIGHT_MARGIN_LEVEL:
                # DECSLRM: the left and right margins, a VT420 setting, as in xterm
                setting = f"{self.margin_left + 1:d};{self.margin_right + 1:d}s"
            case b"*|":
                # DECSNLS: the lines per screen
                setting = f"{self.height:d}*|"
            case b"t":
                # DECSLPP: the lines per page
                setting = f"{self.height:d}t"
            case b"*x":
                setting = f"{self.attribute_extent:d}*x"
            case b" q":
                # DECSCUSR: the cursor style
                style = self.modes.cursor_style
                setting = f"{_DEFAULT_CURSOR_STYLE if style is None else style:d} q"
            case _:
                self.widget.respond(f"{DCS}0$r{ST}")
                return
        self.widget.respond(f"{DCS}1$r{setting}{ST}")

    def csi_report_presentation_state(self, report: int) -> None:
        """Answer DECRQPSR for *report* 1 with DECCIR and for *report* 2 with DECTABSR.

        Any other report is not answered.

        DECCIR is ``DCS 1 $ u Pr ; Pc ; Pp ; Srend ; Satt ; Sflag ; Pgl ; Pgr ; Scss ; Sdesig ST``, as xterm sends it:

        - the 1-based cursor row and column on the screen, also in origin mode, and page 1;
        - ``@`` plus the bits of bold (1), underline (2), blink (4) and reverse (8);
        - ``@`` plus 1 while DECSCA protects the characters written, where xterm adds 1 once DECSCA has protected any
          since the last reset, and neither adds it for SPA;
        - ``@`` plus the bits of origin mode (1), a pending SS2 (2) or SS3 (4), and a pending autowrap (8);
        - the slots invoked into GL and GR;
        - ``@`` plus a bit per slot holding a 96-character set, and the final bytes G0 to G3 were designated with.

        DECTABSR is ``DCS 2 $ u Pt ST``, with the 1-based columns of the tab stops separated by ``/``.
        """
        match report:
            case 1:
                x, y = self.term_cursor
                rendition = sum(bit for name, bit, _sgr in _RENDITION_BITS if getattr(self.attrspec, name, False))
                single = self.charset.single_shifted
                flags = (
                    _FLAG_ORIGIN * self.modes.constrain_scrolling
                    + _FLAG_SS2 * (single == 2)
                    + _FLAG_SS3 * (single == 3)
                    + _FLAG_WRAP * self.is_rotten_cursor
                )
                finals, sets96 = self.charset.designations
                # as in xterm, the characters SPA protects are not reported
                protection = self.protected and not self.modes.iso_protection
                body = (
                    f"{y + 1:d};{x + 1:d};1;{0x40 + rendition:c};{0x40 + protection:c};{0x40 + flags:c};"
                    f"{self.charset.active:d};{self.charset.gr:d};{0x40 + sets96:c};{finals.decode('ascii')}"
                )
                self.widget.respond(f"{DCS}1$u{body}{ST}")
            case 2:
                stops = "/".join(str(x + 1) for x in range(self.width) if self.is_tabstop(x))
                self.widget.respond(f"{DCS}2$u{stops}{ST}")

    def dcs_restore_cursor_information(self, body: bytes) -> None:
        """Restore the cursor, its attributes and the character sets from a DECCIR report *body* (DECRSPS 1).

        A body that is not in the form :meth:`csi_report_presentation_state` describes is ignored whole.
        The colours are kept, since DECCIR does not carry them.
        DECSCA is restored too, which xterm does not do; while SPA protects, which DECCIR does not report, the
        protection is kept.
        """
        fields = body.split(b";")
        if len(fields) != 10:
            return
        row, col, _page, rendition, protection, flags, gl, gr, sets96, finals = fields
        bits = [
            field[0] - 0x40
            for field in (rendition, protection, flags, sets96)
            if len(field) == 1 and 0x40 <= field[0] < 0x50
        ]
        if len(bits) != 4 or not (row.isdigit() and col.isdigit()):
            return
        if {gl, gr} - {b"0", b"1", b"2", b"3"} or len(finals) != 4 or not all(0x30 <= final < 0x7F for final in finals):
            return
        rendition_bits, protection_bits, flag_bits, sets96_bits = bits
        if not self.modes.iso_protection:
            self.protected = bool(protection_bits & 1)
        # origin mode first, since it decides how the cursor position is constrained
        self.modes.constrain_scrolling = bool(flag_bits & _FLAG_ORIGIN)
        self.set_term_cursor(int(col) - 1, int(row) - 1)
        self.is_rotten_cursor = bool(flag_bits & _FLAG_WRAP)
        # SGR 22 also ends faint, which DECCIR does not carry, so faint is set again, as xterm keeps it
        faint = [2] if getattr(self.attrspec, "faint", False) else []
        self.csi_set_attr(
            [22, 24, 25, 27, *faint, *(sgr for _name, bit, sgr in _RENDITION_BITS if rendition_bits & bit)],
        )
        for g, final in enumerate(finals):
            final_byte = bytes((final,))
            self.charset.define(
                g,
                _DESIGNATED_CHARSETS.get(final_byte, "default"),
                final=final_byte,
                size96=bool(sets96_bits & (1 << g)),
            )
        self.charset.activate(int(gl))
        self.charset.gr = int(gr)
        self.charset.end_single_shift()
        if flag_bits & (_FLAG_SS2 | _FLAG_SS3):
            self.charset.single_shift(2 if flag_bits & _FLAG_SS2 else 3)

    def dcs_request_termcap(self, names: bytes) -> None:
        """Answer an XTGETTCAP query (DCS + q Pt ST) for the capability names in *names*.

        Each name is hex-encoded, and the names are separated by ``;``.
        The capabilities answered describe the colors the canvas takes, which the screen it is drawn on converts to
        the colors it draws:

        - ``Co`` and ``colors``, the termcap and terminfo names of the color count: the 256 of the palette;
        - ``RGB``, 8 bits per channel, as any RGB color is taken.

        The reply follows xterm:

        - the names are answered in order up to the first one that is not answered;
        - those answered are listed in one DCS 1 + r Pt ST, Pt holding ``name=value;`` for each, the value hex-encoded
          as the name is;
        - when the first name is not answered, the reply is DCS 0 + r ST.
        """
        values = {"Co": str(_PALETTE_COLORS), "colors": str(_PALETTE_COLORS), "RGB": "8"}
        answered = ""
        for name in names.split(b";"):
            try:
                hex_name = name.decode("ascii")
                key = bytes.fromhex(hex_name).decode("ascii")
            except ValueError:
                break
            if key not in values:
                break
            answered += f"{hex_name}={values[key].encode('ascii').hex().upper()};"
        self.widget.respond(f"{DCS}1+r{answered}{ST}" if answered else f"{DCS}0+r{ST}")

    def dcs_restore_tab_stops(self, body: bytes) -> None:
        """Set the tab stops to the 1-based columns of a DECTABSR report *body* (DECRSPS 2), separated by ``/``.

        An empty body clears every tab stop, and a body with anything but such columns is ignored whole.
        A column past the right edge is dropped.
        """
        columns = body.split(b"/") if body else []
        if not all(column.isdigit() for column in columns):
            return
        self.set_tabstop(clear=True)
        for column in columns:
            if 0 < int(column) <= self.width:
                self.set_tabstop(int(column) - 1)

    def csi_request_user_preferred_supplemental_set(self, _params: Sequence[int | None]) -> None:
        """Answer DECRQUPSS (``CSI & u``) with DECAUPSS for ISO Latin-1, ``DCS 1 ! u A ST``.

        That is the 96-character set a designation such as ``ESC - A`` draws.
        It is not answered at the VT100 level (61), like the other DCS replies.
        """
        if self.conformance_level > 61:
            self.widget.respond(f"{DCS}1!uA{ST}")

    def csi_report_displayed_extent(self, _params: Sequence[int | None]) -> None:
        """Answer DECRQDE (``CSI " v``) with DECRPDE.

        The reply is the height and the width, and column, row and page 1 at the top left.
        """
        self.widget.respond(f'{CSI}{self.height:d};{self.width:d};1;1;1"w')

    def csi_get_device_attributes(self, qmark: bool) -> None:
        """Report the primary device attributes: a VT220 with ANSI colour."""
        if not qmark:
            self.widget.respond(_PRIMARY_DEVICE_ATTRIBUTES)

    def csi_status_report(self, mode: int, *, private: bool = False) -> None:
        """Answer a device status report (DSR) query for *mode*, as xterm does.

        :param mode: the report asked for:

            - 5, the device status report: the terminal is OK;
            - 6, the cursor position report, with the row and the column counted from the top and left margins in
              origin mode, as CUP takes them.
        :param private: the DEC form, ``CSI ? Ps n``, was sent.
            Its cursor position report (DECXCPR) adds page 1, and it also answers 15 (no printer), 25 (user-defined
            keys unlocked) and 26 (a North American keyboard, ready, an LK201).
        """
        prefix = "?" if private else ""
        if mode == 5:
            self.widget.respond(f"{CSI}{prefix}0n")
        elif mode == 6:
            x, y = self.term_cursor
            if self.modes.constrain_scrolling:
                x -= self.margin_left
                y -= self.scrollregion_start
            self.widget.respond(f"{CSI}{prefix}{y + 1:d};{x + 1:d}{';1' if private else ''}R")
        elif private and mode in _PRIVATE_STATUS_REPORTS:
            self.widget.respond(f"{CSI}?{_PRIVATE_STATUS_REPORTS[mode]}n")

    def csi_set_keyboard_leds(self, mode: int = 0) -> None:
        """Set keyboard LEDs.

        This currently just emits a signal, so it can be processed by another widget or the main application.

        The mode-to-state-name mapping is delegated to the shared :func:`urwid.ansi_parser.led_state`, so it is
        maintained in exactly one place.

        :param mode: one of ``0`` (clear all LEDs), ``1`` (set scroll lock LED), ``2`` (set num lock LED) or
            ``3`` (set caps lock LED).
        """
        state = led_state(mode)

        if state is not None:
            self.widget.leds(state)  # type: ignore[arg-type]

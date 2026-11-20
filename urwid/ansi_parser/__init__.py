# Urwid standalone ANSI/VT100 escape-sequence line parser
#    Copyright (C) 2026  urwid contributors
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
"""Standalone ANSI/VT100 escape-sequence parsing, decoupled from any canvas.

This package extracts the platform-independent portion of the escape-sequence
grammar historically embedded inside :mod:`urwid.canvas.term`'s ``TermCanvas`` --
SGR colour/attribute interpretation, horizontal cursor movement, BEL, OSC
title, OSC 8 hyperlink, DEC Special Graphics and keyboard-LED recognition -- into a form that can be used to
interpret a single string (or a stream of chunks) of ANSI-coloured text
without instantiating a pty-backed :class:`~urwid.Terminal` widget.

Sequences that only make sense against a genuine two-dimensional screen
buffer (vertical cursor movement, scroll regions, mode toggles, and so
forth) are recognised, stripped from the resolved text and logged (see
:class:`SkippedOp`) rather than raising or being silently discarded without
trace.
"""

from __future__ import annotations

from urwid.ansi_parser._grammar import _CANCEL as _CANCEL
from urwid.ansi_parser._grammar import MAX_CSI_LENGTH, MAX_OSC_LENGTH, OSC_IGNORED_CONTROLS, ParseState
from urwid.ansi_parser._parser import _DEC_SPECIAL_GRAPHICS as _DEC_SPECIAL_GRAPHICS
from urwid.ansi_parser._parser import _FBTERM_COLOR_SGR as _FBTERM_COLOR_SGR
from urwid.ansi_parser._parser import _INLINE_CONTROLS as _INLINE_CONTROLS
from urwid.ansi_parser._parser import _LINE_END_PAIR as _LINE_END_PAIR
from urwid.ansi_parser._parser import _MAX_CURSOR_POSITION as _MAX_CURSOR_POSITION
from urwid.ansi_parser._parser import _MAX_SKIPPED as _MAX_SKIPPED
from urwid.ansi_parser._parser import _PADDING_BUDGET as _PADDING_BUDGET
from urwid.ansi_parser._parser import _PADDING_PER_CHARACTER as _PADDING_PER_CHARACTER
from urwid.ansi_parser._parser import _PADDING_PER_ROW as _PADDING_PER_ROW
from urwid.ansi_parser._parser import _TERMINAL_SETTING_CSI as _TERMINAL_SETTING_CSI
from urwid.ansi_parser._parser import _VERTICAL_MOVE_CSI as _VERTICAL_MOVE_CSI
from urwid.ansi_parser._parser import LOGGER as LOGGER
from urwid.ansi_parser._parser import AnsiParser, parse_ansi_line, parse_ansi_text
from urwid.ansi_parser._resolve import _LED_STATES as _LED_STATES
from urwid.ansi_parser._resolve import LedsLiteral as LedsLiteral
from urwid.ansi_parser._resolve import attrspec_with_hyperlink, led_state, resolve_osc_hyperlink, resolve_osc_title
from urwid.ansi_parser._results import _ASCII_SET as _ASCII_SET
from urwid.ansi_parser._results import CharsetState, ParsedLine, SkippedOp
from urwid.display._sgr import parse_sgr_parameters, sgi_params_to_attrspec, split_sgr_parameters

# Importable from this module in 5.1.3, where the SGR decoder that used them lived.
from urwid.display.common import _BASIC_COLORS as BASIC_COLORS
from urwid.display.common import _color_desc_256 as color_desc_256
from urwid.display.common import _color_desc_true as color_desc_true

# Defined in this module in 5.1.3.
from urwid.display.escape import BEL as BEL
from urwid.display.escape import ESC as ESC

__all__ = (
    "MAX_CSI_LENGTH",
    "MAX_OSC_LENGTH",
    "OSC_IGNORED_CONTROLS",
    "AnsiParser",
    "CharsetState",
    "ParseState",
    "ParsedLine",
    "SkippedOp",
    "attrspec_with_hyperlink",
    "led_state",
    "parse_ansi_line",
    "parse_ansi_text",
    "parse_sgr_parameters",
    "resolve_osc_hyperlink",
    "resolve_osc_title",
    "sgi_params_to_attrspec",
    "split_sgr_parameters",
)

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


"""Direct terminal UI implementation."""

from __future__ import annotations

from urwid.display._raw_display_base._base import _INPUT_READ_LIMIT as _INPUT_READ_LIMIT
from urwid.display._raw_display_base._base import _SIGWINCH as _SIGWINCH
from urwid.display._raw_display_base._base import SupportsFileno, TermModes, TextWriter
from urwid.display._raw_display_base._detection import (
    IS_WINDOWS,
    IS_WSL,
    TerminalProperties,
    detect_term_colors,
    detect_terminal_properties,
    sends_incomplete_window_size_reports,
)
from urwid.display._raw_display_base._detection import _is_linux_console as _is_linux_console
from urwid.display._raw_display_base._detection import _parse_terminfo_extended_names as _parse_terminfo_extended_names
from urwid.display._raw_display_base._input import _RESIZE_HOLD_PASSES as _RESIZE_HOLD_PASSES
from urwid.display._raw_display_base._screen import Screen

__all__ = (
    "IS_WINDOWS",
    "IS_WSL",
    "Screen",
    "SupportsFileno",
    "TermModes",
    "TerminalProperties",
    "TextWriter",
    "detect_term_colors",
    "detect_terminal_properties",
    "sends_incomplete_window_size_reports",
)

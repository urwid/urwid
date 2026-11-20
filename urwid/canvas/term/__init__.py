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

"""Terminal emulation canvas holding a terminal's screen, scrollback and escape sequence parser.

The module imports nothing platform-specific, so it works where :mod:`urwid.vterm`, which runs a child process on a
pty, does not.
"""

from __future__ import annotations

from urwid.canvas.term._cells import CHARSET_DEFAULT, CHARSET_UTF8, ESC_B
from urwid.canvas.term._parser import CSI_COMMANDS, CSIAlias, CSICommand, TermCanvas
from urwid.canvas.term._state import TermCharset, TermModes
from urwid.display.escape import ESC

__all__ = (
    "CHARSET_DEFAULT",
    "CHARSET_UTF8",
    "CSI_COMMANDS",
    "ESC",
    "ESC_B",
    "CSIAlias",
    "CSICommand",
    "TermCanvas",
    "TermCharset",
    "TermModes",
)

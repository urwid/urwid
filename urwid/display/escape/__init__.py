# Urwid escape sequences common to curses_display and raw_display
#    Copyright (C) 2004-2011  Ian Ward
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


"""Terminal Escape Sequences for input and display."""

from __future__ import annotations

import typing

from urwid import _deprecation
from urwid import str_util as str_util
from urwid.display.escape._input import IS_WINDOWS, decode_input, input_trie, process_keyqueue
from urwid.display.escape._input import _control_sequence_length as _control_sequence_length
from urwid.display.escape._input import _keyconv as _keyconv
from urwid.display.escape._input import _process_keyqueue_at as _process_keyqueue_at
from urwid.display.escape._keys import _CSI_LETTER_KEYS as _CSI_LETTER_KEYS
from urwid.display.escape._keys import _CSI_TILDE_KEYS as _CSI_TILDE_KEYS
from urwid.display.escape._keys import _CSI_U_KEYS as _CSI_U_KEYS
from urwid.display.escape._keys import _KEY_MODIFIER_PREFIXES as _KEY_MODIFIER_PREFIXES
from urwid.display.escape._keys import _MODIFY_OTHER_KEYS_NUMBER as _MODIFY_OTHER_KEYS_NUMBER
from urwid.display.escape._keys import _TILDE_KEY_NUMBERS as _TILDE_KEY_NUMBERS
from urwid.display.escape._keys import KeyModifier, KittyKeyboardFlag, escape_modifier, input_sequences
from urwid.display.escape._keys import _modified_key_name as _modified_key_name
from urwid.display.escape._keys import _text_key_name as _text_key_name
from urwid.display.escape._mouse import _MOUSE_BYTE_MAX as _MOUSE_BYTE_MAX
from urwid.display.escape._mouse import _MOUSE_BYTE_OFFSET as _MOUSE_BYTE_OFFSET
from urwid.display.escape._mouse import _MOUSE_COORD_OFFSET as _MOUSE_COORD_OFFSET
from urwid.display.escape._mouse import _MOUSE_MODIFIER_PREFIXES as _MOUSE_MODIFIER_PREFIXES
from urwid.display.escape._mouse import _NEXT_MOUSE_REPORT as _NEXT_MOUSE_REPORT
from urwid.display.escape._mouse import _RENAMED_MOUSE_BITS as _RENAMED_MOUSE_BITS
from urwid.display.escape._mouse import _SGR_MOUSE_MAX_LEN as _SGR_MOUSE_MAX_LEN
from urwid.display.escape._mouse import (
    MOUSE_DRAG_FLAG,
    MOUSE_MULTIPLE_CLICK_FLAG,
    MOUSE_MULTIPLE_CLICK_MASK,
    MOUSE_RELEASE_FLAG,
    MOUSE_X10_PAST_END,
    MouseBit,
)
from urwid.display.escape._mouse import _mouse_button as _mouse_button
from urwid.display.escape._sequences import _C0_CONTROLS as _C0_CONTROLS
from urwid.display.escape._sequences import _C1_CONTROLS as _C1_CONTROLS
from urwid.display.escape._sequences import _MOUSE_MODES as _MOUSE_MODES
from urwid.display.escape._sequences import _SI_BYTES as _SI_BYTES
from urwid.display.escape._sequences import _SI_SO as _SI_SO
from urwid.display.escape._sequences import _SO_BYTES as _SO_BYTES
from urwid.display.escape._sequences import (
    ALT_DEC_SPECIAL_CHARS,
    APP_KEYPAD_MODE,
    BEL,
    CSI,
    CURSOR_HOME,
    CURSOR_HOME_COL,
    DCS,
    DEC_SPECIAL_CHARMAP,
    DEC_SPECIAL_CHARS,
    DEC_SPECIAL_RE,
    DEC_TAG,
    DECRQM_RECOGNIZED_VALUES,
    DECRQM_SETTABLE_VALUES,
    DESIGNATE_G1_SPECIAL,
    ERASE_IN_LINE_RIGHT,
    ESC,
    HIDE_CURSOR,
    HYPERLINK_CLOSE,
    IBMPC_OFF,
    IBMPC_ON,
    INSERT_OFF,
    INSERT_ON,
    KITTY_KEYBOARD_FLAGS,
    KITTY_KEYBOARD_POP,
    KITTY_KEYBOARD_PUSH,
    KITTY_KEYBOARD_QUERY,
    LINUX_RESET_PALETTE,
    LINUX_SET_PALETTE,
    MODIFY_OTHER_KEYS_ON,
    MODIFY_OTHER_KEYS_QUERY,
    MODIFY_OTHER_KEYS_RESOURCE,
    MOUSE_TRACKING_OFF,
    MOUSE_TRACKING_ON,
    NUM_KEYPAD_MODE,
    OSC,
    REPORT_CURSOR_POSITION,
    REPORT_DEFAULT_COLORS,
    REPORT_DEVICE_ATTRIBUTES,
    REPORT_STATUS,
    REPORT_TERMINAL_VERSION,
    REQUEST_RENDITION,
    SAFE_ASCII_DEC_SPECIAL_RE,
    SET_CLIPBOARD,
    SET_TITLE,
    SHOW_CURSOR,
    SI,
    SO,
    ST,
    TITLE_POP,
    TITLE_PUSH,
    ModeReportState,
    PrivateMode,
    hyperlink_open,
    move_cursor_down,
    move_cursor_right,
    move_cursor_up,
    request_capability,
    set_cursor_position,
    set_modify_other_keys,
    window_size_report,
    within_double_byte,
)
from urwid.display.escape._trie import _CSI_PARAMETERS_MAX_LEN as _CSI_PARAMETERS_MAX_LEN
from urwid.display.escape._trie import _ORD_0 as _ORD_0
from urwid.display.escape._trie import _ORD_9 as _ORD_9
from urwid.display.escape._trie import _WINDOW_SIZE_MAX as _WINDOW_SIZE_MAX
from urwid.display.escape._trie import _WINDOW_SIZE_REPORT_LENGTHS as _WINDOW_SIZE_REPORT_LENGTHS
from urwid.display.escape._trie import KeyqueueTrie, MoreInputRequired

__all__ = (
    "ALT_DEC_SPECIAL_CHARS",
    "APP_KEYPAD_MODE",
    "BEL",
    "CSI",
    "CURSOR_HOME",
    "CURSOR_HOME_COL",
    "DCS",
    "DECRQM_RECOGNIZED_VALUES",
    "DECRQM_SETTABLE_VALUES",
    "DEC_SPECIAL_CHARMAP",
    "DEC_SPECIAL_CHARS",
    "DEC_SPECIAL_RE",
    "DEC_TAG",
    "DESIGNATE_G1_SPECIAL",
    "ERASE_IN_LINE_RIGHT",
    "ESC",
    "HIDE_CURSOR",
    "HYPERLINK_CLOSE",
    "IBMPC_OFF",
    "IBMPC_ON",
    "INSERT_OFF",
    "INSERT_ON",
    "IS_WINDOWS",
    "KITTY_KEYBOARD_FLAGS",
    "KITTY_KEYBOARD_POP",
    "KITTY_KEYBOARD_PUSH",
    "KITTY_KEYBOARD_QUERY",
    "LINUX_RESET_PALETTE",
    "LINUX_SET_PALETTE",
    "MODIFY_OTHER_KEYS_ON",
    "MODIFY_OTHER_KEYS_QUERY",
    "MODIFY_OTHER_KEYS_RESOURCE",
    "MOUSE_DRAG_FLAG",
    "MOUSE_MULTIPLE_CLICK_FLAG",
    "MOUSE_MULTIPLE_CLICK_MASK",
    "MOUSE_RELEASE_FLAG",
    "MOUSE_TRACKING_OFF",
    "MOUSE_TRACKING_ON",
    "MOUSE_X10_PAST_END",
    "NUM_KEYPAD_MODE",
    "OSC",
    "REPORT_CURSOR_POSITION",
    "REPORT_DEFAULT_COLORS",
    "REPORT_DEVICE_ATTRIBUTES",
    "REPORT_STATUS",
    "REPORT_TERMINAL_VERSION",
    "REQUEST_RENDITION",
    "SAFE_ASCII_DEC_SPECIAL_RE",
    "SET_CLIPBOARD",
    "SET_TITLE",
    "SHOW_CURSOR",
    "SI",
    "SO",
    "ST",
    "TITLE_POP",
    "TITLE_PUSH",
    "KeyModifier",
    "KeyqueueTrie",
    "KittyKeyboardFlag",
    "ModeReportState",
    "MoreInputRequired",
    "MouseBit",
    "PrivateMode",
    "decode_input",
    "escape_modifier",
    "hyperlink_open",
    "input_sequences",
    "input_trie",
    "move_cursor_down",
    "move_cursor_right",
    "move_cursor_up",
    "process_keyqueue",
    "request_capability",
    "set_cursor_position",
    "set_modify_other_keys",
    "window_size_report",
    "within_double_byte",
)


# Hidden from type checkers, which would otherwise accept any attribute name of this module.
if not typing.TYPE_CHECKING:

    def __getattr__(name: str) -> int:
        """Resolve a mouse report bit by the name it had before :class:`MouseBit`, warning about the rename.

        :raises AttributeError: *name* is not defined in this module.

        .. deprecated:: 5.0.0
            Use the members of :class:`MouseBit` instead of the ``_MOUSE_*_FLAG`` names and ``_MOUSE_BUTTON_MASK``.
            This API will be removed in version 6.0.
        """
        if name in _RENAMED_MOUSE_BITS:
            bit = _RENAMED_MOUSE_BITS[name]
            _deprecation.warn(
                f"{__name__}.{name} is renamed to {__name__}.MouseBit.{bit.name}.", since="5.0.0", removed_in="6.0"
            )
            return int(bit)
        raise AttributeError(f"{name} is not defined in {__name__}")

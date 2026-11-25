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


"""Detection of the host terminal's colours and properties from its name, the environment and terminfo."""

from __future__ import annotations

import dataclasses
import os
import pathlib
import platform
import re
import stat
import struct
import sys
import typing

from urwid.display import _sgr
from urwid.display.common import _depth

if typing.TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence


IS_WINDOWS = sys.platform == "win32"
IS_WSL = (sys.platform == "linux") and ("wsl" in platform.platform().lower())


_ColorCount = typing.Literal[1, 16, 88, 256, 16777216]

# Terminals that implement SGR 90-97 / 100-107 bright colors without needing bold/blink.
_INDEPENDENT_BRIGHT_FAMILIES = frozenset(
    {
        "alacritty",
        "conemu",
        "cygwin",
        "eterm",
        "foot",
        "ghostty",
        "gnome",
        "iterm",
        "iterm2",
        "kitty",
        "konsole",
        "mintty",
        "mlterm",
        "putty",
        "rxvt",
        "st",
        "terminator",
        "tmux",
        "vscode",
        "vte",
        "wezterm",
        "xfce",
        "xterm",
    }
)
_TRUECOLOR_FAMILIES = frozenset(
    {
        "alacritty",
        "contour",
        "foot",
        "ghostty",
        "iterm",
        "iterm2",
        "kitty",
        "wezterm",
    }
)
_NO_UNDERLINE_FAMILIES = frozenset({"dumb", "unknown", "vt52"})
# the TERM families of a multiplexer, which answers the program in place of the terminal around it
_MULTIPLEXER_FAMILIES = frozenset({"screen", "tmux"})
# the terminals that draw every underline style (SGR 4:2 to 4:5) and the underline colour without a terminfo entry
# saying so, by the lower-case terminal name of their XTVERSION reply, and the first version that draws them all.
# VTE replies with the number of its VTE_VERSION, and 0.76 is the first with dotted and dashed underlines.
# The environment variables that name these terminals are not read: a terminal started from inside another one
# inherits them (Konsole and tmux pass VTE_VERSION on), while the reply comes from the terminal itself.
_XTVERSION_UNDERLINE_STYLE_FLOORS: Mapping[str, tuple[int, ...]] = {
    "foot": (1, 18, 0),
    "ghostty": (1, 0, 0),
    "iterm2": (3, 6, 7),
    "konsole": (22, 12),
    "mintty": (3, 1, 5),
    "rio": (0, 1, 6),
    "vte": (7600,),
    "wezterm": (20210203, 95643),
    "xterm.js": (5, 0, 0),
}
# the numbers a version starts with, separated by "." or "-", as in "3.6.7" or WezTerm's "20240203-110809-5046fc22"
_VERSION_NUMBERS = re.compile(r"v?(\d{1,9}(?:[.-]\d{1,9}){0,7})")
# a word after the numbers that marks a build before the release they name
_PRERELEASE = re.compile(r"alpha|beta|canary|dev|insider|nightly|pre|rc", re.IGNORECASE)
# an XTVERSION reply's terminal name and its version, as in "XTerm(390)" or "WezTerm 20240203-110809-5046fc22"
_XTVERSION_TEXT = re.compile(r"([A-Za-z][\w.+-]*?)[ (](.*)")
#: the terminfo capabilities asked of the terminal with XTGETTCAP: the colour count, 24-bit colour in the ncurses and
#: in the tmux form, and the underline style and colour strings
_QUERIED_CAPABILITIES: typing.Final = ("colors", "RGB", "Tc", "Smulx", "Setulc")
# an RGB value that names the bits per component, as ncurses gives it: one number, or one per component
_RGB_BITS: typing.Final = re.compile(r"[1-9][0-9]?(?:/[1-9][0-9]?/[1-9][0-9]?)?", re.ASCII)
# the terminals that draw 24-bit colours and show it in no reply to the rendition probe or XTGETTCAP, by the
# lower-case name of their XTVERSION reply; tmux converts them for the terminal around it
_XTVERSION_TRUE_COLOR_TERMINALS: typing.Final = frozenset({"konsole", "tmux", "xterm.js"})
# the background the rendition probe sets, a 256-colour cube entry the 88-colour palette does not have, as an RGB
# value and as that entry
_PROBE_RGB: typing.Final = (135, 175, 215)
_PROBE_ENTRY: typing.Final = 110
# a DECRPSS reply to the rendition request: SGR parameters, and the final byte
_RENDITION_SETTING: typing.Final = re.compile(r"[0-9:;]*m", re.ASCII)
# the decimal number of a colour component or a palette entry
_BYTE: typing.Final = re.compile(r"[0-9]{1,3}", re.ASCII)


# Windows 10 TH2 (1511) gained 256-color VT; 1703-era build 14931 gained 24-bit color.
_WINDOWS_256COLOR_BUILD = 10586
_WINDOWS_TRUECOLOR_BUILD = 14931

# Compiled terminfo entries, as term(5) describes them.
# ncurses' built-in search path on common systems, searched after TERMINFO, ~/.terminfo and TERMINFO_DIRS.
_TERMINFO_SYSTEM_DIRS = ("/etc/terminfo", "/lib/terminfo", "/usr/share/terminfo", "/usr/lib/terminfo")
# Header magic -> struct format of one numeric capability: the legacy format has 16-bit numbers,
# the ncurses 6.1 extended number format has 32-bit numbers.
_TERMINFO_NUMBER_FORMATS: Mapping[int, str] = {0o432: "<h", 0o1036: "<i"}
_TERMINFO_HEADER = struct.Struct("<6h")
# the extended section's counts: booleans, numbers, strings, string table items, and string table bytes
_TERMINFO_EXTENDED_HEADER = struct.Struct("<5h")
_TERMINFO_COLORS_INDEX = 13  # position of "colors" among the predefined numeric capabilities
_TERMINFO_MAX_SIZE = 32768  # bytes read from an entry: the largest entry ncurses accepts
# Minimum terminfo "colors" value -> the colour count it allows; 8-colour terminals use bold for the bright half.
_TERMINFO_COLOR_COUNTS: Sequence[tuple[int, _ColorCount]] = ((16777216, 16777216), (256, 256), (88, 88), (8, 16))


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class TerminalProperties:
    """The properties of a terminal that a raw screen draws with.

    :func:`detect_terminal_properties` takes them from TERM, its terminfo entry and the environment; it never turns
    on :attr:`hyperlinks`, since no query for OSC 8 support exists.
    """

    colors: _ColorCount
    has_underline: bool
    fg_bright_is_bold: bool
    bg_bright_is_blink: bool
    back_color_erase: bool
    underline_styles: bool = False
    hyperlinks: bool = False


# iTerm2 3.5.6 to 3.5.10 send a window size report without its final "t",
# so the key typed after it is read as the final byte of an unknown sequence.
_ITERM2_COMPLETE_WINDOW_SIZE_REPORT: typing.Final = (3, 5, 11)


def sends_incomplete_window_size_reports(environ: Mapping[str, str]) -> bool:
    """Return whether *environ* names an iTerm2 release that sends a window size report without its final byte.

    iTerm2 sets ``LC_TERMINAL`` and ``LC_TERMINAL_VERSION``, and SSH passes them on with the locale.
    An iTerm2 version that cannot be read counts as such a release.
    Under screen or tmux, as TERM names them, the variables are inherited, and the program talks to the multiplexer.
    """
    if environ.get("LC_TERMINAL") != "iTerm2" or _term_families(environ.get("TERM", "")) & _MULTIPLEXER_FAMILIES:
        return False
    version = re.match(r"(\d+)\.(\d+)\.(\d+)", environ.get("LC_TERMINAL_VERSION", ""))
    return version is None or tuple(int(part) for part in version.groups()) < _ITERM2_COMPLETE_WINDOW_SIZE_REPORT


def _term_families(term: str) -> frozenset[str]:
    """Name tokens from a TERM value.

    ``screen.xterm-256color`` yields ``screen``, ``xterm`` and ``256color``.
    ``rxvt-unicode-256color`` yields ``rxvt``, ``unicode`` and ``256color``.
    ``xterm-kitty`` yields ``xterm`` and ``kitty``.
    """
    families: set[str] = set()
    for part in term.lower().split("."):
        if part:
            families.update(token for token in part.split("-") if token)
    return frozenset(families)


# ``linux``, optionally with a kernel version as in the terminfo names ``linux2.6`` and ``linux3.0``,
# then the end of the name or a ``-`` or ``.`` suffix.
_LINUX_CONSOLE_TERM = re.compile(r"linux(?:\d+(?:\.\d+)*)?(?:[-.]|$)", re.IGNORECASE)


def _is_linux_console(term: str) -> bool:
    """Tell whether a TERM value names the Linux virtual console.

    ``linux``, ``linux-16color``, ``linux.utf8`` and the versioned terminfo names such as ``linux2.6.26`` do.
    A multiplexer that names its outer terminal, such as ``screen.linux``, is not the console.
    """
    return _LINUX_CONSOLE_TERM.match(term) is not None


def _rejects_osc(term: str) -> bool:
    """Tell whether the terminal a TERM value names cannot take a window title or clipboard sequence.

    The Linux virtual console reads only its own palette sequences and prints the others as text.
    fbterm has neither a window title nor a clipboard.
    A ``dumb`` terminal reads no escape sequences.
    On Windows, TERM does not describe the console, so only the Linux console names count there.
    """
    return _is_linux_console(term) or (term.lower() in {"dumb", "fbterm"} and not IS_WINDOWS)


def _parse_force_color(value: str) -> _ColorCount:
    """Map FORCE_COLOR / CLICOLOR_FORCE to a color count (chalk / supports-color convention)."""
    normalized = value.strip().lower()
    if normalized in {"0", "false", "no"}:
        return 1
    if normalized in {"", "1", "true", "yes"}:
        return 16
    if normalized == "2":
        return 256
    if normalized == "3":
        return 16777216
    return 16


def _windows_version() -> tuple[int, int, int] | None:
    if sys.platform != "win32":
        return None
    # pyrefly: ignore[missing-attribute]  # Windows only, behind a platform check
    version = sys.getwindowsversion()  # pylint: disable=no-member
    return (version.major, version.minor, version.build)


def _windows_console_colors(version: tuple[int, int, int] | None) -> _ColorCount | None:
    """Color depth of the Windows console VT host, if any."""
    if version is None or version < (10, 0, 0):
        return None
    if version >= (10, 0, _WINDOWS_TRUECOLOR_BUILD):
        return 16777216
    if version >= (10, 0, _WINDOWS_256COLOR_BUILD):
        return 256
    return 16


def _colors_from_term(term: str, families: frozenset[str]) -> _ColorCount:
    term_l = term.lower()
    if not term_l:
        return 16
    if families & _NO_UNDERLINE_FAMILIES or term_l in _NO_UNDERLINE_FAMILIES:
        return 1
    if "direct" in term_l or families & _TRUECOLOR_FAMILIES:
        return 16777216
    if "256color" in term_l:
        return 256
    if "88color" in term_l:
        return 88
    return 16


def _parse_terminfo_colors(data: bytes) -> int | None:
    """Return the ``colors`` capability of a compiled terminfo entry.

    The entry is untrusted data, so its header is checked before its sizes are used as offsets.

    :returns: the number of colours, or None when the entry has no ``colors``.
    :raises ValueError: the entry is not in a compiled terminfo format, or it is shorter than its header says.
    """
    if len(data) < _TERMINFO_HEADER.size:
        raise ValueError
    magic, *sizes = _TERMINFO_HEADER.unpack_from(data)
    names_size, booleans_count, numbers_count, strings_count, strings_size = sizes
    number_format = _TERMINFO_NUMBER_FORMATS.get(magic)
    if number_format is None or min(sizes) < 0:
        raise ValueError
    number_size = struct.calcsize(number_format)
    numbers_offset = _TERMINFO_HEADER.size + names_size + booleans_count
    numbers_offset += numbers_offset % 2  # the numbers start on an even byte
    # The string offsets are 16-bit and followed by the string table.
    if numbers_offset + numbers_count * number_size + 2 * strings_count + strings_size > len(data):
        raise ValueError
    if numbers_count <= _TERMINFO_COLORS_INDEX:
        return None
    (colors,) = struct.unpack_from(number_format, data, numbers_offset + _TERMINFO_COLORS_INDEX * number_size)
    # -1 marks an absent capability and -2 a cancelled one
    return colors if colors > 0 else None


def _parse_terminfo_extended_names(data: bytes) -> frozenset[str]:
    """Return the names of the extended capabilities of a compiled terminfo entry, such as ``Smulx``.

    The extended section follows the string table, on an even byte: a header of five 16-bit counts, the boolean values,
    the numbers, the offsets of the strings and of the names, and then a table of NUL-terminated strings, which holds
    the strings that are set before the names.
    The entry is untrusted data, so the sizes are checked before they are used as offsets.

    :returns: the names, empty when the entry has no extended section.
    :raises ValueError: the entry is not in a compiled terminfo format, or its sizes do not fit it.
    """
    if len(data) < _TERMINFO_HEADER.size:
        raise ValueError
    magic, names_size, booleans_count, numbers_count, strings_count, strings_size = _TERMINFO_HEADER.unpack_from(data)
    number_format = _TERMINFO_NUMBER_FORMATS.get(magic)
    if number_format is None or min(names_size, booleans_count, numbers_count, strings_count, strings_size) < 0:
        raise ValueError
    number_size = struct.calcsize(number_format)
    offset = _TERMINFO_HEADER.size + names_size + booleans_count
    offset += offset % 2
    offset += numbers_count * number_size + 2 * strings_count + strings_size
    offset += offset % 2
    if offset + _TERMINFO_EXTENDED_HEADER.size > len(data):
        return frozenset()
    ext_booleans, ext_numbers, ext_strings, _items, table_size = _TERMINFO_EXTENDED_HEADER.unpack_from(data, offset)
    if min(ext_booleans, ext_numbers, ext_strings, table_size) < 0:
        raise ValueError
    offset += _TERMINFO_EXTENDED_HEADER.size + ext_booleans
    offset += offset % 2
    offset += ext_numbers * number_size
    names_count = ext_booleans + ext_numbers + ext_strings
    if offset + 2 * (ext_strings + names_count) + table_size > len(data):
        raise ValueError
    string_offsets = struct.unpack_from(f"<{ext_strings}h", data, offset)
    offset += 2 * (ext_strings + names_count)
    table = data[offset : offset + table_size].split(b"\0")
    # the strings that are set come first, an absent or cancelled one has a negative offset and no entry
    values = sum(1 for string_offset in string_offsets if string_offset >= 0)
    names = table[values : values + names_count]
    if len(names) != names_count:
        raise ValueError
    return frozenset(name.decode("ascii", "replace") for name in names)


def _read_terminfo_entry(path: pathlib.Path) -> bytes | None:
    """Return the start of the regular file at *path*.

    Opening a device, even briefly, can disturb its other users: a serial port asserts DTR.
    So a device is never opened, even if the entry is replaced while it is being read:

    - The path is resolved with realpath(), which reads links without opening anything.
    - stat() checks that the resolved path is a regular file.
    - Each component is opened through the previous directory with O_NOFOLLOW, so a symlink planted afterwards fails.
    - O_NONBLOCK and O_NOCTTY stop a FIFO from blocking and a tty from becoming the controlling terminal.

    :returns: up to ``_TERMINFO_MAX_SIZE`` bytes, or None when *path* is missing, unreadable or not a regular file.
    """
    try:
        real = os.path.realpath(path, strict=True)
        if not stat.S_ISREG(pathlib.Path(real).stat().st_mode):
            return None
        *directories, name = pathlib.PurePath(real).parts
        fd = os.open(directories[0], os.O_RDONLY | os.O_DIRECTORY)
        try:
            for directory in directories[1:]:
                parent, fd = fd, -1
                try:
                    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                finally:
                    os.close(parent)
            entry = os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOCTTY | os.O_NOFOLLOW, dir_fd=fd)
        finally:
            if fd >= 0:
                os.close(fd)
    # ValueError: a directory from the environment holds NUL or a lone surrogate.
    # RecursionError: realpath() before Python 3.13 recurses once per link of a long symlink chain.
    # NotImplementedError: dir_fd is unavailable at run time, as on macOS 10.9.
    except (OSError, ValueError, RecursionError, NotImplementedError):
        return None
    try:
        return os.read(entry, _TERMINFO_MAX_SIZE) if stat.S_ISREG(os.fstat(entry).st_mode) else None
    except OSError:
        return None
    finally:
        os.close(entry)


def _terminfo_entry(term: str, environ: Mapping[str, str]) -> bytes | None:
    """Return the compiled terminfo entry of *term*.

    The stdlib ``curses.setupterm()`` loads one entry per process and ignores later terminal names,
    so the compiled entry is read directly.
    Directories are searched in ncurses' order: ``TERMINFO``, ``$HOME/.terminfo``, ``TERMINFO_DIRS``,
    then the system directories.
    In each one the entry is looked up under its first letter, and under that letter's hexadecimal code as on macOS.
    The first valid entry found is used, and a malformed one is passed over as ncurses does.

    Native Windows has no terminfo database, and a Win32 path can name a device such as ``COM1`` by its file name,
    so nothing is looked up there.

    :returns: the entry, or None when no valid entry is found.
    """
    if IS_WINDOWS:
        return None
    # TERM comes from the environment and becomes a file name. Only the characters terminal names use are accepted,
    # so it cannot name another directory or a path the file system cannot encode.
    if not term or not term.isascii() or not all(char.isalnum() or char in "+-._" for char in term):
        return None
    directories: list[pathlib.Path] = []
    if terminfo := environ.get("TERMINFO"):
        directories.append(pathlib.Path(terminfo))
    if home := environ.get("HOME"):
        directories.append(pathlib.Path(home, ".terminfo"))
    directories.extend(pathlib.Path(entry) for entry in environ.get("TERMINFO_DIRS", "").split(os.pathsep) if entry)
    directories.extend(pathlib.Path(directory) for directory in _TERMINFO_SYSTEM_DIRS)
    for directory in directories:
        for subdirectory in (term[0], f"{ord(term[0]):x}"):
            if (data := _read_terminfo_entry(directory / subdirectory / term)) is None:
                continue
            try:
                _parse_terminfo_colors(data)
            except ValueError:  # malformed: ncurses passes over it too
                continue
            return data
    return None


def _version_reaches(version: str, floor: tuple[int, ...] | None) -> bool:
    """Return whether *version* is a release at or after *floor*.

    A version with a pre-release word after its numbers, such as ``3.6.7beta2`` or ``1.2.0-dev``, counts as just before
    the release its numbers name, so it reaches only a *floor* below that release.
    VS Code ships pre-releases of xterm.js, such as ``6.1.0-beta.337``.

    >>> _version_reaches("3.6.7", (3, 6, 7)), _version_reaches("3.6.7beta2", (3, 6, 7))
    (True, False)
    >>> _version_reaches("6.1.0-beta.337", (5, 0, 0)), _version_reaches("22.12.0-rc1", (22, 12))
    (True, False)
    >>> _version_reaches("20240203-110809-5046fc22", (20210203, 95643))
    True

    :param floor: the first release, None for a terminal with none.
    """
    if floor is None or (match := _VERSION_NUMBERS.match(version)) is None:
        return False
    numbers = tuple(int(part) for part in re.split(r"[.-]", match.group(1)))
    # missing parts are zeros, so 22.12.0 and 22.12 name the same release
    width = max(len(numbers), len(floor))
    numbers += (0,) * (width - len(numbers))
    floor += (0,) * (width - len(floor))
    if _PRERELEASE.search(version, match.end()):
        return numbers > floor
    return numbers >= floor


def _underline_styles_from_version(text: str) -> bool:
    """Return whether the terminal an XTVERSION reply names draws every underline style and the underline colour.

    >>> _underline_styles_from_version("Konsole 25.08.3"), _underline_styles_from_version("XTerm(407)")
    (True, False)

    :param text: the reply's text, a terminal name and its version.
    """
    if (match := _XTVERSION_TEXT.match(text)) is None:
        return False
    return _version_reaches(match.group(2), _XTVERSION_UNDERLINE_STYLE_FLOORS.get(match.group(1).lower()))


def _colors_from_version(text: str) -> _ColorCount | None:
    """Return the colour count of the terminal an XTVERSION reply names, None when the reply does not show one.

    >>> _colors_from_version("Konsole 25.12.3"), _colors_from_version("XTerm(407)")
    (16777216, None)

    :param text: the reply's text, a terminal name and its version.
    """
    if (match := _XTVERSION_TEXT.match(text)) is None or match.group(1).lower() not in _XTVERSION_TRUE_COLOR_TERMINALS:
        return None
    return 16777216


def _valid_background_groups(groups: Sequence[str]) -> bool:
    """Return whether every background colour among the SGR parameter *groups* is complete and in range.

    A background is ``48:2:r:g:b``, ``48:2::r:g:b``, ``48;2;r;g;b``, ``48:5:n`` or ``48;5;n``,
    each component a decimal number from 0 to 255.
    The arguments of a semicolon-form foreground or underline colour are passed over, not read as codes.
    """
    index = 0
    while index < len(groups):
        code, *subparameters = groups[index].split(":")
        # the decoder reads a code as a number, so a code with leading zeros is the same code
        code = code.lstrip("0") or "0"
        if code in {"38", "48", "58"} and not subparameters:
            count = {"5": 1, "2": 3}.get(groups[index + 1] if index + 1 < len(groups) else "")
            if count is None:
                if code == "48":
                    return False
                index += 1
                continue
            arguments = groups[index + 2 : index + 2 + count]
            if code == "48" and not (
                len(arguments) == count and all(_BYTE.fullmatch(value) and int(value) <= 0xFF for value in arguments)
            ):
                return False
            index += 2 + count
            continue
        if code == "48":
            model, *components = subparameters or [""]
            if model == "2" and len(components) == 4 and not components[0]:
                components = components[1:]
            if not (
                {"2": 3, "5": 1}.get(model) == len(components)
                and all(_BYTE.fullmatch(value) and int(value) <= 0xFF for value in components)
            ):
                return False
        index += 1
    return True


def _colors_from_rendition(setting: str) -> _ColorCount | None:
    """Return the colour count a DECRPSS reply to the rendition probe confirms, None when it confirms none.

    The terminal stores the probe's background as it draws it: the RGB value means 24-bit colour, and the probe's
    256-colour entry means a 256-colour palette.
    Any other entry is a palette both colour counts have, and any other background is no evidence.
    A reply with a malformed background is ignored whole: the decoder that reads it for drawing accepts a background
    cut short, and would leave the probe's entry active.

    >>> _colors_from_rendition("0;1;4;33;48;2;135;175;215m")
    16777216
    >>> _colors_from_rendition("0;22;1;33;48:2:135:175:215;4m")
    16777216
    >>> _colors_from_rendition("0;1;4;93;48:5:110m"), _colors_from_rendition("0;48:5:110;48:2:1:2m")
    (256, None)
    >>> _colors_from_rendition("0;048;5;110;048;5m")

    :param setting: the setting of the DECRPSS reply: SGR parameters, and ``m``.
    """
    if not _RENDITION_SETTING.fullmatch(setting):
        return None
    parameters = setting.removesuffix("m")
    if not _valid_background_groups(parameters.split(";")):
        return None
    spec = _sgr.sgi_params_to_attrspec(_sgr.parse_sgr_parameters(parameters), None)
    background = _depth.DEFAULT_CHANNEL if spec is None else _depth.channels(spec)[1]
    if background == _depth.rgb(*_PROBE_RGB):
        return 16777216
    if background == _depth.Channel(_depth.Kind.INDEX_256, _PROBE_ENTRY):
        return 256
    return None


def _properties_from_capabilities(capabilities: Iterable[tuple[str, str | None]]) -> tuple[_ColorCount | None, bool]:
    """Return what the capabilities of an XTGETTCAP reply show the terminal draws.

    :param capabilities: ``(name, value)`` pairs, the value None for a capability the terminal lacks.
    :returns: the colour count ``colors``, ``RGB`` and ``Tc`` allow,
        None when they allow fewer than 8 colours or are not given;
        and whether ``Smulx`` or ``Setulc`` is there.
        ``RGB`` counts only without a value or with one that names the bits per component, such as ``8`` or
        ``8/8/8``: xterm answers ``-1`` when it stores colours in its palette.
    """
    colors: int | None = None
    underline_styles = False
    for name, value in capabilities:
        if value is None:
            continue
        if (name == "RGB" and (not value or _RGB_BITS.fullmatch(value))) or name == "Tc":
            colors = 16777216
        elif name == "colors" and value.isascii() and value.isdigit() and len(value) <= 9 and colors is None:
            colors = int(value)
        elif name in {"Smulx", "Setulc"}:
            underline_styles = True
    if colors is None:
        return None, underline_styles
    return next((count for minimum, count in _TERMINFO_COLOR_COUNTS if colors >= minimum), None), underline_styles


def _terminfo_colors(term: str, environ: Mapping[str, str]) -> _ColorCount | None:
    """Return the colour count the terminfo entry of *term* allows, as :func:`_terminfo_entry` finds the entry.

    :returns: the colour count, or None when no valid entry is found or it allows fewer than 8 colours.
    """
    if (data := _terminfo_entry(term, environ)) is None or (colors := _parse_terminfo_colors(data)) is None:
        return None
    return next((count for minimum, count in _TERMINFO_COLOR_COUNTS if colors >= minimum), None)


def _environment_colors(environ: Mapping[str, str]) -> _ColorCount | None:
    """Return the colour count an explicit setting in *environ* decides, None when it decides none.

    The settings are ``NO_COLOR``, then ``FORCE_COLOR`` / ``CLICOLOR_FORCE``, then ``CLICOLOR=0``.
    A count they decide is the user's choice, which no terminal reply changes.

    >>> _environment_colors({"NO_COLOR": "1"}), _environment_colors({"FORCE_COLOR": "2"}), _environment_colors({})
    (1, 256, None)
    """
    force = environ.get("FORCE_COLOR") or environ.get("CLICOLOR_FORCE")
    if environ.get("NO_COLOR") or (environ.get("CLICOLOR") == "0" and not force):
        return 1
    if force:
        return _parse_force_color(force)
    return None


def detect_term_colors(
    term: str | None = None,
    environ: Mapping[str, str] | None = None,
    *,
    windows_version: tuple[int, int, int] | None = None,
) -> _ColorCount:
    """Detect the colour count of the terminal.

    Sources, the first that decides wins:

    - ``NO_COLOR``, then ``FORCE_COLOR`` / ``CLICOLOR_FORCE``, then ``CLICOLOR=0``.
    - A monochrome TERM such as ``dumb``.
    - Windows 10 from build 14931, which has 24-bit colours.
    - The Windows 10 console from build 10586, which has 256 colours.
    - TERM itself.

    TERM gives a count by its name, matched by family so ``gnome-256color``, ``konsole-direct``
    and ``rxvt-unicode-256color`` are recognized.
    The ``colors`` capability of its terminfo entry raises that count and never lowers it.
    Variables that name a terminal, such as ``COLORTERM`` or ``WT_SESSION``, are not read: a terminal or multiplexer
    started inside another one inherits them. The raw screen raises the count from the terminal's own replies instead.
    The entry is searched in the ``TERMINFO``, ``$HOME/.terminfo`` and ``TERMINFO_DIRS`` directories of *environ*,
    then in the system terminfo directories; native Windows has no terminfo lookup.

    :param term: the terminal name; ``TERM`` from *environ* when None.
    :param environ: the environment; :data:`os.environ` when None.
    :param windows_version: the Windows version as (major, minor, build); the running system's when None.
    :returns: the colour count: 1, 16, 88, 256 or 16777216.

    >>> detect_term_colors("xterm", {"FORCE_COLOR": "3"})
    16777216
    >>> detect_term_colors("xterm-256color", {"NO_COLOR": "1"})
    1
    """
    env = os.environ if environ is None else environ
    if (override := _environment_colors(env)) is not None:
        return override
    term_value = env.get("TERM", "") if term is None else term
    term_colors = _colors_from_term(term_value, _term_families(term_value))
    # The name rules know hosts whose entries understate them, such as the truecolor families.
    if (terminfo_colors := _terminfo_colors(term_value, env)) is not None:
        term_colors = max(term_colors, terminfo_colors)
    if term_colors == 1:
        return 1
    win_colors = _windows_console_colors(_windows_version() if windows_version is None else windows_version)
    return max(term_colors, win_colors or 1)


def detect_terminal_properties(
    term: str | None = None,
    environ: Mapping[str, str] | None = None,
    *,
    windows_version: tuple[int, int, int] | None = None,
) -> TerminalProperties:
    """Detect raw-display capabilities from TERM, its terminfo entry and the colour settings in the environment.

    The colour count comes from :func:`detect_term_colors`.
    TERM names are matched by family, so ``screen.xterm-256color`` is treated as both screen and xterm.

    On Windows 10 from build 10586 the console VT host draws bright colours without bold and draws underlines,
    under any TERM but the Linux console's.
    """
    env = os.environ if environ is None else environ
    term_value = env.get("TERM", "") if term is None else term
    families = _term_families(term_value)
    term_l = term_value.lower()
    if windows_version is None:
        windows_version = _windows_version()
    win_colors = _windows_console_colors(windows_version)
    vt_host = win_colors in {256, 16777216}

    has_underline = not bool(families & _NO_UNDERLINE_FAMILIES)
    linux_console = _is_linux_console(term_value)
    # ms-terminal is Windows Terminal; the other ms-* entries name older Microsoft consoles, most with 8 colours
    fg_bright_is_bold = not (families & _INDEPENDENT_BRIGHT_FAMILIES or term_l.startswith("ms-terminal"))
    if vt_host and not linux_console:
        fg_bright_is_bold = False
        has_underline = True
    bg_bright_is_blink = linux_console
    back_color_erase = "bce" in term_l or not families & {"screen", "dumb", "unknown"}

    return TerminalProperties(
        colors=detect_term_colors(term_value, env, windows_version=windows_version),
        has_underline=has_underline,
        fg_bright_is_bold=fg_bright_is_bold,
        bg_bright_is_blink=bg_bright_is_blink,
        back_color_erase=back_color_erase,
        underline_styles=_has_underline_styles(term_value, env),
    )


def _has_underline_styles(term: str, environ: Mapping[str, str]) -> bool:
    """Return whether the terminfo entry of *term* says the terminal draws underline styles and underline colors.

    The styles are SGR 4:2 to 4:5 and the colors SGR 58; the entry says so with ``Smulx`` or ``Setulc``.
    """
    if (data := _terminfo_entry(term, environ)) is None:
        return False
    try:
        return bool(_parse_terminfo_extended_names(data) & {"Smulx", "Setulc"})
    except ValueError:  # an entry the colour count was read from, with a malformed extended section
        return False

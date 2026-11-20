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

"""The results :class:`AnsiParser` returns: parsed lines, their character sets and the skipped sequences."""

from __future__ import annotations

import dataclasses
import typing

from urwid.display.escape import DEC_TAG

if typing.TYPE_CHECKING:
    from collections.abc import Hashable

    from urwid.display import AttrSpec


#: The final byte of a G0/G1 designation that selects US ASCII.
_ASCII_SET: typing.Final = "B"


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class SkippedOp:
    """A single escape-sequence (or control character) that was recognised but stripped.

    Such a sequence is stripped from the resolved text rather than interpreted, because it has no meaning outside a
    full two-dimensional terminal canvas.

    :ivar kind: one of ``"vertical-move"``, ``"terminal-setting"`` or ``"unknown"``.
    :ivar raw: the raw sequence text as encountered (including its ``ESC``/``CSI`` framing), truncated for a sequence
        skipped for its length.
    :ivar reason: a human-readable explanation, used verbatim in the log message emitted alongside this entry.
    """

    kind: str
    raw: str
    reason: str


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class CharsetState:
    """The character sets designated to G0 and G1, and the one selected, at the end of a parsed line.

    :ivar g0: the final byte of the G0 designation: ``"B"`` for US ASCII, ``"0"`` for DEC Special Graphics.
    :ivar g1: the final byte of the G1 designation, in the same form.
    :ivar selected: ``0`` when G0 is selected (SI), ``1`` when G1 is (SO).
    :raises ValueError: *selected* is neither ``0`` nor ``1``.
    """

    g0: str = _ASCII_SET
    g1: str = DEC_TAG
    selected: typing.Literal[0, 1] = 0

    def __post_init__(self) -> None:
        """Refuse a selected slot other than G0 or G1."""
        if self.selected not in {0, 1}:
            raise ValueError(f"selected must be 0 (G0) or 1 (G1), not {self.selected!r}")


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class ParsedLine:
    r"""The result of parsing one physical line of ANSI-coloured text.

    :ivar text: the resolved, escape-free text of this line. When produced by :class:`AnsiParser` constructed with
        ``one_line=True`` (or :func:`parse_ansi_line`), this is guaranteed never to contain a ``\n`` -- line ends
        are structural split points that produce *separate* :class:`ParsedLine` instances. That invariant is
        deliberately **not** upheld when :class:`AnsiParser` is constructed with ``one_line=False`` (or by
        :func:`parse_ansi_text`): since that mode resolves a whole multi-row block into a single :class:`ParsedLine`,
        its ``text`` legitimately contains embedded ``\n`` characters, one per row boundary, by design.
    :ivar attrib: run-length encoded display attributes for :attr:`text`, the same shape as
        :attr:`urwid.Text.attrib`. ``None`` is a valid RLE tag (meaning "no attribute"), matching
        :func:`urwid.util.decompose_tagmarkup`'s convention.
    :ivar last_attr: the SGR/colour state in effect at the end of this line.
    :ivar bel: the number of BEL (``\a``) characters seen on this line (``0`` if none were seen).
    :ivar title: the last OSC window-title string seen on this line, or ``None`` if none was seen.
    :ivar leds: the last keyboard-LED state requested on this line (``CSI n q``), or ``None`` if none was seen.
    :ivar skipped: the :class:`SkippedOp` entries stripped while parsing this line, in encounter order, for
        programmatic inspection independent of the log. It holds at most the first 65536 of them.
    :ivar last_charsets: the character sets in effect at the end of this line.

    Pass the line itself as ``previous_attr`` to continue both :attr:`last_attr` and :attr:`last_charsets` into a
    subsequently parsed line; passing :attr:`last_attr` alone starts that line with the default character sets.
    """

    text: str
    attrib: list[tuple[Hashable, int]]
    last_attr: AttrSpec | None
    bel: int = 0
    title: str | None = None
    leds: str | None = None
    skipped: list[SkippedOp] = dataclasses.field(default_factory=list)
    last_charsets: CharsetState = CharsetState()

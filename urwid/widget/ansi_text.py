# Urwid ANSI-coloured text widget
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
"""A read-only widget rendering a block of ANSI/VT100-coloured text, optionally restricted to a single line."""

from __future__ import annotations

import typing

from urwid.ansi_parser import AnsiParser

from .constants import Align, WrapMode
from .text import Text
from .widget import WidgetWrap

if typing.TYPE_CHECKING:
    from collections.abc import Hashable, Iterable, Iterator

    from typing_extensions import Literal

    from urwid.ansi_parser import ParsedLine
    from urwid.display import AttrSpec

__all__ = ("ANSIText",)


class ANSIText(WidgetWrap[Text]):
    """A read-only widget interpreting ANSI/VT100 colour, horizontal and (optionally) vertical movement escapes.

    It acts almost exactly like a read-only :class:`~urwid.Text` widget for the resolved, escape-free content.

    Parsing is delegated to :class:`urwid.ansi_parser.AnsiParser`, and layout (wrapping, alignment, packing and
    rendering) is delegated to an internal :class:`~urwid.Text` instance that this widget wraps via
    :class:`~urwid.WidgetWrap`, so this widget's ``pack``/``render``/``rows`` behaviour is identical to
    :class:`~urwid.Text` for the same resolved characters, without needing to forward those calls by hand.

    By default (``one_line=False``), a newline genuinely starts a new row, ``CSI n A``/``B`` genuinely moves the
    cursor up/down between rows, and a bare ``\\r`` genuinely overwrites the current row in place (letting
    progress-bar-style redraw sequences resolve correctly) -- ``ansi_text`` is treated as a single, complete block,
    meant to render one already-complete captured screen/block.

    Pass ``one_line=True`` to restrict this widget to a single physical line of resolved text; see
    :class:`~urwid.ansi_parser.AnsiParser`'s ``one_line`` flag for the underlying parsing semantics. In this mode,
    line ends and vertical cursor movement are treated as meaningless outside a single line (stripped/split rather
    than resolved into rows): since the underlying parser always
    returns a ``tuple[ParsedLine, ...]`` in this mode (line-end characters are structural split points, never
    silently discarded), constructing an :class:`ANSIText` directly from text containing an embedded line end only
    surfaces the *first* resulting line -- no data is lost (the full split is always computed), but only the first
    line is exposed by this widget instance. Use :meth:`from_lines` to turn arbitrary multi-line (or arbitrarily
    chunked) raw text into a complete sequence of :class:`ANSIText` instances, in either mode.

    >>> ANSIText("hello")
    <ANSIText fixed/flow widget 'hello'>
    >>> ANSIText("a\\nb").text
    'a\\nb'
    >>> ANSIText("a\\nb", one_line=True).text
    'a'
    """

    def __init__(
        self,
        ansi_text: str,
        previous_attr: AttrSpec | None = None,
        *,
        one_line: bool = False,
        wrap: Literal["space", "any", "clip", "ellipsis"] | WrapMode = WrapMode.SPACE,
        align: Literal["left", "center", "right"] | Align = Align.LEFT,
    ) -> None:
        """
        :param ansi_text: a block of text, optionally spanning several lines and containing ANSI/VT100 escape
            sequences. If ``one_line`` is true, only its first physical line is surfaced by this widget instance.
        :param previous_attr: SGR/colour state to carry in from previously parsed text (see :attr:`last_attr`).
        :param one_line: restrict this widget to a single physical line of resolved text rather than resolving the
            whole block into multi-row output.
        :param wrap: forwarded to the internal :class:`~urwid.Text`.
        :param align: forwarded to the internal :class:`~urwid.Text`.
        """
        self._one_line = one_line
        super().__init__(Text("", align=align, wrap=wrap))
        self.set_ansi_text(ansi_text, previous_attr)

    def _repr_words(self) -> list[str]:
        first = super()._repr_words()
        return [*first, repr(self.text)]

    def set_ansi_text(self, ansi_text: str, previous_attr: AttrSpec | None = None) -> None:
        """Re-parse ``ansi_text`` and invalidate this widget.

        Parsing uses the mode (``one_line``) this widget was constructed with; if ``one_line`` is true, only the
        first resulting line is used, see the class docstring.

        :param ansi_text: a block of text, optionally spanning several lines and containing ANSI/VT100 escape
            sequences.
        :param previous_attr: SGR/colour state to carry in from previously parsed text (see :attr:`last_attr`).
        """
        parser = AnsiParser(previous_attr, one_line=self._one_line)
        parser.feed(ansi_text)
        self._set_parsed(parser.finalize()[0])

    def _set_parsed(self, parsed: ParsedLine) -> None:
        self._parsed = parsed
        self._w.set_text(self._build_markup(parsed))
        self._invalidate()

    @staticmethod
    def _build_markup(parsed: ParsedLine) -> list[tuple[Hashable, str]]:
        markup: list[tuple[Hashable, str]] = []
        pos = 0
        for attr, run in parsed.attrib:
            markup.append((attr, parsed.text[pos : pos + run]))
            pos += run
        return markup

    def get_text(self) -> tuple[str | bytes, list[tuple[Hashable, int]]]:
        """
        :returns: (*text*, *display attributes*), see :meth:`urwid.Text.get_text`.
        """
        return self._w.get_text()

    @property
    def text(self) -> str | bytes:
        """Read-only property returning the resolved, escape-free text of this widget (may contain ``\\n``)."""
        return self.get_text()[0]

    @property
    def attrib(self) -> list[tuple[Hashable, int]]:
        """Read-only property returning the run-length encoded display attributes of this widget's text."""
        return self.get_text()[1]

    @property
    def last_attr(self) -> AttrSpec | None:
        """The SGR/colour state in effect at the very end of this widget's text.

        Feed this in as ``previous_attr`` to a subsequently constructed :class:`ANSIText` to continue the same
        colour state.
        """
        return self._parsed.last_attr

    @property
    def bel(self) -> int:
        """The number of BEL characters seen (aggregated over the whole block unless ``one_line`` is true)."""
        return self._parsed.bel

    @property
    def title(self) -> str | None:
        """The last OSC window-title string seen, if any."""
        return self._parsed.title

    @property
    def leds(self) -> str | None:
        """The last keyboard-LED state requested, if any."""
        return self._parsed.leds

    @classmethod
    def _from_parsed(
        cls,
        parsed: ParsedLine,
        *,
        one_line: bool,
        wrap: Literal["space", "any", "clip", "ellipsis"] | WrapMode = WrapMode.SPACE,
        align: Literal["left", "center", "right"] | Align = Align.LEFT,
    ) -> ANSIText:
        """Construct an :class:`ANSIText` directly from an already-parsed :class:`~urwid.ansi_parser.ParsedLine`.

        Bypasses re-parsing. Used internally by :meth:`from_lines`.

        :param parsed: the already-parsed line to build the widget from.
        :param one_line: the mode this widget instance should remember itself as having been parsed in, so that a
            later :meth:`set_ansi_text` call re-parses consistently.
        :param wrap: forwarded to the internal :class:`~urwid.Text`.
        :param align: forwarded to the internal :class:`~urwid.Text`.
        :returns: a new :class:`ANSIText` wrapping ``parsed``.
        """
        obj = cls.__new__(cls)
        obj._one_line = one_line
        WidgetWrap.__init__(obj, Text("", align=align, wrap=wrap))
        obj._set_parsed(parsed)
        return obj

    @classmethod
    def from_lines(
        cls,
        chunks: Iterable[str],
        previous_attr: AttrSpec | None = None,
        *,
        one_line: bool = False,
        **kwargs: typing.Any,
    ) -> Iterator[ANSIText]:
        """Consume raw ANSI text chunks and yield the resulting :class:`ANSIText` widget(s).

        ``chunks`` (e.g. successive ``os.read()`` results from a subprocess) are **not** required to be pre-split
        on line boundaries, and each chunk may contain zero, one, or several line ends. Internally accumulates a
        single :class:`~urwid.ansi_parser.AnsiParser` across all chunks, so a line split across two chunk
        boundaries -- or an escape sequence split across two chunk boundaries -- is still resolved correctly, and
        calls :meth:`~urwid.ansi_parser.AnsiParser.finalize` only once the iterable is exhausted.

        If ``one_line`` is true, one :class:`ANSIText` is yielded per line the shared parser completes, in order,
        with SGR colour state carried forward continuously: each produced :class:`ANSIText`'s ``previous_attr`` is
        the previous one's :attr:`last_attr`, whether that previous line came from the same chunk or an earlier
        one.

        If ``one_line`` is false (the default), this naturally reduces to yielding exactly *one* :class:`ANSIText`
        once every chunk has been consumed, representing the entire accumulated multi-chunk block resolved into
        real multi-row output -- the "normal multiline" case, reached through the same code path as the
        ``one_line=True`` case rather than a separate one.

        :param chunks: an iterable of raw text chunks, not required to be aligned on line or escape-sequence
            boundaries.
        :param previous_attr: SGR/colour state to seed the shared parser with, as if it were carried over from
            previously parsed text.
        :param one_line: parse in single-line-splitting mode (see the class docstring) rather than resolving the
            whole accumulated input into one multi-row block.
        :param kwargs: forwarded to :meth:`_from_parsed` (i.e. ``wrap``/``align`` for the internal
            :class:`~urwid.Text`).
        :returns: an iterator yielding one or more :class:`ANSIText` instances, in order, depending on ``one_line``.
        """
        parser = AnsiParser(previous_attr, one_line=one_line)
        for chunk in chunks:
            parser.feed(chunk)
        for parsed in parser.finalize():
            yield cls._from_parsed(parsed, one_line=one_line, **kwargs)

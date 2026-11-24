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


"""Raw display :class:`Screen`, the top layer that draws canvases on the terminal."""

from __future__ import annotations

import errno
import re
import typing

from urwid import str_util, util
from urwid.display import escape
from urwid.display._raw_display_base._detection import IS_WINDOWS
from urwid.display._raw_display_base._input import _InputScreen
from urwid.display.common import (
    UNPRINTABLE_C1_TRANS_TABLE,
    UNPRINTABLE_TRANS_TABLE,
)

if typing.TYPE_CHECKING:
    from collections.abc import Hashable
    from typing import Literal

    from urwid import Canvas


# the start of a raw sequence in a charset "U" run: ESC or a C1 control as UTF-8, and only ESC in the
# single and double byte encodings, where bytes 0x80-0x9f are glyphs of the IBM PC character set or parts of characters
_RAW_SEQUENCE_UTF8 = re.compile(rb"\x1b|\xc2[\x80-\x9f]")
_RAW_SEQUENCE_BYTES = re.compile(rb"\x1b")


class Screen(_InputScreen):  # pylint: disable=abstract-method  # a platform screen completes it
    """Shared base for the raw POSIX and Windows screen backends that talk directly to the terminal."""

    __slots__ = ()

    def _setup_G1(self) -> None:
        """Initialize the G1 character set to graphics mode if required.

        :raises OSError: the terminal could not be written to. The setup is tried again on the next draw.
        """
        if self._setup_G1_done:
            return

        self.write(escape.DESIGNATE_G1_SPECIAL)
        self.flush()
        self._setup_G1_done = True

    def draw_screen(self, size: tuple[int, int], canvas: Canvas) -> None:
        """Paint screen with rendered canvas.

        A frame whose write fails is drawn whole again by the next call, even for the same canvas,
        since part of it may have reached the terminal.

        :raises RuntimeError: the screen has not been started.
        :raises ValueError: *canvas* does not have the number of rows given by *size*.
        :raises OSError: the terminal could not be written to, for a reason other than an interrupted system call.
        """
        # the settings cannot change during a draw
        properties = self._terminal_properties

        def set_cursor_position(x: int, y: int) -> str:
            if self._rows_used is None:
                return escape.set_cursor_position(x, y)
            if cy > y:
                return "\b" + escape.CURSOR_HOME_COL + escape.move_cursor_up(cy - y) + escape.move_cursor_right(x)
            return "\b" + escape.CURSOR_HOME_COL + escape.move_cursor_down(y - cy) + escape.move_cursor_right(x)

        def handle_row(
            attr: Hashable,
            charset: Literal["0", "U"] | None,
            run: bytes,
            last: bool,
        ) -> None:
            """Append the escape sequences and text of one canvas run to the output.

            The bytes of a charset "U" run are written unchanged, OSC 8 sequences included:
            they belong to the application, and urwid's own hyperlinks only wrap attribute-linked runs.

            :raises TypeError: *run* is not a byte string.
            :raises ValueError: *charset* is not a known character set flag.
            """
            nonlocal last_charset_flag, last_attributes, first, link_open, rendition  # type: ignore[misc]

            if not isinstance(run, bytes):  # canvases render with bytes
                raise TypeError(run)

            if charset != "U":
                run = run.translate(UNPRINTABLE_TRANS_TABLE)

            if last_attributes != attr:
                attr_rendition, attr_link = self._attr_escape_parts(attr)
                attr_escape = attr_rendition + attr_link
                rendition = attr_rendition
                if properties.hyperlinks:
                    # only an escape that opens a hyperlink ends with ST, and an open replaces any open link
                    opens = attr_escape.endswith(escape.ST)
                    if link_open and not opens:
                        output.append(escape.HYPERLINK_CLOSE)
                    link_open = opens
                output.append(attr_escape)
                last_attributes = attr

            if last:
                output.append("\x08" * back)

            if encoding != "utf-8" and (first or last_charset_flag != charset):
                if charset not in {None, "0", "U"}:
                    raise ValueError(charset)
                if last_charset_flag == "U":
                    output.append(escape.IBMPC_OFF)

                if charset is None:
                    icss = escape.SI
                elif charset == "U":
                    icss = escape.IBMPC_ON
                else:
                    icss = escape.SO

                output.append(icss)

                last_charset_flag = charset

            line_text = run.decode(encoding, "replace")
            if charset != "U" and not line_text.isascii():
                line_text = line_text.translate(UNPRINTABLE_C1_TRANS_TABLE)

            if not last:
                output.append(line_text)
            else:
                if not IS_WINDOWS:
                    output.extend((escape.INSERT_ON, line_text, escape.INSERT_OFF))
                else:
                    output.extend((f"{escape.CSI}{str_util.calc_width(line_text, 0, len(line_text))}@", line_text))

                if encoding != "utf-8" and charset == "U":
                    output.append(escape.IBMPC_OFF)

            if properties.hyperlinks and charset == "U":
                # the run may have closed or replaced urwid's hyperlink, so the next run reopens its own
                last_attributes = link_closed
            if charset == "U" and run:
                # the run may carry SGR sequences of its own
                rendition = None

            first = False

        encoding = util.get_encoding()

        logger = self.logger.getChild("draw_screen")

        (maxcol, maxrow) = size

        if not self._started:
            raise RuntimeError

        if maxrow != canvas.rows():
            raise ValueError(maxrow)

        # quick return if nothing has changed
        if self.screen_buf and canvas is self._screen_buf_canvas:
            return

        self._setup_G1()

        if self._resized:
            # handle resize before trying to draw screen
            logger.debug("Not drawing screen: screen resized and resize was not handled")
            return

        logger.debug(f"Drawing screen with size {size!r}")

        last_attributes: Hashable = None  # Default = empty
        # last_attributes after a hyperlink is closed: unequal to every attribute, so the next run reopens its link
        link_closed = object()
        # whether the output has a hyperlink open that urwid opened
        link_open = False

        output: list[str] = [escape.HIDE_CURSOR, self._attr_to_escape(last_attributes)]
        # the SGR sequence written last, which the terminal is left in; None after a raw run that may change it
        rendition: str | None = self._attr_escape_parts(last_attributes)[0]

        if self._rows_used is None:
            output.append(escape.CURSOR_HOME)

        osb: list[list[tuple[str, Literal["0", "U"] | None, bytes]]] = self._drawn_rows if self.screen_buf else []
        sb: list[list[tuple[Hashable, Literal["0", "U"] | None, bytes]]] = []
        drawn_rows: list[list[tuple[str, Literal["0", "U"] | None, bytes]]] = []
        cy = self._cy
        y = -1

        ins: list[tuple[Hashable, Literal["0", "U"] | None, bytes]] = []
        if self._rows_used is None:
            output.append(escape.set_cursor_position(0, 0))
        else:
            output.append(escape.CURSOR_HOME_COL + escape.move_cursor_up(cy))
        cy = 0

        first = True
        last_charset_flag: Literal["0", "U"] | None = None

        for row in canvas.content():
            y += 1
            drawn_row: list[tuple[str, Literal["0", "U"] | None, bytes]] = [
                (self._attr_to_escape(a), cs, run) for a, cs, run in row
            ]
            sb.append(row)
            drawn_rows.append(drawn_row)
            if osb and y < len(osb) and osb[y] == drawn_row:
                # this row of the screen buffer matches what is
                # currently displayed, so we can skip this line
                continue

            # leave blank lines off display when we are using
            # the default screen buffer (allows partial screen)
            if self._rows_used is not None and y > self._rows_used:
                if len(row) == 1 and not row[0][2].strip():
                    continue
                self._rows_used = y

            if y or self._rows_used is not None:
                output.append(set_cursor_position(0, y))
            # after updating the line we will be just over the
            # edge, but terminals still treat this as being
            # on the same line
            cy = y

            whitespace_at_end = False
            back = 0

            if row:
                a, cs, run = row[-1]
                if (
                    run[-1:] == b" "
                    and properties.back_color_erase
                    and not (
                        (pal_a := self._drawn_spec(a)).standout
                        or pal_a.underline
                        or (properties.hyperlinks and pal_a.hyperlink is not None and pal_a.hyperlink.uri)
                    )
                ):
                    whitespace_at_end = True
                    row = [*row[:-1], (a, cs, run.rstrip(b" "))]  # noqa: PLW2901
                elif y == maxrow - 1 and maxcol > 1:
                    row, back, ins = self._last_row(row)  # noqa: PLW2901
            else:
                continue

            for a, cs, run in row:
                handle_row(a, cs, run, last=False)

            if ins:
                a, cs, run = ins[0]
                handle_row(a, cs, run, last=True)
                # runs of no width between Y and Z follow Y, and add nothing to shift
                for a, cs, run in ins[1:]:
                    handle_row(a, cs, run, last=False)

            if link_open:
                # a hyperlink left open would cover the cursor moves and erased cells up to the next run
                output.append(escape.HYPERLINK_CLOSE)
                link_open = False
                last_attributes = link_closed

            if whitespace_at_end:
                output.append(escape.ERASE_IN_LINE_RIGHT)

        if canvas.cursor is not None:
            x, y = canvas.cursor
            output += [set_cursor_position(x, y), escape.SHOW_CURSOR]
            self._cy = y

        if self._resized:
            # handle resize before trying to draw screen
            return
        try:
            # A single write() call, rather than one per output fragment, avoids paying the
            # per-call overhead (and, for a real file, a separate write syscall) once per row.
            frame = "".join(output)
            if self.modes.synchronized_output:
                # Confirmed supported; the terminal defers painting until END_SYNCHRONIZED_UPDATE.
                frame = (
                    f"{escape.PrivateMode.SYNCHRONIZED_OUTPUT.enable_seq}"
                    f"{frame}"
                    f"{escape.PrivateMode.SYNCHRONIZED_OUTPUT.disable_seq}"
                )
            self.write(frame)
            self.flush()
        except OSError as e:
            # part of the frame may have reached the terminal, so neither the rows nor the rendition are known
            self._rendition = None
            self.screen_buf = None
            self._screen_buf_canvas = None
            # ignore interrupted syscall
            if e.args[0] != errno.EINTR:
                raise
            return

        self.screen_buf = sb
        self._drawn_rows = drawn_rows
        self._screen_buf_canvas = canvas
        self._rendition = rendition
        self._send_color_probe()

    def _last_row(
        self,
        row: list[tuple[Hashable, Literal["0", "U"] | None, bytes]],
    ) -> tuple[
        list[tuple[Hashable, Literal["0", "U"] | None, bytes]],
        int,
        list[tuple[Hashable, Literal["0", "U"] | None, bytes]],
    ]:
        """On the last row we need to slide the bottom right character into place.

        eg. last row:
        XXXXXXXXXXXXXXXXXXXXYZ

        Y will be drawn after Z, shifting Z into position.

        Runs of no width, such as a bidi mark or a combining mark, are neither Y nor Z:
        those after Z are drawn after Z, and those between Y and Z are written after Y
        is inserted, so each stays behind the character it follows.

        The row is returned untouched, with nothing to insert and its bottom right
        character written directly, when:

        - nothing of any width comes before Z, as happens with a double width
          character on a two column screen, so there is no Y to draw after Z;
        - a non-empty run of no width in charset "U" comes after Y;
        - Y or Z is taken from a charset "U" run holding the start of a raw sequence.

        A charset "U" run holds the application's raw bytes. The column count can read
        the parameters of an escape sequence there as text and cut it, and the sequence,
        such as an OSC 8 hyperlink, applies to what is written after it, so moving it
        around Y would change what it applies to.

        :returns: the row to draw, the columns to move back over Z, and the runs to insert, Y first.
        """
        end = len(row)
        while end > 1 and not str_util.calc_width(row[end - 1][2], 0, len(row[end - 1][2])):
            end -= 1
        tail = row[end:]

        raw_sequence = _RAW_SEQUENCE_UTF8 if str_util.get_byte_encoding() == "utf8" else _RAW_SEQUENCE_BYTES
        z_attr, z_cs, last_text = row[end - 1]
        if z_cs == "U" and raw_sequence.search(last_text):
            return row, 0, []
        last_cols = str_util.calc_width(last_text, 0, len(last_text))
        last_offs, _ = str_util.calc_text_pos(last_text, 0, len(last_text), last_cols - 1)
        z_text = last_text[last_offs:]
        head = row[: end - 1]
        if last_offs:
            head.append((z_attr, z_cs, last_text[:last_offs]))

        y_end = len(head)
        while y_end and not str_util.calc_width(head[y_end - 1][2], 0, len(head[y_end - 1][2])):
            y_end -= 1
        if not y_end or any(cs == "U" and run for _, cs, run in (*head[y_end:], *tail)):
            return row, 0, []

        y_attr, y_cs, y_run = head[y_end - 1]
        if y_cs == "U" and raw_sequence.search(y_run):
            return row, 0, []
        y_cols = str_util.calc_width(y_run, 0, len(y_run))
        y_offs, _ = str_util.calc_text_pos(y_run, 0, len(y_run), y_cols - 1)
        new_row = head[: y_end - 1]
        if y_offs:
            new_row.append((y_attr, y_cs, y_run[:y_offs]))
        new_row.append((z_attr, z_cs, z_text))
        new_row.extend(tail)
        # Z is drawn where Y starts, so move back over Z to insert Y in front of it
        return new_row, str_util.calc_width(z_text, 0, len(z_text)), [(y_attr, y_cs, y_run[y_offs:]), *head[y_end:]]

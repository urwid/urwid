from __future__ import annotations

import typing

from urwid.canvas import CanvasCombine, CompositeCanvas, SolidCanvas
from urwid.util import get_encoding_mode

from .constants import BAR_SYMBOLS, Sizing
from .text import Text
from .widget import Widget, WidgetError, WidgetMeta, nocache_widget_render, nocache_widget_render_instance

if typing.TYPE_CHECKING:
    from typing_extensions import Literal


class BarGraphMeta(WidgetMeta):
    """
    Detect subclass get_data() method and dynamic change to
    get_data() method and disable caching in these cases.

    This is for backwards compatibility only, new programs
    should use set_data() instead of overriding get_data().
    """

    def __init__(cls, name, bases, d):
        # pylint: disable=protected-access

        super().__init__(name, bases, d)

        if "get_data" in d:
            cls.render = nocache_widget_render(cls)
            cls._get_data = cls.get_data
        cls.get_data = property(lambda self: self._get_data, nocache_bargraph_get_data)


def nocache_bargraph_get_data(self, get_data_fn):
    """
    Disable caching on this bargraph because get_data_fn needs
    to be polled to get the latest data.
    """
    self.render = nocache_widget_render_instance(self)
    self._get_data = get_data_fn  # pylint: disable=protected-access


class BarGraphError(WidgetError):
    pass


class BarGraph(Widget, metaclass=BarGraphMeta):
    _sizing = frozenset([Sizing.BOX])

    ignore_focus = True

    eighths = BAR_SYMBOLS.VERTICAL[:8]  # Full height is done by style
    hlines = "_⎺⎻─⎼⎽"

    def __init__(self, attlist, hatt=None, satt=None) -> None:
        """
        Create a bar graph with the passed display characteristics.
        see set_segment_attributes for a description of the parameters.
        """
        super().__init__()
        self.set_segment_attributes(attlist, hatt, satt)
        self.set_data([], 1, None)
        self.set_bar_width(None)

    def set_segment_attributes(self, attlist, hatt=None, satt=None):
        """
        :param attlist: list containing display attribute or
                        (display attribute, character) tuple for background,
                        first segment, and optionally following segments.
                        ie. len(attlist) == num segments+1
                        character defaults to ' ' if not specified.
        :param hatt: list containing attributes for horizontal lines. First
                     element is for lines on background, second is for lines
                     on first segment, third is for lines on second segment
                     etc.
        :param satt: dictionary containing attributes for smoothed
                     transitions of bars in UTF-8 display mode. The values
                     are in the form:

                       (fg,bg) : attr

                     fg and bg are integers where 0 is the graph background,
                     1 is the first segment, 2 is the second, ...
                     fg > bg in all values.  attr is an attribute with a
                     foreground corresponding to fg and a background
                     corresponding to bg.

        If satt is not None and the bar graph is being displayed in
        a terminal using the UTF-8 encoding then the character cell
        that is shared between the segments specified will be smoothed
        with using the UTF-8 vertical eighth characters.

        eg: set_segment_attributes( ['no', ('unsure',"?"), 'yes'] )
        will use the attribute 'no' for the background (the area from
        the top of the graph to the top of the bar), question marks
        with the attribute 'unsure' will be used for the topmost
        segment of the bar, and the attribute 'yes' will be used for
        the bottom segment of the bar.
        """
        self.attr = []
        self.char = []
        if len(attlist) < 2:
            raise BarGraphError(f"attlist must include at least background and seg1: {attlist!r}")
        if len(attlist) < 2:
            raise BarGraphError("must at least specify bg and fg!")
        for a in attlist:
            if not isinstance(a, tuple):
                self.attr.append(a)
                self.char.append(" ")
            else:
                attr, ch = a
                self.attr.append(attr)
                self.char.append(ch)

        self.hatt = []
        if hatt is None:
            hatt = [self.attr[0]]
        elif not isinstance(hatt, list):
            hatt = [hatt]
        self.hatt = hatt

        if satt is None:
            satt = {}
        for i in satt.items():
            try:
                (fg, bg), attr = i
            except ValueError as exc:
                raise BarGraphError(f"satt not in (fg,bg:attr) form: {i!r}").with_traceback(exc.__traceback__) from exc
            if not isinstance(fg, int) or fg >= len(attlist):
                raise BarGraphError(f"fg not valid integer: {fg!r}")
            if not isinstance(bg, int) or bg >= len(attlist):
                raise BarGraphError(f"bg not valid integer: {fg!r}")
            if fg <= bg:
                raise BarGraphError(f"fg ({fg}) not > bg ({bg})")
        self.satt = satt

    def set_data(self, bardata, top: float, hlines=None) -> None:
        """
        Store bar data, bargraph top and horizontal line positions.

        bardata -- a list of bar values.
        top -- maximum value for segments within bardata
        hlines -- None or a bar value marking horizontal line positions

        bar values are [ segment1, segment2, ... ] lists where top is
        the maximal value corresponding to the top of the bar graph and
        segment1, segment2, ... are the values for the top of each
        segment of this bar.  Simple bar graphs will only have one
        segment in each bar value.

        Eg: if top is 100 and there is a bar value of [ 80, 30 ] then
        the top of this bar will be at 80% of full height of the graph
        and it will have a second segment that starts at 30%.
        """
        if hlines is not None:
            hlines = sorted(hlines[:], reverse=True)  # shallow copy

        self.data = bardata, top, hlines
        self._invalidate()

    def _get_data(self, size: tuple[int, int]):
        """
        Return (bardata, top, hlines)

        This function is called by render to retrieve the data for
        the graph. It may be overloaded to create a dynamic bar graph.

        This implementation will truncate the bardata list returned
        if not all bars will fit within maxcol.
        """
        (maxcol, maxrow) = size
        bardata, top, hlines = self.data
        widths = self.calculate_bar_widths((maxcol, maxrow), bardata)

        if len(bardata) > len(widths):
            return bardata[: len(widths)], top, hlines

        return bardata, top, hlines

    def set_bar_width(self, width: int | None):
        """
        Set a preferred bar width for calculate_bar_widths to use.

        width -- width of bar or None for automatic width adjustment
        """
        if width is not None and width <= 0:
            raise ValueError(width)
        self.bar_width = width
        self._invalidate()

    def calculate_bar_widths(self, size: tuple[int, int], bardata):
        """
        Return a list of bar widths, one for each bar in data.

        If self.bar_width is None this implementation will stretch
        the bars across the available space specified by maxcol.
        """
        (maxcol, _maxrow) = size

        if self.bar_width is not None:
            return [self.bar_width] * min(len(bardata), maxcol // self.bar_width)

        if len(bardata) >= maxcol:
            return [1] * maxcol

        widths = []
        grow = maxcol
        remain = len(bardata)
        for _row in bardata:
            w = int(float(grow) / remain + 0.5)
            widths.append(w)
            grow -= w
            remain -= 1
        return widths

    def selectable(self) -> Literal[False]:
        """
        Return False.
        """
        return False

    def use_smoothed(self) -> bool:
        return self.satt and get_encoding_mode() == "utf8"

    def calculate_display(self, size: tuple[int, int]):
        """
        Calculate display data.
        """
        (maxcol, maxrow) = size
        bardata, top, hlines = self.get_data((maxcol, maxrow))  # pylint: disable=no-member  # metaclass defined
        widths = self.calculate_bar_widths((maxcol, maxrow), bardata)

        if self.use_smoothed():
            disp = calculate_bargraph_display(bardata, top, widths, maxrow * 8)
            disp = self.smooth_display(disp)

        else:
            disp = calculate_bargraph_display(bardata, top, widths, maxrow)

        if hlines:
            disp = self.hlines_display(disp, top, hlines, maxrow)

        return disp

    def hlines_display(self, disp, top: int, hlines, maxrow: int):
        """
        Add hlines to display structure represented as bar_type tuple
        values:
        (bg, 0-5)
        bg is the segment that has the hline on it
        0-5 is the hline graphic to use where 0 is a regular underscore
        and 1-5 are the UTF-8 horizontal scan line characters.
        """
        if self.use_smoothed():
            shiftr = 0
            r = [
                (0.2, 1),
                (0.4, 2),
                (0.6, 3),
                (0.8, 4),
                (1.0, 5),
            ]
        else:
            shiftr = 0.5
            r = [
                (1.0, 0),
            ]

        # reverse the hlines to match screen ordering
        rhl = [rh for h in hlines if (rh := float(top - h) * maxrow / top - shiftr) >= 0]

        # build a list of rows that will have hlines
        hrows = []
        last_i = -1
        for rh in rhl:
            i = int(rh)
            if i == last_i:
                continue
            f = rh - i
            for spl, chnum in r:
                if f < spl:
                    hrows.append((i, chnum))
                    break
            last_i = i

        # fill hlines into disp data
        def fill_row(row, chnum):
            rout = []
            for bar_type, width in row:
                if isinstance(bar_type, int) and len(self.hatt) > bar_type:
                    rout.append(((bar_type, chnum), width))
                    continue
                rout.append((bar_type, width))
            return rout

        o = []
        k = 0
        rnum = 0
        for y_count, row in disp:
            if k >= len(hrows):
                o.append((y_count, row))
                continue
            end_block = rnum + y_count
            while k < len(hrows) and hrows[k][0] < end_block:
                i, chnum = hrows[k]
                if i - rnum > 0:
                    o.append((i - rnum, row))
                o.append((1, fill_row(row, chnum)))
                rnum = i + 1
                k += 1
            if rnum < end_block:
                o.append((end_block - rnum, row))
                rnum = end_block

        # assert 0, o
        return o

    def smooth_display(self, disp):
        """
        smooth (col, row*8) display into (col, row) display using
        UTF vertical eighth characters represented as bar_type
        tuple values:
        ( fg, bg, 1-7 )
        where fg is the lower segment, bg is the upper segment and
        1-7 is the vertical eighth character to use.
        """
        o = []
        r = 0  # row remainder

        def seg_combine(a, b):
            (bt1, w1), (bt2, w2) = a, b
            if (bt1, w1) == (bt2, w2):
                return (bt1, w1), None, None
            wmin = min(w1, w2)
            l1 = l2 = None
            if w1 > w2:
                l1 = (bt1, w1 - w2)
            elif w2 > w1:
                l2 = (bt2, w2 - w1)
            if isinstance(bt1, tuple):
                return (bt1, wmin), l1, l2
            if (bt2, bt1) not in self.satt:
                if r < 4:
                    return (bt2, wmin), l1, l2
                return (bt1, wmin), l1, l2
            return ((bt2, bt1, 8 - r), wmin), l1, l2

        def row_combine_last(count: int, row):
            o_count, o_row = o[-1]
            row = row[:]  # shallow copy, so we don't destroy orig.
            o_row = o_row[:]
            widget_list = []
            while row:
                (bt, w), l1, l2 = seg_combine(o_row.pop(0), row.pop(0))
                if widget_list and widget_list[-1][0] == bt:
                    widget_list[-1] = (bt, widget_list[-1][1] + w)
                else:
                    widget_list.append((bt, w))
                if l1:
                    o_row = [l1, *o_row]
                if l2:
                    row = [l2, *row]

            if o_row:
                raise BarGraphError(o_row)

            o[-1] = (o_count + count, widget_list)

        # regroup into actual rows (8 disp rows == 1 actual row)
        for y_count, row in disp:
            if r:
                count = min(8 - r, y_count)
                row_combine_last(count, row)
                y_count -= count  # noqa: PLW2901
                r += count
                r %= 8
                if not y_count:
                    continue
            if r != 0:
                raise BarGraphError
            # copy whole blocks
            if y_count > 7:
                o.append((y_count // 8 * 8, row))
                y_count %= 8  # noqa: PLW2901
                if not y_count:
                    continue
            o.append((y_count, row))
            r = y_count
        return [(y // 8, row) for (y, row) in o]

    def render(self, size: tuple[int, int], focus: bool = False) -> CompositeCanvas:
        """
        Render BarGraph.
        """
        (maxcol, maxrow) = size
        disp = self.calculate_display((maxcol, maxrow))

        combinelist = []
        for y_count, row in disp:
            widget_list = []
            for bar_type, width in row:
                if isinstance(bar_type, tuple):
                    if len(bar_type) == 3:
                        # vertical eighths
                        fg, bg, k = bar_type
                        a = self.satt[fg, bg]
                        t = self.eighths[k] * width
                    else:
                        # horizontal lines
                        bg, k = bar_type
                        a = self.hatt[bg]
                        t = self.hlines[k] * width
                else:
                    a = self.attr[bar_type]
                    t = self.char[bar_type] * width
                widget_list.append((a, t))
            c = Text(widget_list).render((maxcol,))
            if c.rows() != 1:
                raise BarGraphError("Invalid characters in BarGraph!")
            combinelist += [(c, None, False)] * y_count

        canv = CanvasCombine(combinelist)
        return canv


def calculate_bargraph_display(bardata, top: float, bar_widths: list[int], maxrow: int):
    """
    Calculate a rendering of the bar graph described by data, bar_widths
    and height.

    bardata -- bar information with same structure as BarGraph.data
    top -- maximal value for bardata segments
    bar_widths -- list of integer column widths for each bar
    maxrow -- rows for display of bargraph

    Returns a structure as follows:
      [ ( y_count, [ ( bar_type, width), ... ] ), ... ]

    The outer tuples represent a set of identical rows. y_count is
    the number of rows in this set, the list contains the data to be
    displayed in the row repeated through the set.

    The inner tuple describes a run of width characters of bar_type.
    bar_type is an integer starting from 0 for the background, 1 for
    the 1st segment, 2 for the 2nd segment etc..

    This function should complete in approximately O(n+m) time, where
    n is the number of bars displayed and m is the number of rows.
    """

    if len(bardata) != len(bar_widths):
        raise BarGraphError

    maxcol = sum(bar_widths)

    # build intermediate data structure
    rows = [None] * maxrow

    def add_segment(seg_num: int, col: int, row: int, width: int, rows=rows) -> None:
        if rows[row]:
            last_seg, last_col, last_end = rows[row][-1]
            if last_end > col:
                if last_col >= col:
                    del rows[row][-1]
                else:
                    rows[row][-1] = (last_seg, last_col, col)
            elif last_seg == seg_num and last_end == col:
                rows[row][-1] = (last_seg, last_col, last_end + width)
                return
        elif rows[row] is None:
            rows[row] = []
        rows[row].append((seg_num, col, col + width))

    col = 0
    barnum = 0
    for bar in bardata:
        width = bar_widths[barnum]
        if width < 1:
            continue
        # loop through in reverse order
        tallest = maxrow
        segments = scale_bar_values(bar, top, maxrow)
        for k in range(len(bar) - 1, -1, -1):
            s = segments[k]

            if s >= maxrow:
                continue
            s = max(s, 0)
            if s < tallest:
                # add only properly-overlapped bars
                tallest = s
                add_segment(k + 1, col, s, width)
        col += width
        barnum += 1

    # print(repr(rows))
    # build rowsets data structure
    rowsets = []
    y_count = 0
    last = [(0, maxcol)]

    for r in rows:
        if r is None:
            y_count += 1
            continue
        if y_count:
            rowsets.append((y_count, last))
            y_count = 0

        i = 0  # index into "last"
        la, ln = last[i]  # last attribute, last run length
        c = 0  # current column
        o = []  # output list to be added to rowsets
        for seg_num, start, end in r:
            while start > c + ln:
                o.append((la, ln))
                i += 1
                c += ln
                la, ln = last[i]

            if la == seg_num:
                # same attribute, can combine
                o.append((la, end - c))
            else:
                if start - c > 0:
                    o.append((la, start - c))
                o.append((seg_num, end - start))

            if end == maxcol:
                i = len(last)
                break

            # skip past old segments covered by new one
            while end >= c + ln:
                i += 1
                c += ln
                la, ln = last[i]

            if la != seg_num:
                ln = c + ln - end
                c = end
                continue

            # same attribute, can extend
            oa, on = o[-1]
            on += c + ln - end
            o[-1] = oa, on

            i += 1
            c += ln
            if c == maxcol:
                break
            if i >= len(last):
                raise ValueError(repr((on, maxcol)))
            la, ln = last[i]

        if i < len(last):
            o += [(la, ln), *last[i + 1 :]]
        last = o
        y_count += 1

    if y_count:
        rowsets.append((y_count, last))

    return rowsets


class GraphVScale(Widget):
    _sizing = frozenset([Sizing.BOX])

    def __init__(self, labels, top: float) -> None:
        """
        GraphVScale( [(label1 position, label1 markup),...], top )
        label position -- 0 < position < top for the y position
        label markup -- text markup for this label
        top -- top y position

        This widget is a vertical scale for the BarGraph widget that
        can correspond to the BarGraph's horizontal lines
        """
        super().__init__()
        self.set_scale(labels, top)

    def set_scale(self, labels, top: float) -> None:
        """
        set_scale( [(label1 position, label1 markup),...], top )
        label position -- 0 < position < top for the y position
        label markup -- text markup for this label
        top -- top y position
        """

        labels = sorted(labels[:], reverse=True)  # shallow copy

        self.pos = []
        self.txt = []
        for y, markup in labels:
            self.pos.append(y)
            self.txt.append(Text(markup))
        self.top = top

    def selectable(self) -> Literal[False]:
        """
        Return False.
        """
        return False

    def render(
        self,
        size: tuple[int, int],
        focus: bool = False,
    ) -> SolidCanvas | CompositeCanvas:
        """
        Render GraphVScale.
        """
        (maxcol, maxrow) = size
        pl = scale_bar_values(self.pos, self.top, maxrow)

        combinelist = []
        rows = 0
        for p, t in zip(pl, self.txt):
            p -= 1  # noqa: PLW2901
            if p >= maxrow:
                break
            if p < rows:
                continue
            c = t.render((maxcol,))
            if p > rows:
                run = p - rows
                c = CompositeCanvas(c)
                c.pad_trim_top_bottom(run, 0)
            rows += c.rows()
            combinelist.append((c, None, False))
        if not combinelist:
            return SolidCanvas(" ", size[0], size[1])

        canvas = CanvasCombine(combinelist)
        if maxrow - rows:
            canvas.pad_trim_top_bottom(0, maxrow - rows)
        return canvas


def scale_bar_values(bar, top: float, maxrow: int) -> list[int]:
    """
    Return a list of bar values aliased to integer values of maxrow.
    """
    return [maxrow - int(float(v) * maxrow / top + 0.5) for v in bar]

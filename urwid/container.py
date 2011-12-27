#!/usr/bin/python
#
# Urwid container widget classes
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
# Urwid web site: http://excess.org/urwid/

from itertools import chain, repeat

from urwid.util import is_mouse_press
from urwid.widget import Widget, BoxWidget, FlowWidget, Divider, FLOW, FIXED
from urwid.decoration import Padding, Filler, calculate_padding, calculate_filler, \
    decompose_align_width, decompose_valign_height
from urwid.monitored_list import MonitoredList, MonitoredFocusList
from urwid.canvas import CompositeCanvas, CanvasOverlay, CanvasCombine, \
    SolidCanvas, CanvasJoin


# extra constants for Pile/Columns
WEIGHT = 'weight'


class GridFlow(FlowWidget):

    def selectable(self):
        """Return True if the cell in focus is selectable."""
        return self.focus_cell and self.focus_cell.selectable()

    def __init__(self, cells, cell_width, h_sep, v_sep, align):
        """
        cells -- list of flow widgets to display
        cell_width -- column width for each cell
        h_sep -- blank columns between each cell horizontally
        v_sep -- blank rows between cells vertically (if more than
                 one row is required to display all the cells)
        align -- horizontal alignment of cells, see "align" parameter
                 of Padding widget for available options
        """
        self.__super.__init__()
        self.cells = cells
        self.cell_width = cell_width
        self.h_sep = h_sep
        self.v_sep = v_sep
        self.align = align
        self.focus_cell = None
        if cells:
            self.focus_cell = cells[0]
        self._cache_maxcol = None

    def set_focus(self, cell):
        """
        Set the cell in focus, for backwards compatibility.  You may also
        use the new standard container property .focus_position to set
        the position by integer index instead.

        item -- widget or integer index
        """
        if isinstance(cell, int):
            return self._set_focus_position(cell)
        self.cells.index(cell) # raises ValueError if missing
        self.focus_cell = cell
        self._cache_maxcol = None
        self._invalidate()

    def get_focus(self):
        """
        Return the widget in focus, for backwards compatibility.  You may
        also use the new standard container property .focus to get the
        child widget in focus.
        """
        return self.focus_cell
    focus = property(get_focus,
        doc="the child widget in focus or None when GridFlow is empty")

    def _get_focus_position(self):
        """
        Return the index of the widget in focus or None if this GridFlow is
        empty.
        """
        if self.focus_cell is None:
            return None
        return self.cells.index(self.focus_cell)
    def _set_focus_position(self, position):
        """
        Set the widget in focus.

        position -- index of child widget to be made focus
        """
        try:
            if position < 0 or position >= len(self.cells):
                raise IndexError
        except (TypeError, IndexError):
            raise IndexError, "No child widget at position %s" % (position,)
        self.focus_cell = self.cells[position]
        self._invalidate()
    focus_position = property(_get_focus_position, _set_focus_position,
        doc="index of child widget in focus or None when GridFlow is empty")

    def get_display_widget(self, size):
        """
        Arrange the cells into columns (and possibly a pile) for
        display, input or to calculate rows.
        """
        (maxcol,) = size
        # use cache if possible
        if self._cache_maxcol == maxcol:
            return self._cache_display_widget

        self._cache_maxcol = maxcol
        self._cache_display_widget = self.generate_display_widget(
            size)

        return self._cache_display_widget

    def generate_display_widget(self, size):
        """
        Actually generate display widget (ignoring cache)
        """
        (maxcol,) = size
        d = Divider()
        if len(self.cells) == 0: # how dull
            return d

        if self.v_sep > 1:
            # increase size of divider
            d.top = self.v_sep-1

        # cells per row
        bpr = (maxcol+self.h_sep) // (self.cell_width+self.h_sep)

        if bpr == 0: # too narrow, pile them on top of eachother
            l = [self.cells[0]]
            f = 0
            for b in self.cells[1:]:
                if b is self.focus_cell:
                    f = len(l)
                if self.v_sep:
                    l.append(d)
                l.append(b)
            return Pile(l, f)

        if bpr >= len(self.cells): # all fit on one row
            k = len(self.cells)
            f = self.cells.index(self.focus_cell)
            cols = Columns(self.cells, self.h_sep, f)
            rwidth = (self.cell_width+self.h_sep)*k - self.h_sep
            row = Padding(cols, self.align, rwidth)
            return row


        out = []
        s = 0
        f = 0
        while s < len(self.cells):
            if out and self.v_sep:
                out.append(d)
            k = min( len(self.cells), s+bpr )
            cells = self.cells[s:k]
            if self.focus_cell in cells:
                f = len(out)
                fcol = cells.index(self.focus_cell)
                cols = Columns(cells, self.h_sep, fcol)
            else:
                cols = Columns(cells, self.h_sep)
            rwidth = (self.cell_width+self.h_sep)*(k-s)-self.h_sep
            row = Padding(cols, self.align, rwidth)
            out.append(row)
            s += bpr
        return Pile(out, f)

    def _set_focus_from_display_widget(self, w):
        """Set the focus to the item in focus in the display widget."""
        if isinstance(w, Padding):
            # unwrap padding
            w = w._original_widget
        w = w.get_focus()
        if w in self.cells:
            self.set_focus(w)
            return
        if isinstance(w, Padding):
            # unwrap padding
            w = w._original_widget
        w = w.get_focus()
        #assert w == self.cells[0], repr((w, self.cells))
        self.set_focus(w)

    def keypress(self, size, key):
        """
        Pass keypress to display widget for handling.
        Capture    focus changes."""

        d = self.get_display_widget(size)
        if not d.selectable():
            return key
        key = d.keypress(size, key)
        if key is None:
            self._set_focus_from_display_widget(d)
        return key

    def rows(self, size, focus=False):
        """Return rows used by this widget."""
        d = self.get_display_widget(size)
        return d.rows(size, focus=focus)

    def render(self, size, focus=False ):
        """Use display widget to render."""
        d = self.get_display_widget(size)
        return d.render(size, focus)

    def get_cursor_coords(self, size):
        """Get cursor from display widget."""
        d = self.get_display_widget(size)
        if not d.selectable():
            return None
        return d.get_cursor_coords(size)

    def move_cursor_to_coords(self, size, col, row ):
        """Set the widget in focus based on the col + row."""
        d = self.get_display_widget(size)
        if not d.selectable():
            # happy is the default
            return True

        r =  d.move_cursor_to_coords(size, col, row)
        if not r:
            return False

        self._set_focus_from_display_widget(d)
        self._invalidate()
        return True

    def mouse_event(self, size, event, button, col, row, focus):
        """Send mouse event to contained widget."""
        d = self.get_display_widget(size)

        r = d.mouse_event(size, event, button, col, row, focus)
        if not r:
            return False

        self._set_focus_from_display_widget(d)
        self._invalidate()
        return True


    def get_pref_col(self, size):
        """Return pref col from display widget."""
        d = self.get_display_widget(size)
        if not d.selectable():
            return None
        return d.get_pref_col(size)



class OverlayError(Exception):
    pass

class Overlay(BoxWidget):
    def __init__(self, top_w, bottom_w, align, width, valign, height,
            min_width=None, min_height=None ):
        """
        top_w -- a flow, box or fixed widget to overlay "on top"
        bottom_w -- a box widget to appear "below" previous widget
        align -- one of:
            'left', 'center', 'right'
            ('fixed left', columns)
            ('fixed right', columns)
            ('relative', percentage 0=left 100=right)
        width -- one of:
            None if top_w is a fixed widget
            number of columns wide
            ('fixed right', columns)  Only if align is 'fixed left'
            ('fixed left', columns)  Only if align is 'fixed right'
            ('relative', percentage of total width)
        valign -- one of:
            'top', 'middle', 'bottom'
            ('fixed top', rows)
            ('fixed bottom', rows)
            ('relative', percentage 0=top 100=bottom)
        height -- one of:
            None if top_w is a flow or fixed widget
            number of rows high
            ('fixed bottom', rows)  Only if valign is 'fixed top'
            ('fixed top', rows)  Only if valign is 'fixed bottom'
            ('relative', percentage of total height)
        min_width -- the minimum number of columns for top_w
            when width is not fixed
        min_height -- one of:
            minimum number of rows for the widget when height not fixed

        Overlay widgets behave similarly to Padding and Filler widgets
        when determining the size and position of top_w.  bottom_w is
        always rendered the full size available "below" top_w.
        """
        self.__super.__init__()

        self.top_w = top_w
        self.bottom_w = bottom_w

        self.set_overlay_parameters(align, width, valign, height,
            min_width, min_height)

    def set_overlay_parameters(self, align, width, valign, height,
            min_width=None, min_height=None):
        """
        Adjust the overlay size and position parameters.

        See __init__() for a description of the parameters.
        """
        at,aa,wt,wa=decompose_align_width(align, width, OverlayError)
        vt,va,ht,ha=decompose_valign_height(valign,height,OverlayError)

        self.align_type, self.align_amount = at, aa
        self.width_type, self.width_amount = wt, wa
        if self.width_type and self.width_type != 'fixed':
            self.min_width = min_width
        else:
            self.min_width = None

        self.valign_type, self.valign_amount = vt, va
        self.height_type, self.height_amount = ht, ha
        if self.height_type not in ('fixed', None):
            self.min_height = min_height
        else:
            self.min_height = None
        self._invalidate()

    def selectable(self):
        """Return selectable from top_w."""
        return self.top_w.selectable()

    def keypress(self, size, key):
        """Pass keypress to top_w."""
        return self.top_w.keypress(self.top_w_size(size,
                       *self.calculate_padding_filler(size, True)), key)

    def _get_focus(self):
        """
        Currently self.top_w is always the focus of an Overlay
        """
        return self.top_w
    focus = property(_get_focus,
        doc="the top widget in this overlay is always in focus")

    def _get_focus_position(self):
        """
        Return the top widget position (currently always 0).
        """
        return 0
    def _set_focus_position(self, position):
        """
        Set the widget in focus.  Currently only position 0 is accepted.

        position -- index of child widget to be made focus
        """
        if position != 0:
            raise IndexError, ("Overlay widget focus position currently "
                "must always be set to 0, not %s" % (position,))
    focus_position = property(_get_focus_position, _set_focus_position,
        doc="index of child widget in focus, currently always 0")

    def get_cursor_coords(self, size):
        """Return cursor coords from top_w, if any."""
        if not hasattr(self.body, 'get_cursor_coords'):
            return None
        (maxcol, maxrow) = size
        left, right, top, bottom = self.calculate_padding_filler(size,
            True)
        x, y = self.top_w.get_cursor_coords(
            (maxcol-left-right, maxrow-top-bottom) )
        if y >= maxrow:  # required??
            y = maxrow-1
        return x+left, y+top

    def calculate_padding_filler(self, size, focus):
        """Return (padding left, right, filler top, bottom)."""
        (maxcol, maxrow) = size
        height = None
        if self.width_type is None:
            # top_w is a fixed widget
            width, height = self.top_w.pack((),focus=focus)
            assert height, "fixed widget must have a height"
            left, right = calculate_padding(self.align_type,
                self.align_amount, 'fixed', width,
                None, maxcol, clip=True )
        else:
            left, right = calculate_padding(self.align_type,
                self.align_amount, self.width_type,
                self.width_amount, self.min_width, maxcol)

        if height:
            # top_w is a fixed widget
            top, bottom = calculate_filler(self.valign_type,
                self.valign_amount, 'fixed', height,
                None, maxrow)
            if maxrow-top-bottom < height:
                bottom = maxrow-top-height
        elif self.height_type is None:
            # top_w is a flow widget
            height = self.top_w.rows((maxcol,),focus=focus)
            top, bottom =  calculate_filler( self.valign_type,
                self.valign_amount, 'fixed', height,
                None, maxrow )
            if height > maxrow: # flow widget rendered too large
                bottom = maxrow - height
        else:
            top, bottom = calculate_filler(self.valign_type,
                self.valign_amount, self.height_type,
                self.height_amount, self.min_height, maxrow)
        return left, right, top, bottom

    def top_w_size(self, size, left, right, top, bottom):
        """Return the size to pass to top_w."""
        if self.width_type is None:
            # top_w is a fixed widget
            return ()
        maxcol, maxrow = size
        if self.width_type is not None and self.height_type is None:
            # top_w is a flow widget
            return (maxcol-left-right,)
        return (maxcol-left-right, maxrow-top-bottom)


    def render(self, size, focus=False):
        """Render top_w overlayed on bottom_w."""
        left, right, top, bottom = self.calculate_padding_filler(size,
            focus)
        bottom_c = self.bottom_w.render(size)
        top_c = self.top_w.render(
            self.top_w_size(size, left, right, top, bottom), focus)
        top_c = CompositeCanvas(top_c)
        if left<0 or right<0:
            top_c.pad_trim_left_right(min(0,left), min(0,right))
        if top<0 or bottom<0:
            top_c.pad_trim_top_bottom(min(0,top), min(0,bottom))

        return CanvasOverlay(top_c, bottom_c, left, top)


    def mouse_event(self, size, event, button, col, row, focus):
        """Pass event to top_w, ignore if outside of top_w."""
        if not hasattr(self.top_w, 'mouse_event'):
            return False

        left, right, top, bottom = self.calculate_padding_filler(size,
            focus)
        maxcol, maxrow = size
        if ( col<left or col>=maxcol-right or
            row<top or row>=maxrow-bottom ):
            return False

        return self.top_w.mouse_event(
            self.top_w_size(size, left, right, top, bottom),
            event, button, col-left, row-top, focus )


class Frame(BoxWidget):
    def __init__(self, body, header=None, footer=None, focus_part='body'):
        """
        body -- a box widget for the body of the frame
        header -- a flow widget for above the body (or None)
        footer -- a flow widget for below the body (or None)
        focus_part -- 'header', 'footer' or 'body'
        """
        self.__super.__init__()

        self._header = header
        self._body = body
        self._footer = footer
        self.focus_part = focus_part

    def get_header(self):
        return self._header
    def set_header(self, header):
        self._header = header
        self._invalidate()
    header = property(get_header, set_header)

    def get_body(self):
        return self._body
    def set_body(self, body):
        self._body = body
        self._invalidate()
    body = property(get_body, set_body)

    def get_footer(self):
        return self._footer
    def set_footer(self, footer):
        self._footer = footer
        self._invalidate()
    footer = property(get_footer, set_footer)

    def set_focus(self, part):
        """
        Set the part of the frame that is in focus, for backwards
        compatibility.  You may also use the new standard container property
        .focus_position to set this value.

        part -- 'header', 'footer' or 'body'
        """
        if part not in ('header', 'footer', 'body'):
            raise IndexError, 'Invalid position for Frame: %s' % (part,)
        if (part == 'header' and self._header is None) or (
                part == 'footer' and self._footer is None):
            raise IndexError, 'This Frame has no %s' % (part,)
        self.focus_part = part
        self._invalidate()

    def get_focus(self):
        """
        Return the part of the frame that is in focus, for backwards
        compatibility.  You may also use the new standard container property
        .focus_position to get this value.

        Returns one of 'header', 'footer' or 'body'.
        """
        return self.focus_part

    def _get_focus(self):
        return {
            'header': self._header,
            'footer': self._footer,
            'body': self._body
            }[self.focus_part]
    focus = property(_get_focus,
        doc="the child widget in focus: the body, header or footer widget")

    focus_position = property(get_focus, set_focus, doc="""
        the part of the frame that is in focus: 'body', 'header' or 'footer'
        """)

    def frame_top_bottom(self, size, focus):
        """Calculate the number of rows for the header and footer.

        Returns (head rows, foot rows),(orig head, orig foot).
        orig head/foot are from rows() calls.
        """
        (maxcol, maxrow) = size
        frows = hrows = 0

        if self.header:
            hrows = self.header.rows((maxcol,),
                self.focus_part=='header' and focus)

        if self.footer:
            frows = self.footer.rows((maxcol,),
                self.focus_part=='footer' and focus)

        remaining = maxrow

        if self.focus_part == 'footer':
            if frows >= remaining:
                return (0, remaining),(hrows, frows)

            remaining -= frows
            if hrows >= remaining:
                return (remaining, frows),(hrows, frows)

        elif self.focus_part == 'header':
            if hrows >= maxrow:
                return (remaining, 0),(hrows, frows)

            remaining -= hrows
            if frows >= remaining:
                return (hrows, remaining),(hrows, frows)

        elif hrows + frows >= remaining:
            # self.focus_part == 'body'
            rless1 = max(0, remaining-1)
            if frows >= remaining-1:
                return (0, rless1),(hrows, frows)

            remaining -= frows
            rless1 = max(0, remaining-1)
            return (rless1,frows),(hrows, frows)

        return (hrows, frows),(hrows, frows)



    def render(self, size, focus=False):
        """Render frame and return it."""
        (maxcol, maxrow) = size
        (htrim, ftrim),(hrows, frows) = self.frame_top_bottom(
            (maxcol, maxrow), focus)

        combinelist = []
        depends_on = []

        head = None
        if htrim and htrim < hrows:
            head = Filler(self.header, 'top').render(
                (maxcol, htrim),
                focus and self.focus_part == 'header')
        elif htrim:
            head = self.header.render((maxcol,),
                focus and self.focus_part == 'header')
            assert head.rows() == hrows, "rows, render mismatch"
        if head:
            combinelist.append((head, 'header',
                self.focus_part == 'header'))
            depends_on.append(self.header)

        if ftrim+htrim < maxrow:
            body = self.body.render((maxcol, maxrow-ftrim-htrim),
                focus and self.focus_part == 'body')
            combinelist.append((body, 'body',
                self.focus_part == 'body'))
            depends_on.append(self.body)

        foot = None
        if ftrim and ftrim < frows:
            foot = Filler(self.footer, 'bottom').render(
                (maxcol, ftrim),
                focus and self.focus_part == 'footer')
        elif ftrim:
            foot = self.footer.render((maxcol,),
                focus and self.focus_part == 'footer')
            assert foot.rows() == frows, "rows, render mismatch"
        if foot:
            combinelist.append((foot, 'footer',
                self.focus_part == 'footer'))
            depends_on.append(self.footer)

        return CanvasCombine(combinelist)


    def keypress(self, size, key):
        """Pass keypress to widget in focus."""
        (maxcol, maxrow) = size

        if self.focus_part == 'header' and self.header is not None:
            if not self.header.selectable():
                return key
            return self.header.keypress((maxcol,),key)
        if self.focus_part == 'footer' and self.footer is not None:
            if not self.footer.selectable():
                return key
            return self.footer.keypress((maxcol,),key)
        if self.focus_part != 'body':
            return key
        remaining = maxrow
        if self.header is not None:
            remaining -= self.header.rows((maxcol,))
        if self.footer is not None:
            remaining -= self.footer.rows((maxcol,))
        if remaining <= 0: return key

        if not self.body.selectable():
            return key
        return self.body.keypress( (maxcol, remaining), key )


    def mouse_event(self, size, event, button, col, row, focus):
        """
        Pass mouse event to appropriate part of frame.
        Focus may be changed on button 1 press.
        """
        (maxcol, maxrow) = size
        (htrim, ftrim),(hrows, frows) = self.frame_top_bottom(
            (maxcol, maxrow), focus)

        if row < htrim: # within header
            focus = focus and self.focus_part == 'header'
            if is_mouse_press(event) and button==1:
                if self.header.selectable():
                    self.set_focus('header')
            if not hasattr(self.header, 'mouse_event'):
                return False
            return self.header.mouse_event( (maxcol,), event,
                button, col, row, focus )

        if row >= maxrow-ftrim: # within footer
            focus = focus and self.focus_part == 'footer'
            if is_mouse_press(event) and button==1:
                if self.footer.selectable():
                    self.set_focus('footer')
            if not hasattr(self.footer, 'mouse_event'):
                return False
            return self.footer.mouse_event( (maxcol,), event,
                button, col, row-maxrow+frows, focus )

        # within body
        focus = focus and self.focus_part == 'body'
        if is_mouse_press(event) and button==1:
            if self.body.selectable():
                self.set_focus('body')

        if not hasattr(self.body, 'mouse_event'):
            return False
        return self.body.mouse_event( (maxcol, maxrow-htrim-ftrim),
            event, button, col, row-htrim, focus )



class PileError(Exception):
    pass

class Pile(Widget): # either FlowWidget or BoxWidget
    def __init__(self, widget_list, focus_item=None):
        """
        widget_list -- iterable of widgets
        focus_item -- widget or integer index, if None the first
            selectable widget will be chosen.

        widget_list may also contain tuples such as:
        ('flow', widget) always treat widget as a flow widget
        ('fixed', height, widget) give this box widget a fixed height
        ('weight', weight, widget) if the pile is treated as a box
            widget then treat widget as a box widget with a
            height based on its relative weight value, otherwise
            treat widget as a flow widget

        widgets not in a tuple are the same as ('weight', 1, widget)

        If the Pile is treated as a box widget there must be at least
        one 'weight' tuple in widget_list.
        """
        self.__super.__init__()
        self._contents = MonitoredFocusList()
        self._contents.set_modified_callback(self._invalidate)
        self._contents.set_focus_changed_callback(lambda f: self._invalidate())
        self._contents.set_validate_contents_modified(self._contents_modified)

        focus_item = focus_item
        for i, original in enumerate(widget_list):
            w = original
            if not isinstance(w, tuple):
                self.contents.append((w, (WEIGHT, 1)))
            elif w[0] == FLOW:
                f, w = w
                self.contents.append((w, (FLOW, None)))
            elif w[0] in (FIXED, WEIGHT):
                f, height, w = w
                self.contents.append((w, (f, height)))
            else:
                raise PileError(
                    "initial widget list item invalid %r" % (original,))
            if focus_item is None and w.selectable():
                focus_item = i

        if self.contents and focus_item is not None:
            self.set_focus(focus_item)

        self.pref_col = 0

    def _contents_modified(self, slc, new_items):
        for item in new_items:
            try:
                w, (t, n) = item
                if t not in (FLOW, FIXED, WEIGHT):
                    raise ValueError
            except (TypeError, ValueError):
                raise PileError("added content invalid: %r" % (item,))

    def _get_widget_list(self):
        ml = MonitoredList(w for w, t in self.contents)
        def user_modified():
            self._set_widget_list(ml)
        ml.set_modified_callback(user_modified)
        return ml
    def _set_widget_list(self, widgets):
        focus_position = self.focus_position
        self.contents = [
            (new, t) for (new, (w, t)) in zip(widgets,
                # need to grow contents list if widgets is longer
                chain(self.contents, repeat((None, (WEIGHT, 1)))))]
        if focus_position < len(widgets):
            self.focus_position = focus_position
    widget_list = property(_get_widget_list, _set_widget_list, doc="""
        A list of the widgets in this Pile, for backwards compatibility only.
        You should use the new standard container property .contents to
        modify Pile contents.
        """)

    def _get_item_types(self):
        ml = MonitoredList(t for w, t in self.contents)
        def user_modified():
            self._set_item_types(ml)
        ml.set_modified_callback(user_modified)
        return ml
    def _set_item_types(self, item_types):
        focus_position = self.focus_position
        self.contents = [
            (w, new) for (new, (w, t)) in zip(item_types, self.contents)]
        if focus_position < len(item_types):
            self.focus_position = focus_position
    item_types = property(_get_item_types, _set_item_types, doc="""
        A list of the height_calc values for widgets in this Pile, for
        backwards compatibility only.  You should use the new standard
        container property .contents to modify Pile contents.
        """)

    def _get_contents(self):
        return self._contents
    def _set_contents(self, c):
        self._contents[:] = c
    contents = property(_get_contents, _set_contents, doc="""
        The contents of this Pile as a list of (widget, options) tuples.

        options currently may be one of:
        ('flow', None) -- Always treat widget as a flow widget, i.e. let it
            calculate the number of rows it will display.
        ('fixed', n) -- Always treat widget as a box widget with a fixed
            height of n rows.
        ('weight', w) -- If the Pile itself is treated as a box widget then
            the value w will be used as a relative weight for assigning rows
            to this box widget.  If the Pile is being treated as a flow
            widget then this is the same as ('flow', None) and the w value
            is ignored.

        If the Pile itself is treated as a box widget then at least one
        widget must have a ('weight', w) height_calc value, or the Pile will
        not be able to grow to fill the required number of rows.

        This list may be modified like a normal list and the Pile widget
        will updated automatically.

        Create new options tuples with the Pile.options() class method for
        forward compatibility, as more items may be added in the future.
        """)

    @classmethod
    def options(cls, height_calc=WEIGHT, height_amount=1):
        """
        Return a new options tuple for use in a Pile's .contents list.

        height_calc -- 'flow', 'fixed' or 'weight'
        height_amount -- None for 'flow', a number of rows for 'fixed'
            or a weight value for 'weight'
        """
        if height_calc == FLOW:
            return (FLOW, None)
        if height_calc not in (FIXED, WEIGHT):
            raise PileError('invalid height_calc: %r' % (height_calc,))
        return (height_calc, height_amount)

    def selectable(self):
        """Return True if the focus item is selectable."""
        w = self.focus
        return w is not None and w.selectable()

    def set_focus(self, item):
        """
        Set the item in focus, for backwards compatibility.  You may also
        use the new standard container property .focus_position to set
        the position by integer index instead.

        item -- widget or integer index
        """
        if isinstance(item, int):
            return self._set_focus_position(item)
        for i, (w, options) in enumerate(self.contents):
            if item == w:
                self.focus_position = i
                return
        raise ValueError("Widget not found in Pile contents: %r" % (item,))

    def get_focus(self):
        """
        Return the widget in focus, for backwards compatibility.  You may
        also use the new standard container property .focus to get the
        child widget in focus.
        """
        if not self.contents:
            return None
        return self.contents[self.focus_position][0]
    focus = property(get_focus,
        doc="the child widget in focus or None when Pile is empty")

    focus_item = property(get_focus, set_focus, doc="""
        A property for reading and setting the widget in focus, for
        backwards compatibility only.  You may also use the new standard
        container properties .focus and .focus_position to get the
        child widget in focus or modify the focus position.
        """)

    def _get_focus_position(self):
        """
        Return the index of the widget in focus or None if this Pile is
        empty.
        """
        return self.contents.focus
    def _set_focus_position(self, position):
        """
        Set the widget in focus.

        position -- index of child widget to be made focus
        """
        if not self.contents:
            raise IndexError("Can't set focus position on an empty Pile")
        self.contents.focus = position
    focus_position = property(_get_focus_position, _set_focus_position,
        doc="index of child widget in focus or None when Pile is empty")

    def get_pref_col(self, size):
        """Return the preferred column for the cursor, or None."""
        if not self.selectable():
            return None
        self._update_pref_col_from_focus(size)
        return self.pref_col

    def get_item_size(self, size, i, focus, item_rows=None):
        """
        Return a size appropriate for passing to self.contents[i][0].render
        """
        maxcol = size[0]
        w, (f, height) = self.contents[i]
        if f == FIXED:
            return (maxcol, height)
        elif f == WEIGHT and len(size) == 2:
            if not item_rows:
                item_rows = self.get_item_rows(size, focus)
            return (maxcol, item_rows[i])
        else:
            return (maxcol,)

    def get_item_rows(self, size, focus):
        """
        Return a list of the number of rows used by each widget
        in self.contents
        """
        remaining = None
        maxcol = size[0]
        if len(size) == 2:
            remaining = size[1]

        l = []

        if remaining is None:
            # pile is a flow widget
            for w, (f, height) in self.contents:
                if f == FIXED:
                    l.append(height)
                else:
                    l.append(w.rows((maxcol,),
                        focus=focus and self.focus_item == w))
            return l

        # pile is a box widget
        # do an extra pass to calculate rows for each widget
        wtotal = 0
        for w, (f, height) in self.contents:
            if f == FLOW:
                rows = w.rows((maxcol,), focus=focus and self.focus_item == w)
                l.append(rows)
                remaining -= rows
            elif f == FIXED:
                l.append(height)
                remaining -= height
            else:
                l.append(None)
                wtotal += height

        if wtotal == 0:
            raise PileError, "No weighted widgets found for Pile treated as a box widget"

        if remaining < 0:
            remaining = 0

        for i, (w, (f, height)) in enumerate(self.contents):
            li = l[i]
            if li is None:
                rows = int(float(remaining) * height / wtotal + 0.5)
                l[i] = rows
                remaining -= rows
                wtotal -= height
        return l

    def render(self, size, focus=False):
        """
        Render all widgets in self.contents and return the results
        stacked one on top of the next.
        """
        maxcol = size[0]
        item_rows = None

        combinelist = []
        for i, (w, (f, height)) in enumerate(self.contents):
            item_focus = self.focus_item == w
            canv = None
            if f == FIXED:
                canv = w.render((maxcol, height), focus=focus and item_focus)
            elif f == FLOW or len(size)==1:
                canv = w.render((maxcol,), focus=focus and item_focus)
            else:
                if item_rows is None:
                    item_rows = self.get_item_rows(size, focus)
                rows = item_rows[i]
                if rows>0:
                    canv = w.render((maxcol, rows), focus=focus and item_focus)
            if canv:
                combinelist.append((canv, i, item_focus))
        if not combinelist:
            return SolidCanvas(" ", size[0], (size[1:]+(0,))[0])

        out = CanvasCombine(combinelist)
        if len(size) == 2 and size[1] < out.rows():
            # flow/fixed widgets rendered too large
            out = CompositeCanvas(out)
            out.pad_trim_top_bottom(0, size[1] - out.rows())
        return out

    def get_cursor_coords(self, size):
        """Return the cursor coordinates of the focus widget."""
        if not self.selectable():
            return None
        if not hasattr(self.focus_item, 'get_cursor_coords'):
            return None

        i = self.focus_position
        w, (f, height) = self.contents[i]
        item_rows = None
        maxcol = size[0]
        if f == FIXED or (f == WEIGHT and len(size) == 2):
            if f == FIXED:
                maxrow = height
            else:
                if item_rows is None:
                    item_rows = self.get_item_rows(size, focus=True)
                maxrow = item_rows[i]
            coords = self.focus_item.get_cursor_coords((maxcol, maxrow))
        else:
            coords = self.focus_item.get_cursor_coords((maxcol,))

        if coords is None:
            return None
        x,y = coords
        if i > 0:
            if item_rows is None:
                item_rows = self.get_item_rows(size, focus=True)
            for r in item_rows[:i]:
                y += r
        return x, y

    def rows(self, size, focus=False ):
        """Return the number of rows required for this widget."""
        return sum(self.get_item_rows(size, focus))

    def keypress(self, size, key ):
        """Pass the keypress to the widget in focus.
        Unhandled 'up' and 'down' keys may cause a focus change."""
        if not self.contents:
            return key

        item_rows = None
        if len(size) == 2:
            item_rows = self.get_item_rows(size, focus=True)

        i = self.focus_position
        if self.selectable():
            tsize = self.get_item_size(size, i, True, item_rows)
            key = self.focus.keypress(tsize, key)
            if self._command_map[key] not in ('cursor up', 'cursor down'):
                return key

        if self._command_map[key] == 'cursor up':
            candidates = range(i-1, -1, -1) # count backwards to 0
        else: # self._command_map[key] == 'cursor down'
            candidates = range(i+1, len(self.contents))

        if not item_rows:
            item_rows = self.get_item_rows(size, focus=True)

        for j in candidates:
            if not self.contents[j][0].selectable():
                continue

            self._update_pref_col_from_focus(size)
            self.focus_position = j
            if not hasattr(self.focus, 'move_cursor_to_coords'):
                return

            rows = item_rows[j]
            if self._command_map[key] == 'cursor up':
                rowlist = range(rows-1, -1, -1)
            else: # self._command_map[key] == 'cursor down'
                rowlist = range(rows)
            for row in rowlist:
                tsize = self.get_item_size(size, j, True, item_rows)
                if self.focus_item.move_cursor_to_coords(
                        tsize, self.pref_col, row):
                    break
            return

        # nothing to select
        return key

    def _update_pref_col_from_focus(self, size):
        """Update self.pref_col from the focus widget."""

        if not hasattr(self.focus, 'get_pref_col'):
            return
        i = self.focus_position
        tsize = self.get_item_size(size, i, True)
        pref_col = self.focus.get_pref_col(tsize)
        if pref_col is not None:
            self.pref_col = pref_col

    def move_cursor_to_coords(self, size, col, row):
        """Capture pref col and set new focus."""
        self.pref_col = col

        #FIXME guessing focus==True
        focus=True
        wrow = 0
        item_rows = self.get_item_rows(size, focus)
        for i, (r, w) in enumerate(zip(item_rows,
                (w for (w, options) in self.contents))):
            if wrow + r > row:
                break
            wrow += r
        else:
            return False

        if not w.selectable():
            return False

        if hasattr(w, 'move_cursor_to_coords'):
            tsize = self.get_item_size(size, i, focus, item_rows)
            rval = w.move_cursor_to_coords(tsize, col, row-wrow)
            if rval is False:
                return False

        self.focus_position = i
        return True

    def mouse_event(self, size, event, button, col, row, focus):
        """
        Pass the event to the contained widget.
        May change focus on button 1 press.
        """
        wrow = 0
        item_rows = self.get_item_rows(size, focus)
        for i, (r, w) in enumerate(zip(item_rows,
                (w for (w, options) in self.contents))):
            if wrow + r > row:
                break
            wrow += r

        focus = focus and self.focus_item == w
        if is_mouse_press(event) and button == 1:
            if w.selectable():
                self.set_focus_position = i

        if not hasattr(w, 'mouse_event'):
            return False

        tsize = self.get_item_size(size, i, focus, item_rows)
        return w.mouse_event(tsize, event, button, col, row-wrow,
            focus)



class ColumnsError(Exception):
    pass


class Columns(Widget): # either FlowWidget or BoxWidget
    def __init__(self, widget_list, dividechars=0, focus_column=None,
        min_width=1, box_columns=None):
        """
        widget_list -- iterable of flow widgets or iterable of box widgets
        dividechars -- blank characters between columns
        focus_column -- index into widget_list of column in focus,
            if None the first selectable widget will be chosen.
        min_width -- minimum width for each column which is not
            designated as flow widget in widget_list.
        box_columns -- a list of column indexes containing box widgets
            whose maxrow is set to the maximum of the rows
            required by columns not listed in box_columns.

        widget_list may also contain tuples such as:
        ('flow', widget) call pack() to calculate the width
        ('fixed', width, widget) give this column a fixed width
        ('weight', weight, widget) give this column a relative weight

        widgets not in a tuple are the same as ('weight', 1, widget)

        Is the Columns widget is treated as a box widget then all children
        are treated as box widgets, and box_columns is ignored.

        If the Columns widget is treated as a flow widget then the rows
        are calcualated as the largest rows() returned from all columns
        except the ones listed in box_columns.  The box widgets in
        box_columns will be displayed with this calculated number of rows,
        filling the full height.
        """
        self.__super.__init__()
        self._contents = MonitoredFocusList()
        self._contents.set_modified_callback(self._invalidate)
        self._contents.set_focus_changed_callback(lambda f: self._invalidate())
        self._contents.set_validate_contents_modified(self._contents_modified)

        box_columns = set(box_columns or ())

        for i, original in enumerate(widget_list):
            w = original
            if not isinstance(w, tuple):
                self.contents.append((w, (WEIGHT, 1, i in box_columns)))
            elif w[0] == FLOW:
                f, w = w
                self.contents.append((w, (f, None, i in box_columns)))
            elif w[0] in (FIXED, WEIGHT):
                f, width, w = w
                self.contents.append((w, (f, width, i in box_columns)))
            else:
                raise ColumnsError(
                    "initial widget list item invalid: %r" % (original,))
            if focus_column is None and w.selectable():
                focus_column = i

        self.dividechars = dividechars

        if self.contents and focus_column is not None:
            self.focus_position = focus_column
        if focus_column is None:
            focus_column = 0
        self.dividechars = dividechars
        self.pref_col = None
        self.min_width = min_width
        self._cache_maxcol = None

    def _contents_modified(self, slc, new_items):
        for item in new_items:
            try:
                w, (t, n, b) = item
                if t not in (FLOW, FIXED, WEIGHT):
                    raise ValueError
            except (TypeError, ValueError):
                raise ColumnsError("added content invalid %r" % (item,))

    def _get_widget_list(self):
        ml = MonitoredList(w for w, t in self.contents)
        def user_modified():
            self._set_widget_list(ml)
        ml.set_modified_callback(user_modified)
        return ml
    def _set_widget_list(self, widgets):
        focus_position = self.focus_position
        self.contents = [
            (new, t) for (new, (w, t)) in zip(widgets,
                # need to grow contents list if widgets is longer
                chain(self.contents, repeat((None, (WEIGHT, 1, False)))))]
        if focus_position < len(widgets):
            self.focus_position = focus_position
    widget_list = property(_get_widget_list, _set_widget_list, doc="""
        A list of the widgets in this Columns, for backwards compatibility only.
        You should use the new standard container property .contents to
        modify Column contents.
        """)

    def _get_column_types(self):
        ml = MonitoredList(t[:2] for w, t in self.contents)
        def user_modified():
            self._set_column_types(ml)
        ml.set_modified_callback(user_modified)
        return ml
    def _set_column_types(self, column_types):
        focus_position = self.focus_position
        self.contents = [
            (w, new + (b,))
            for (new, (w, (t, n, b))) in zip(column_types, self.contents)]
        if focus_position < len(column_types):
            self.focus_position = focus_position
    column_types = property(_get_column_types, _set_column_types, doc="""
        A list of the partial options values for widgets in this Pile, for
        backwards compatibility only.  You should use the new standard
        container property .contents to modify Pile contents.
        """)

    def _get_box_columns(self):
        ml = MonitoredList(
            i for i, (w, (t, n, b)) in enumerate(self.contents) if b)
        def user_modified():
            self._set_box_columns(ml)
        ml.set_modified_callback(user_modified)
        return ml
    def _set_box_columns(self, box_columns):
        box_columns = set(box_columns)
        focus_position = self.focus_position
        self.contents = [
            (w, (t, n, i in box_columns))
            for (i, (w, (t, n, b))) in enumerate(self.contents)]
        if focus_position < len(column_types):
            self.focus_position = focus_position
    box_columns = property(_get_box_columns, _set_box_columns, doc="""
        A list of the indexes of the columns that are to be treated as
        box widgets when the Columns is treated as a flow widget, for
        backwards compatibility only.  You should use the new standard
        container property .contents to modify Pile contents instead.
        """)

    def _get_has_flow_type(self):
        return FLOW in self.column_types
    has_flow_type = property(_get_has_flow_type, lambda ignore:None)

    def _get_contents(self):
        return self._contents
    def _set_contents(self, c):
        self._contents[:] = c
    contents = property(_get_contents, _set_contents, doc="""
        The contents of this Columns as a list of (widget, options)
        tuples.

        options is currently a tuple in the form (width_calc,
        width_amount, box_widget), where width_calc is one of:
        'flow' -- Call the widget's pack() method to determine how wide
            this column should be.  width_amount is ignored.
        'fixed' -- Make column exactly width_amount screen-columns wide.
        'weight' -- Allocate the remaining space to this column by using
            width_amount as a weight value.

        box_widget is True if this widget is to be treated as a box
        widget when the Columns widget itself is treated as a flow
        widget.

        This list may be modified like a normal list and the Columns
        widget will update automatically.

        Create new options tuples with the Columns.options() class
        method for forward compatibility, as more options may be added
        in the future.
        """)

    @classmethod
    def options(cls, width_calc=WEIGHT, width_amount=1, box_widget=False):
        """
        Return a new options tuple for use in a Pile's .contents list.

        width_calc -- 'flow', 'fixed' or 'weight'
        width_amount -- None for 'flow', a number of rows for 'fixed'
            or a weight value for 'weight'
        box_widget -- True to treat as box widget when Columns is
            treated as a flow widget
        """
        if width_calc == FLOW:
            width_amount = None
        if width_calc not in (FLOW, FIXED, WEIGHT):
            raise ColumnsError('invalid width_calc: %r' % (width_calc,))
        return (width_calc, width_amount, box_widget)

    def _invalidate(self):
        self._cache_maxcol = None
        self.__super._invalidate()

    def set_focus_column(self, num):
        """
        Set the column in focus by its index in self.widget_list, for
        backwards compatibility.  You may also use the new standard
        container property .focus_position to set the focus.
        """
        self._set_focus_position(num)

    def get_focus_column(self):
        """
        Return the focus column index, for backwards compatibility. You
        may also use the new standard container property .focus_position
        to get the focus column index.
        """
        return self.focus_position

    def set_focus(self, item):
        """
        Set the item in focus, for backwards compatibility.  You may also
        use the new standard container property .focus_position to set
        the position by integer index instead.

        item -- widget or integer index"""
        if isinstance(item, int):
            return self._set_focus_position(item)
        for i, (w, options) in enumerate(self.contents):
            if item == w:
                self.focus_position = i
                return
        raise ValueError("Widget not found in Columns contents: %r" % (item,))

    def get_focus(self):
        """
        Return the widget in focus, for backwards compatibility.  You may
        also use the new standard container property .focus to get the
        child widget in focus.
        """
        if not self.contents:
            return None
        return self.contents[self.focus_position][0]
    focus = property(get_focus,
        doc="the child widget in focus or None when Columns is empty")

    def _get_focus_position(self):
        """
        Return the index of the widget in focus or None if this Columns is
        empty.
        """
        if not self.widget_list:
            return None
        return self.contents.focus
    def _set_focus_position(self, position):
        """
        Set the widget in focus.

        position -- index of child widget to be made focus
        """
        try:
            if position < 0 or position >= len(self.contents):
                raise IndexError
        except (TypeError, IndexError):
            raise IndexError, "No child widget at position %s" % (position,)
        self.contents.focus = position
        self._invalidate()
    focus_position = property(_get_focus_position, _set_focus_position,
        doc="index of child widget in focus or None when Columns is empty")

    focus_col = property(_get_focus_position, _set_focus_position, doc="""
        A property for reading and setting the index of the column in
        focus, for backwards compatibility only.  You may also use the
        new standard container property .focus_position to get or
        modify the focus position.
        """)

    def column_widths(self, size, focus=False):
        """
        Return a list of column widths.

        size -- (maxcol,) if self.widget_list contains flow widgets or
            (maxcol, maxrow) if it contains box widgets.
        """
        maxcol = size[0]
        # FIXME: get rid of has_flow_type
        if maxcol == self._cache_maxcol and not self.has_flow_type:
            return self._cache_column_widths

        widths = []

        weighted = []
        shared = maxcol + self.dividechars

        for i, (w, (t, width, b)) in enumerate(self.contents):
            if t == FIXED:
                static_w = width
            elif t == FLOW:
                # FIXME: should be able to pack with a different
                # maxcol value
                static_w = w.pack((maxcol,), focus)[0]
            else:
                static_w = self.min_width

            if shared < static_w + self.dividechars:
                break

            widths.append(static_w)
            shared -= static_w + self.dividechars
            if t not in (FIXED, FLOW):
                weighted.append((width, i))

        if shared:
            # divide up the remaining space between weighted cols
            weighted.sort()
            wtotal = sum(weight for weight, i in weighted)
            grow = shared + len(weighted) * self.min_width
            for weight, i in weighted:
                width = int(float(grow) * weight / wtotal + 0.5)
                width = max(self.min_width, width)
                widths[i] = width
                grow -= width
                wtotal -= weight

        self._cache_maxcol = maxcol
        self._cache_column_widths = widths
        return widths

    def render(self, size, focus=False):
        """
        Render columns and return canvas.

        size -- (maxcol,) if self.widget_list contains flow widgets or
            (maxcol, maxrow) if it contains box widgets.
        """
        widths = self.column_widths(size, focus)
        if not widths:
            return SolidCanvas(" ", size[0], (size[1:]+(1,))[0])

        box_maxrow = None
        if len(size) == 1:
            box_maxrow = 1
            # two-pass mode to determine maxrow for box columns
            for i, (mc, (w, (t, n, b))) in enumerate(zip(widths, self.contents)):
                if b:
                    continue
                rows = w.rows((mc,),
                    focus = focus and self.focus_position == i)
                box_maxrow = max(box_maxrow, rows)

        l = []
        for i, (mc, (w, (t, n, b))) in enumerate(zip(widths, self.contents)):
            # if the widget has a width of 0, hide it
            if mc <= 0:
                continue

            if box_maxrow and b:
                sub_size = (mc, box_maxrow)
            else:
                sub_size = (mc,) + size[1:]

            canv = w.render(sub_size,
                focus = focus and self.focus_position == i)

            if i < len(widths) - 1:
                mc += self.dividechars
            l.append((canv, i, self.focus_position == i, mc))

        canv = CanvasJoin(l)
        if canv.cols() < size[0]:
            canv.pad_trim_left_right(0, size[0] - canv.cols())
        return canv

    def get_cursor_coords(self, size):
        """Return the cursor coordinates from the focus widget."""
        w = self.contents[self.focus_position][0]

        if not w.selectable():
            return None
        if not hasattr(w, 'get_cursor_coords'):
            return None

        widths = self.column_widths(size)
        if len(widths) <= self.focus_position:
            return None
        colw = widths[self.focus_position]

        coords = w.get_cursor_coords((colw,)+size[1:])
        if coords is None:
            return None
        x, y = coords
        x += self.focus_col * self.dividechars
        x += sum(widths[:self.focus_position])
        return x, y

    def move_cursor_to_coords(self, size, col, row):
        """Choose a selectable column to focus based on the coords."""
        widths = self.column_widths(size)

        best = None
        x = 0
        for i, (width, (w, options)) in enumerate(zip(widths, self.contents)):
            end = x + width
            if w.selectable():
                # FIXME: sometimes, col == 'left' - that doesn't seem like its handled here, does it?
                # assert isinstance(x, int) and isinstance(col, int), (x, col)
                if x > col and best is None:
                    # no other choice
                    best = i, x, end, w
                    break
                if x > col and col-best[2] < x-col:
                    # choose one on left
                    break
                best = i, x, end, w
                if col < end:
                    # choose this one
                    break
            x = end + self.dividechars

        if best is None:
            return False
        i, x, end, w = best
        if hasattr(w, 'move_cursor_to_coords'):
            if isinstance(col, int):
                move_x = min(max(0, col - x), end - x - 1)
            else:
                move_x = col
            rval = w.move_cursor_to_coords((end - x,) + size[1:],
                move_x, row)
            if rval is False:
                return False

        self.focus_position = i
        self.pref_col = col
        return True

    def mouse_event(self, size, event, button, col, row, focus):
        """
        Send event to appropriate column.
        May change focus on button 1 press.
        """
        widths = self.column_widths(size)

        x = 0
        for i, (width, (w, options)) in enumerate(zip(widths, self.contents)):
            if col < x:
                return False
            w = self.widget_list[i]
            end = x + width

            if col >= end:
                x = end + self.dividechars
                continue

            focus = focus and self.focus_col == i
            if is_mouse_press(event) and button == 1:
                if w.selectable():
                    self.focus_position = i

            if not hasattr(w, 'mouse_event'):
                return False

            return w.mouse_event((end - x,) + size[1:], event, button,
                col - x, row, focus)
        return False

    def get_pref_col(self, size):
        """Return the pref col from the column in focus."""
        maxcol = size[0]
        widths = self.column_widths(size)

        w = self.contents[self.focus_position][0]
        if len(widths) <= self.focus_position:
            return 0
        col = None
        cwidth = widths[self.focus_position]
        if hasattr(w, 'get_pref_col'):
            col = w.get_pref_col((cwidth,) + size[1:])
            if isinstance(col, int):
                col += self.focus_col * self.dividechars
                col += sum(widths[:self.focus_position])
        if col is None:
            col = self.pref_col
        if col is None and w.selectable():
            col = cwidth // 2
            col += self.focus_position * self.dividechars
            col += sum(widths[:self.focus_position] )
        return col

    def rows(self, size, focus=0):
        """
        Return the number of rows required by the columns.
        Only makes sense if self.widget_list contains flow widgets.
        """
        widths = self.column_widths(size, focus)

        rows = 1
        for i, (mc, (w, (t, n, b))) in enumerate(zip(widths, self.contents)):
            if b:
                continue
            rows = max(rows,
                w.rows((mc,), focus=focus and self.focus_position == i))
        return rows

    def keypress(self, size, key):
        """
        Pass keypress to the focus column.

        size -- (maxcol,) if self.widget_list contains flow widgets or
            (maxcol, maxrow) if it contains box widgets.
        """
        if self.focus_position is None: return key

        widths = self.column_widths(size)
        if self.focus_position >= len(widths):
            return key

        i = self.focus_position
        mc = widths[i]
        w = self.contents[i][0]
        if self._command_map[key] not in ('cursor up', 'cursor down',
            'cursor page up', 'cursor page down'):
            self.pref_col = None
        key = w.keypress((mc,) + size[1:], key)

        if self._command_map[key] not in ('cursor left', 'cursor right'):
            return key

        if self._command_map[key] == 'cursor left':
            candidates = range(i-1, -1, -1) # count backwards to 0
        else: # key == 'right'
            candidates = range(i+1, len(widths))

        for j in candidates:
            if not self.contents[j][0].selectable():
                continue

            self.focus_position = j
            return
        return key


    def selectable(self):
        """Return the selectable value of the focus column."""
        return self.contents[self.focus_position][0].selectable()






def _test():
    import doctest
    doctest.testmod()

if __name__=='__main__':
    _test()

#!/usr/bin/python
#
# Urwid basic widget classes
#    Copyright (C) 2004-2007  Ian Ward
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

from util import *
import signals
import text_layout
from canvas import *
from monitored_list import MonitoredList
from command_map import command_map
from signals import connect_signal, connect_signal, disconnect_signal
from split_repr import split_repr, remove_defaults

try: sum # old python?
except: sum = lambda l: reduce(lambda a,b: a+b, l, 0)

try: set
except: set = list # not perfect, but should be good enough for python2.2


# Widget sizing methods
# (use the same string objects to make some comparisons faster)
FLOW = 'flow'
BOX = 'box'
FIXED = 'fixed'

# Text alignment modes 
LEFT = 'left'
RIGHT = 'right'
CENTER = 'center'

# Filler alignment modes 
TOP = 'top'
MIDDLE = 'middle'
BOTTOM = 'bottom'

# Text wrapping modes
SPACE = 'space'
ANY = 'any'
CLIP = 'clip'

# Extras for Padding
PACK = 'pack'
GIVEN = 'given'
RELATIVE = 'relative'
RELATIVE_100 = (RELATIVE, 100)
CLIP = 'clip'


class WidgetMeta(MetaSuper, signals.MetaSignals):
    """
    Automatic caching of render and rows methods.

    Class variable no_cache is a list of names of methods to not cache.
    Class variable ignore_focus if defined and True indicates that this
    widget is not affected by the focus parameter, so it may be ignored
    when caching.
    """
    def __init__(cls, name, bases, d):
        no_cache = d.get("no_cache", [])
        
        super(WidgetMeta, cls).__init__(name, bases, d)

        if "render" in d:
            if "render" not in no_cache:
                render_fn = cache_widget_render(cls)
            else:
                render_fn = nocache_widget_render(cls)
            cls.render = render_fn

        if "rows" in d and "rows" not in no_cache:
            cls.rows = cache_widget_rows(cls)
        if "no_cache" in d:
            del cls.no_cache
        if "ignore_focus" in d:
            del cls.ignore_focus

class WidgetError(Exception):
    pass

def validate_size(widget, size, canv):
    """
    Raise a WidgetError if a canv does not match size size.
    """
    if (size and size[1:] != (0,) and size[0] != canv.cols()) or \
        (len(size)>1 and size[1] != canv.rows()):
        raise WidgetError("Widget %r rendered (%d x %d) canvas"
            " when passed size %r!" % (widget, canv.cols(),
            canv.rows(), size))

def update_wrapper(new_fn, fn):
    """
    Copy as much of the function detail from fn to new_fn
    as we can.
    """
    try:
        new_fn.__name__ = fn.__name__
        new_fn.__dict__.update(fn.__dict__)
        new_fn.__doc__ = fn.__doc__
        new_fn.__module__ = fn.__module__
    except TypeError:
        pass # python2.3 ignore read-only attributes


def cache_widget_render(cls):
    """
    Return a function that wraps the cls.render() method
    and fetches and stores canvases with CanvasCache.
    """
    ignore_focus = bool(getattr(cls, "ignore_focus", False))
    fn = cls.render
    def cached_render(self, size, focus=False):
        focus = focus and not ignore_focus
        canv = CanvasCache.fetch(self, cls, size, focus)
        if canv:
            return canv

        canv = fn(self, size, focus=focus)
        validate_size(self, size, canv)
        if canv.widget_info:
            canv = CompositeCanvas(canv)
        canv.finalize(self, size, focus)
        CanvasCache.store(cls, canv)
        return canv
    cached_render.original_fn = fn
    update_wrapper(cached_render, fn)
    return cached_render

def nocache_widget_render(cls):
    """
    Return a function that wraps the cls.render() method
    and finalizes the canvas that it returns.
    """
    fn = cls.render
    if hasattr(fn, "original_fn"):
        fn = fn.original_fn
    def finalize_render(self, size, focus=False):
        canv = fn(self, size, focus=focus)
        if canv.widget_info:
            canv = CompositeCanvas(canv)
        validate_size(self, size, canv)
        canv.finalize(self, size, focus)
        return canv
    finalize_render.original_fn = fn
    update_wrapper(finalize_render, fn)
    return finalize_render

def nocache_widget_render_instance(self):
    """
    Return a function that wraps the cls.render() method
    and finalizes the canvas that it returns, but does not 
    cache the canvas.
    """
    fn = self.render.original_fn
    def finalize_render(size, focus=False):
        canv = fn(self, size, focus=focus)
        if canv.widget_info:
            canv = CompositeCanvas(canv)
        canv.finalize(self, size, focus)
        return canv
    finalize_render.original_fn = fn
    update_wrapper(finalize_render, fn)
    return finalize_render

def cache_widget_rows(cls):
    """
    Return a function that wraps the cls.rows() method
    and returns rows from the CanvasCache if available.
    """
    ignore_focus = bool(getattr(cls, "ignore_focus", False))
    fn = cls.rows
    def cached_rows(self, size, focus=False):
        focus = focus and not ignore_focus
        canv = CanvasCache.fetch(self, cls, size, focus)
        if canv:
            return canv.rows()

        return fn(self, size, focus)
    update_wrapper(cached_rows, fn)
    return cached_rows


class Widget(object):
    """
    base class of widgets
    """
    __metaclass__ = WidgetMeta
    _selectable = False
    _sizing = set([])

    def _invalidate(self):
        CanvasCache.invalidate(self)

    def _emit(self, name, *args):
        """
        Convenience function to emit signals with self as first
        argument.
        """
        signals.emit_signal(self, name, self, *args)
    
    def selectable(self):
        """
        Return True if this widget should take focus.  Default
        implementation returns the value of self._selectable.
        """
        return self._selectable
    
    def sizing(self):
        """
        Return a set including one or more of 'box', 'flow' and
        'fixed'.  Default implementation returns the value of
        self._sizing.
        """
        return self._sizing

    def pack(self, size, focus=False):
        """
        Return a 'packed' (maxcol, maxrow) for this widget.  Default 
        implementation (no packing defined) returns size, and
        calculates maxrow if not given.
        """
        if size == ():
            if FIXED in self.sizing():
                raise NotImplementedError('Fixed widgets must override'
                    ' Widget.size()')
            raise WidgetError('Cannot pack () size, this is not a fixed'
                ' widget: %s' % repr(self))
        elif len(size) == 1:
            if FLOW in self.sizing():
                return size + (self.rows(size, focus),)
            raise WidgetError('Cannot pack (maxcol,) size, this is not a'
                ' flow widget: %s' % repr(self))
        return size

    # this property returns the widget without any decorations, default
    # implementation returns self.
    base_widget = property(lambda self:self)
    

    # Use the split_repr module to create __repr__ from _repr_words
    # and _repr_attrs
    __repr__ = split_repr

    def _repr_words(self):
        words = []
        if self.selectable():
            words = ["selectable"] + words
        if self.sizing():
            sizing_modes = list(self.sizing())
            sizing_modes.sort()
            words.append("/".join(sizing_modes))
        return words + ["widget"]

    def _repr_attrs(self):
        return {}
    

class FlowWidget(Widget):
    """
    base class of widgets that determine their rows from the number of
    columns available.
    """
    _sizing = set([FLOW])
    
    def rows(self, size, focus=False):
        """
        All flow widgets must implement this function.
        """
        raise NotImplementedError()

    def render(self, size, focus=False):
        """
        All widgets must implement this function.
        """
        raise NotImplementedError()


class BoxWidget(Widget):
    """
    base class of width and height constrained widgets such as
    the top level widget attached to the display object
    """
    _selectable = True
    _sizing = set([BOX])
    
    def render(self, size, focus=False):
        """
        All widgets must implement this function.
        """
        raise NotImplementedError()
    

def fixed_size(size):
    """
    raise ValueError if size != ().
    
    Used by FixedWidgets to test size parameter.
    """
    if size != ():
        raise ValueError("FixedWidget takes only () for size." \
            "passed: %s" % `size`)

class FixedWidget(Widget):
    """
    base class of widgets that know their width and height and
    cannot be resized
    """
    _sizing = set([FIXED])
    
    def render(self, size, focus=False):
        """
        All widgets must implement this function.
        """
        raise NotImplementedError()
    
    def pack(self, size=None, focus=False):
        """
        All fixed widgets must implement this function.
        """
        raise NotImplementedError()


class Divider(FlowWidget):
    """
    Horizontal divider widget
    """
    ignore_focus = True

    def __init__(self,div_char=" ",top=0,bottom=0):
        """
        Create a horizontal divider widget.
        
        div_char -- character to repeat across line
        top -- number of blank lines above
        bottom -- number of blank lines below

        >>> Divider()
        <Divider flow widget div_char=' '>
        >>> Divider('-')
        <Divider flow widget div_char='-'>
        >>> Divider('x', 1, 2)
        <Divider flow widget bottom=2 div_char='x' top=1>
        """
        self.__super.__init__()
        self.div_char = div_char
        self.top = top
        self.bottom = bottom
        
    def _repr_attrs(self):
        attrs = dict(self.__super._repr_attrs(),
            div_char=self.div_char)
        if self.top: attrs['top'] = self.top
        if self.bottom: attrs['bottom'] = self.bottom
        return attrs
    
    def rows(self, size, focus=False):
        """
        Return the number of lines that will be rendered.

        >>> Divider().rows((10,))
        1
        >>> Divider('x', 1, 2).rows((10,))
        4
        """
        (maxcol,) = size
        return self.top + 1 + self.bottom
    
    def render(self, size, focus=False):
        """
        Render the divider as a canvas and return it.
        
        >>> Divider().render((10,)).text 
        ['          ']
        >>> Divider('-', top=1).render((10,)).text
        ['          ', '----------']
        >>> Divider('x', bottom=2).render((5,)).text
        ['xxxxx', '     ', '     ']
        """
        (maxcol,) = size
        canv = SolidCanvas(self.div_char, maxcol, 1)
        canv = CompositeCanvas(canv)
        if self.top or self.bottom:
            canv.pad_trim_top_bottom(self.top, self.bottom)
        return canv
    

class SolidFill(BoxWidget):
    _selectable = False
    ignore_focus = True

    def __init__(self, fill_char=" "):
        """
        Create a box widget that will fill an area with a single 
        character.
        
        fill_char -- character to fill area with

        >>> SolidFill('8')
        <SolidFill box widget '8'>
        """
        self.__super.__init__()
        self.fill_char = fill_char
    
    def _repr_words(self):
        return self.__super._repr_words() + [repr(self.fill_char)]
    
    def render(self, size, focus=False ):
        """
        Render the Fill as a canvas and return it.

        >>> SolidFill().render((4,2)).text
        ['    ', '    ']
        >>> SolidFill('#').render((5,3)).text
        ['#####', '#####', '#####']
        """
        maxcol, maxrow = size
        return SolidCanvas(self.fill_char, maxcol, maxrow)
    
class TextError(Exception):
    pass

class Text(FlowWidget):
    """
    a horizontally resizeable text widget
    """
    ignore_focus = True

    def __init__(self, markup, align=LEFT, wrap=SPACE, layout=None):
        """
        markup -- content of text widget, one of:
            plain string -- string is displayed
            ( attr, markup2 ) -- markup2 is given attribute attr
            [ markupA, markupB, ... ] -- list items joined together
        align -- align mode for text layout
        wrap -- wrap mode for text layout
        layout -- layout object to use, defaults to StandardTextLayout

        >>> Text("Hello")
        <Text flow widget 'Hello'>
        >>> t = Text(('bold', "stuff"), 'right', 'any')
        >>> t
        <Text flow widget 'stuff' align='right' wrap='any'>
        >>> t.text
        'stuff'
        >>> t.attrib
        [('bold', 5)]
        """
        self.__super.__init__()
        self._cache_maxcol = None
        self.set_text(markup)
        self.set_layout(align, wrap, layout)
    
    def _repr_words(self):
        return self.__super._repr_words() + [
            repr(self.get_text()[0])]
    
    def _repr_attrs(self):
        attrs = dict(self.__super._repr_attrs(),
            align=self._align_mode, 
            wrap=self._wrap_mode)
        return remove_defaults(attrs, Text.__init__)
    
    def _invalidate(self):
        self._cache_maxcol = None
        self.__super._invalidate()

    def set_text(self,markup):
        """
        Set content of text widget.

        markup -- see __init__() for description.

        >>> t = Text("foo")
        >>> t.text
        'foo'
        >>> t.set_text("bar")
        >>> t.text
        'bar'
        >>> t.text = "baz"  # not supported because text stores text but set_text() takes markup
        Traceback (most recent call last):
            ...  
        AttributeError: can't set attribute
        """
        self._text, self._attrib = decompose_tagmarkup(markup)
        self._invalidate()

    def get_text(self):
        """
        Returns (text, attributes).
        
        text -- complete string content of text widget
        attributes -- run length encoded attributes for text

        >>> Text("Hello").get_text()
        ('Hello', [])
        >>> Text(('bright', "Headline")).get_text()
        ('Headline', [('bright', 8)])
        >>> Text([('a', "one"), "two", ('b', "three")]).get_text()
        ('onetwothree', [('a', 3), (None, 3), ('b', 5)])
        """
        return self._text, self._attrib

    text = property(lambda self:self.get_text()[0])
    attrib = property(lambda self:self.get_text()[1])

    def set_align_mode(self, mode):
        """
        Set text alignment / justification.  
        
        Valid modes for StandardTextLayout are: 
            'left', 'center' and 'right'

        >>> t = Text("word")
        >>> t.set_align_mode('right')
        >>> t.align
        'right'
        >>> t.render((10,)).text
        ['      word']
        >>> t.align = 'center'
        >>> t.render((10,)).text
        ['   word   ']
        >>> t.align = 'somewhere'
        Traceback (most recent call last):
            ...
        TextError: Alignment mode 'somewhere' not supported.
        """
        if not self.layout.supports_align_mode(mode):
            raise TextError("Alignment mode %s not supported."%
                `mode`)
        self._align_mode = mode
        self._invalidate()

    def set_wrap_mode(self, mode):
        """
        Set wrap mode.  
        
        Valid modes for StandardTextLayout are :
            'any'    : wrap at any character
            'space'    : wrap on space character
            'clip'    : truncate lines instead of wrapping
        
        >>> t = Text("some words")
        >>> t.render((6,)).text
        ['some  ', 'words ']
        >>> t.set_wrap_mode('clip')
        >>> t.wrap
        'clip'
        >>> t.render((6,)).text
        ['some w']
        >>> t.wrap = 'any'  # Urwid 0.9.9 or later
        >>> t.render((6,)).text
        ['some w', 'ords  ']
        >>> t.wrap = 'somehow'
        Traceback (most recent call last):
            ...
        TextError: Wrap mode 'somehow' not supported.
        """
        if not self.layout.supports_wrap_mode(mode):
            raise TextError("Wrap mode %s not supported."%`mode`)
        self._wrap_mode = mode
        self._invalidate()

    def set_layout(self, align, wrap, layout=None):
        """
        Set layout object, align and wrap modes.
        
        align -- align mode for text layout
        wrap -- wrap mode for text layout
        layout -- layout object to use, defaults to StandardTextLayout

        >>> t = Text("hi")
        >>> t.set_layout('right', 'clip')
        >>> t
        <Text flow widget 'hi' align='right' wrap='clip'>
        """
        if layout is None:
            layout = text_layout.default_layout
        self._layout = layout
        self.set_align_mode(align)
        self.set_wrap_mode(wrap)

    align = property(lambda self:self._align_mode, set_align_mode)
    wrap = property(lambda self:self._wrap_mode, set_wrap_mode)
    layout = property(lambda self:self._layout)

    def render(self, size, focus=False):
        """
        Render contents with wrapping and alignment.  Return canvas.

        >>> Text("important things").render((18,)).text
        ['important things  ']
        >>> Text("important things").render((11,)).text
        ['important  ', 'things     ']
        """
        (maxcol,) = size
        text, attr = self.get_text()
        trans = self.get_line_translation( maxcol, (text,attr) )
        return apply_text_layout(text, attr, trans, maxcol)

    def rows(self, size, focus=False):
        """
        Return the number of rows the rendered text spans.
        
        >>> Text("important things").rows((18,))
        1
        >>> Text("important things").rows((11,))
        2
        """
        (maxcol,) = size
        return len(self.get_line_translation(maxcol))

    def get_line_translation(self, maxcol, ta=None):
        """
        Return layout structure used to map self.text to a canvas.
        This method is used internally, but may be useful for
        debugging custom layout classes.

        maxcol -- columns available for display
        ta -- None or the (text, attr) tuple returned from
              self.get_text()
        """
        if not self._cache_maxcol or self._cache_maxcol != maxcol:
            self._update_cache_translation(maxcol, ta)
        return self._cache_translation

    def _update_cache_translation(self,maxcol, ta):
        if ta:
            text, attr = ta
        else:
            text, attr = self.get_text()
        self._cache_maxcol = maxcol
        self._cache_translation = self._calc_line_translation(
            text, maxcol )
    
    def _calc_line_translation(self, text, maxcol ):
        return self.layout.layout(
            text, self._cache_maxcol, 
            self._align_mode, self._wrap_mode )
    
    def pack(self, size=None, focus=False):
        """
        Return the number of screen columns and rows required for
        this Text widget to be displayed without wrapping or 
        clipping, as a single element tuple.

        size -- None for unlimited screen columns or (maxcol,) to
                specify a maximum column size

        >>> Text("important things").pack()
        (16, 1)
        >>> Text("important things").pack((15,))
        (9, 2)
        >>> Text("important things").pack((8,))
        (8, 2)
        """
        text, attr = self.get_text()
        
        if size is not None:
            (maxcol,) = size
            if not hasattr(self.layout, "pack"):
                return size
            trans = self.get_line_translation( maxcol, (text,attr))
            cols = self.layout.pack( maxcol, trans )
            return (cols, len(trans))
    
        i = 0
        cols = 0
        while i < len(text):
            j = text.find('\n', i)
            if j == -1:
                j = len(text)
            c = calc_width(text, i, j)
            if c>cols:
                cols = c
            i = j+1
        return (cols, text.count('\n') + 1)


class EditError(TextError):
    pass
            

class Edit(Text):
    """
    Text editing widget implements cursor movement, text insertion and 
    deletion.  A caption may prefix the editing area.  Uses text class 
    for text layout.
    """
    
    # allow users of this class to listen for change events
    # sent when the value of edit_text changes
    # (this variable is picked up by the MetaSignals metaclass)
    signals = ["change"]
    
    def valid_char(self, ch):
        """Return true for printable characters."""
        return is_wide_char(ch,0) or (len(ch)==1 and ord(ch) >= 32)
    
    def selectable(self): return True

    def __init__(self, caption="", edit_text="", multiline=False,
            align=LEFT, wrap=SPACE, allow_tab=False,
            edit_pos=None, layout=None):
        """
        caption -- markup for caption preceeding edit_text
        edit_text -- text string for editing
        multiline -- True: 'enter' inserts newline  False: return it
        align -- align mode
        wrap -- wrap mode
        allow_tab -- True: 'tab' inserts 1-8 spaces  False: return it
        edit_pos -- initial position for cursor, None:at end
        layout -- layout object

        >>> Edit()
        <Edit selectable flow widget '' edit_pos=0>
        >>> Edit("Y/n? ", "yes")
        <Edit selectable flow widget 'yes' caption='Y/n? ' edit_pos=3>
        >>> Edit("Name ", "Smith", edit_pos=1)
        <Edit selectable flow widget 'Smith' caption='Name ' edit_pos=1>
        >>> Edit("", "3.14", align='right')
        <Edit selectable flow widget '3.14' align='right' edit_pos=4>
        """
        
        self.__super.__init__("", align, wrap, layout)
        self.multiline = multiline
        self.allow_tab = allow_tab
        self._edit_pos = 0
        self.set_caption(caption)
        self.set_edit_text(edit_text)
        if edit_pos is None:
            edit_pos = len(edit_text)
        self.set_edit_pos(edit_pos)
        self._shift_view_to_cursor = False
    
    def _repr_words(self):
        return self.__super._repr_words()[:-1] + [
            repr(self._edit_text)] + [
            'multiline'] * (self.multiline is True)

    def _repr_attrs(self):
        attrs = dict(self.__super._repr_attrs(),
            edit_pos=self._edit_pos,
            caption=self._caption)
        return remove_defaults(attrs, Edit.__init__)
    
    def get_text(self):
        """
        Returns (text, attributes).
        
        text -- complete text of caption and edit_text
        attributes -- run length encoded attributes for text

        >>> Edit("What? ","oh, nothing.").get_text()
        ('What? oh, nothing.', [])
        >>> Edit(('bright',"user@host:~$ "),"ls").get_text()
        ('user@host:~$ ls', [('bright', 13)])
        """
        return self._caption + self._edit_text, self._attrib
    
    def set_text(self, markup):
        """
        Not supported by Edit widget.

        >>> Edit().set_text("test")
        Traceback (most recent call last):
            ...
        EditError: set_text() not supported.  Use set_caption() or set_edit_text() instead.
        """
        # hack to let Text.__init__() work
        if not hasattr(self, '_text') and markup == "":
            self._text = None
            return

        raise EditError("set_text() not supported.  Use set_caption()"
            " or set_edit_text() instead.")

    def get_pref_col(self, size):
        """
        Return the preferred column for the cursor, or the
        current cursor x value.  May also return 'left' or 'right'
        to indicate the leftmost or rightmost column available.

        This method is used internally and by other widgets when
        moving the cursor up or down between widgets so that the 
        column selected is one that the user would expect.

        >>> size = (10,)
        >>> Edit().get_pref_col(size)
        0
        >>> e = Edit("","word")
        >>> e.get_pref_col(size)
        4
        >>> e.keypress(size, 'left')
        >>> e.get_pref_col(size)
        3
        >>> e.keypress(size, 'end')
        >>> e.get_pref_col(size)
        'right'
        >>> e = Edit("","2\\nwords")
        >>> e.keypress(size, 'left')
        >>> e.keypress(size, 'up')
        >>> e.get_pref_col(size)
        4
        >>> e.keypress(size, 'left')
        >>> e.get_pref_col(size)
        0
        """
        (maxcol,) = size
        pref_col, then_maxcol = self.pref_col_maxcol
        if then_maxcol != maxcol:
            return self.get_cursor_coords((maxcol,))[0]
        else:
            return pref_col
    
    def update_text(self):
        """
        No longer supported.
        
        >>> Edit().update_text()
        Traceback (most recent call last):
            ...
        EditError: update_text() has been removed.  Use set_caption() or set_edit_text() instead.
        """
        raise EditError("update_text() has been removed.  Use "
            "set_caption() or set_edit_text() instead.")

    def set_caption(self, caption):
        """
        Set the caption markup for this widget.

        caption -- see Text.__init__() for description of markup
        
        >>> e = Edit("")
        >>> e.set_caption("cap1")
        >>> e.caption
        'cap1'
        >>> e.set_caption(('bold', "cap2"))
        >>> e.caption
        'cap2'
        >>> e.attrib
        [('bold', 4)]
        >>> e.caption = "cap3"  # not supported because caption stores text but set_caption() takes markup
        Traceback (most recent call last):
            ...  
        AttributeError: can't set attribute
        """
        self._caption, self._attrib = decompose_tagmarkup(caption)
        self._invalidate()
    
    caption = property(lambda self:self._caption)

    def set_edit_pos(self, pos):
        """
        Set the cursor position with a self.edit_text offset.  
        Clips pos to [0, len(edit_text)].

        >>> e = Edit("", "word")
        >>> e.edit_pos
        4
        >>> e.set_edit_pos(2)
        >>> e.edit_pos
        2
        >>> e.edit_pos = -1  # Urwid 0.9.9 or later
        >>> e.edit_pos
        0
        >>> e.edit_pos = 20
        >>> e.edit_pos
        4
        """
        if pos < 0:
            pos = 0
        if pos > len(self._edit_text):
            pos = len(self._edit_text)
        self.highlight = None
        self.pref_col_maxcol = None, None
        self._edit_pos = pos
        self._invalidate()
    
    edit_pos = property(lambda self:self._edit_pos, set_edit_pos)
    
    def set_edit_text(self, text):
        """
        Set the edit text for this widget.
        
        >>> e = Edit()
        >>> e.set_edit_text("yes")
        >>> e.edit_text
        'yes'
        >>> e
        <Edit selectable flow widget 'yes' edit_pos=0>
        >>> e.edit_text = "no"  # Urwid 0.9.9 or later
        >>> e.edit_text
        'no'
        """
        if type(text) not in (str, unicode):
            try:
                text = unicode(text)
            except:
                raise EditError("Can't convert edit text to a string!")
        self.highlight = None
        self._emit("change", text)
        self._edit_text = text
        if self.edit_pos > len(text):
            self.edit_pos = len(text)
        self._invalidate()

    def get_edit_text(self):
        """
        Return the edit text for this widget.

        >>> e = Edit("What? ", "oh, nothing.")
        >>> e.get_edit_text()
        'oh, nothing.'
        >>> e.edit_text
        'oh, nothing.'
        """
        return self._edit_text
    
    edit_text = property(get_edit_text, set_edit_text)

    def insert_text(self, text):
        """
        Insert text at the cursor position and update cursor.
        This method is used by the keypress() method when inserting
        one or more characters into edit_text.

        >>> e = Edit("", "42")
        >>> e.insert_text(".5")
        >>> e
        <Edit selectable flow widget '42.5' edit_pos=4>
        >>> e.set_edit_pos(2)
        >>> e.insert_text("a")
        >>> e.edit_text
        '42a.5'
        """
        p = self.edit_pos
        self.set_edit_text(self._edit_text[:p] + text + 
            self._edit_text[p:])
        self.set_edit_pos(self.edit_pos + len(text))
    
    def keypress(self, size, key):
        """
        Handle editing keystrokes, return others.
        
        >>> e, size = Edit(), (20,)
        >>> e.keypress(size, 'x')
        >>> e.keypress(size, 'left')
        >>> e.keypress(size, '1')
        >>> e.edit_text
        '1x'
        >>> e.keypress(size, 'backspace')
        >>> e.keypress(size, 'end')
        >>> e.keypress(size, '2')
        >>> e.edit_text
        'x2'
        >>> e.keypress(size, 'shift f1')
        'shift f1'
        """
        (maxcol,) = size

        p = self.edit_pos
        if self.valid_char(key):
            self._delete_highlighted()
            self.insert_text( key )
            
        elif key=="tab" and self.allow_tab:
            self._delete_highlighted() 
            key = " "*(8-(self.edit_pos%8))
            self.insert_text( key )

        elif key=="enter" and self.multiline:
            self._delete_highlighted() 
            key = "\n"
            self.insert_text( key )

        elif command_map[key] == 'cursor left':
            if p==0: return key
            p = move_prev_char(self.edit_text,0,p)
            self.set_edit_pos(p)
        
        elif command_map[key] == 'cursor right':
            if p >= len(self.edit_text): return key
            p = move_next_char(self.edit_text,p,len(self.edit_text))
            self.set_edit_pos(p)
        
        elif command_map[key] in ('cursor up', 'cursor down'):
            self.highlight = None
            
            x,y = self.get_cursor_coords((maxcol,))
            pref_col = self.get_pref_col((maxcol,))
            assert pref_col is not None
            #if pref_col is None: 
            #    pref_col = x

            if command_map[key] == 'cursor up': y -= 1
            else: y += 1

            if not self.move_cursor_to_coords((maxcol,),pref_col,y):
                return key
        
        elif key=="backspace":
            self._delete_highlighted()
            self.pref_col_maxcol = None, None
            if p == 0: return key
            p = move_prev_char(self.edit_text,0,p)
            self.set_edit_text( self.edit_text[:p] + 
                self.edit_text[self.edit_pos:] )
            self.set_edit_pos( p )

        elif key=="delete":
            self._delete_highlighted()
            self.pref_col_maxcol = None, None
            if p >= len(self.edit_text):
                return key
            p = move_next_char(self.edit_text,p,len(self.edit_text))
            self.set_edit_text( self.edit_text[:self.edit_pos] + 
                self.edit_text[p:] )
        
        elif command_map[key] in ('cursor max left', 'cursor max right'):
            self.highlight = None
            self.pref_col_maxcol = None, None
            
            x,y = self.get_cursor_coords((maxcol,))
            
            if command_map[key] == 'cursor max left':
                self.move_cursor_to_coords((maxcol,), LEFT, y)
            else:
                self.move_cursor_to_coords((maxcol,), RIGHT, y)
            return
            
            
        else:
            # key wasn't handled
            return key

    def move_cursor_to_coords(self, size, x, y):
        """
        Set the cursor position with (x,y) coordinates.
        Returns True if move succeeded, False otherwise.
        
        >>> size = (10,)
        >>> e = Edit("","edit\\ntext")
        >>> e.move_cursor_to_coords(size, 5, 0)
        True
        >>> e.edit_pos
        4
        >>> e.move_cursor_to_coords(size, 5, 3)
        False
        >>> e.move_cursor_to_coords(size, 0, 1)
        True
        >>> e.edit_pos
        5
        """
        (maxcol,) = size
        trans = self.get_line_translation(maxcol)
        top_x, top_y = self.position_coords(maxcol, 0)
        if y < top_y or y >= len(trans):
            return False

        pos = calc_pos( self.get_text()[0], trans, x, y )
        e_pos = pos - len(self.caption)
        if e_pos < 0: e_pos = 0
        if e_pos > len(self.edit_text): e_pos = len(self.edit_text)
        self.edit_pos = e_pos
        self.pref_col_maxcol = x, maxcol
        self._invalidate()
        return True

    def mouse_event(self, size, event, button, x, y, focus):
        """
        Move the cursor to the location clicked for button 1.

        >>> size = (20,)
        >>> e = Edit("","words here")
        >>> e.mouse_event(size, 'mouse press', 1, 2, 0, True)
        True
        >>> e.edit_pos
        2
        """
        (maxcol,) = size
        if button==1:
            return self.move_cursor_to_coords( (maxcol,), x, y )


    def _delete_highlighted(self):
        """
        Delete all highlighted text and update cursor position, if any
        text is highlighted.
        """
        if not self.highlight: return
        start, stop = self.highlight
        btext, etext = self.edit_text[:start], self.edit_text[stop:]
        self.set_edit_text( btext + etext )
        self.edit_pos = start
        self.highlight = None
        
        
    def render(self, size, focus=False):
        """ 
        Render edit widget and return canvas.  Include cursor when in
        focus.

        >>> c = Edit("? ","yes").render((10,), focus=True)
        >>> c.text
        ['? yes     ']
        >>> c.cursor
        (5, 0)
        """
        (maxcol,) = size
        self._shift_view_to_cursor = bool(focus)
        
        canv = Text.render(self,(maxcol,))
        if focus:
            canv = CompositeCanvas(canv)
            canv.cursor = self.get_cursor_coords((maxcol,))

        # .. will need to FIXME if I want highlight to work again
        #if self.highlight:
        #    hstart, hstop = self.highlight_coords()
        #    d.coords['highlight'] = [ hstart, hstop ]
        return canv

    
    def get_line_translation(self, maxcol, ta=None ):
        trans = Text.get_line_translation(self, maxcol, ta)
        if not self._shift_view_to_cursor: 
            return trans
        
        text, ignore = self.get_text()
        x,y = calc_coords( text, trans, 
            self.edit_pos + len(self.caption) )
        if x < 0:
            return ( trans[:y]
                + [shift_line(trans[y],-x)]
                + trans[y+1:] )
        elif x >= maxcol:
            return ( trans[:y] 
                + [shift_line(trans[y],-(x-maxcol+1))]
                + trans[y+1:] )
        return trans
            

    def get_cursor_coords(self, size):
        """
        Return the (x,y) coordinates of cursor within widget.
        
        >>> Edit("? ","yes").get_cursor_coords((10,))
        (5, 0)
        """
        (maxcol,) = size

        self._shift_view_to_cursor = True
        return self.position_coords(maxcol,self.edit_pos)
    
    
    def position_coords(self,maxcol,pos):
        """
        Return (x,y) coordinates for an offset into self.edit_text.
        """
        
        p = pos + len(self.caption)
        trans = self.get_line_translation(maxcol)
        x,y = calc_coords(self.get_text()[0], trans,p)
        return x,y

        




class IntEdit(Edit):
    """Edit widget for integer values"""

    def valid_char(self, ch):
        """
        Return true for decimal digits.
        """
        return len(ch)==1 and ch in "0123456789"
    
    def __init__(self,caption="",default=None):
        """
        caption -- caption markup
        default -- default edit value

        >>> IntEdit("", 42)
        <IntEdit selectable flow widget '42' edit_pos=2>
        """
        if default is not None: val = str(default)
        else: val = ""
        self.__super.__init__(caption,val)

    def keypress(self, size, key):
        """
        Handle editing keystrokes.  Remove leading zeros.
        
        >>> e, size = IntEdit("", 5002), (10,)
        >>> e.keypress(size, 'home')
        >>> e.keypress(size, 'delete')
        >>> e.edit_text
        '002'
        >>> e.keypress(size, 'end')
        >>> e.edit_text
        '2'
        """
        (maxcol,) = size
        unhandled = Edit.keypress(self,(maxcol,),key)

        if not unhandled:
        # trim leading zeros
            while self.edit_pos > 0 and self.edit_text[:1] == "0":
                self.set_edit_pos( self.edit_pos - 1)
                self.set_edit_text(self.edit_text[1:])

        return unhandled

    def value(self):
        """
        Return the numeric value of self.edit_text.
        
        >>> e, size = IntEdit(), (10,)
        >>> e.keypress(size, '5')
        >>> e.keypress(size, '1')
        >>> e.value() == 51
        True
        """
        if self.edit_text:
            return long(self.edit_text)
        else:
            return 0


class WidgetWrapError(Exception):
    pass

class WidgetWrap(Widget):
    no_cache = ["rows"]

    def __init__(self, w):
        """
        w -- widget to wrap, stored as self._w

        This object will pass the functions defined in Widget interface
        definition to self._w.

        The purpose of this widget is to provide a base class for
        widgets that compose other widgets for their display and
        behaviour.  The details of that composition should not affect
        users of the subclass.  The subclass may decide to expose some
        of the wrapped widgets by behaving like a ContainerWidget or
        WidgetDecoration, or it may hide them from outside access.
        """
        self.__w = w

    def _set_w(self, w):
        """
        Change the wrapped widget.  This is meant to be called
        only by subclasses.

        >>> size = (10,)
        >>> ww = WidgetWrap(Edit("hello? ","hi"))
        >>> ww.render(size).text
        ['hello? hi ']
        >>> ww.selectable()
        True
        >>> ww._w = Text("goodbye") # calls _set_w()
        >>> ww.render(size).text
        ['goodbye   ']
        >>> ww.selectable()
        False
        """
        self.__w = w
        self._invalidate()
    _w = property(lambda self:self.__w, _set_w)

    def _raise_old_name_error(self, val=None):
        raise WidgetWrapError("The WidgetWrap.w member variable has "
            "been renamed to WidgetWrap._w (not intended for use "
            "outside the class and its subclasses).  "
            "Please update your code to use self._w "
            "instead of self.w.")
    w = property(_raise_old_name_error, _raise_old_name_error)

    def render(self, size, focus=False):
        """Render self._w."""
        canv = self._w.render(size, focus=focus)
        return CompositeCanvas(canv)

    selectable = property(lambda self:self.__w.selectable)
    get_cursor_coords = property(lambda self:self.__w.get_cursor_coords)
    get_pref_col = property(lambda self:self.__w.get_pref_col)
    keypress = property(lambda self:self.__w.keypress)
    move_cursor_to_coords = property(lambda self:self.__w.move_cursor_to_coords)
    rows = property(lambda self:self.__w.rows)
    mouse_event = property(lambda self:self.__w.mouse_event)
    sizing = property(lambda self:self.__w.sizing)


def _test():
    import doctest
    doctest.testmod()

if __name__=='__main__':
    _test()

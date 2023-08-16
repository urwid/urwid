# Urwid basic widget classes
#    Copyright (C) 2004-2012  Ian Ward
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


from __future__ import annotations

import enum
import functools
import typing
import warnings
from operator import attrgetter

from urwid import signals, text_layout
from urwid.canvas import CanvasCache, CompositeCanvas, SolidCanvas, apply_text_layout
from urwid.command_map import Command, command_map
from urwid.split_repr import remove_defaults, split_repr
from urwid.util import MetaSuper, calc_width, decompose_tagmarkup, is_wide_char, move_next_char, move_prev_char

if typing.TYPE_CHECKING:
    from collections.abc import Callable

    from typing_extensions import Literal

    from urwid.canvas import TextCanvas


# define some names for these constants to avoid misspellings in the source
# and to document the constant strings we are using


class Sizing(str, enum.Enum):
    """Widget sizing methods."""

    FLOW = "flow"
    BOX = "box"
    FIXED = "fixed"


class Align(str, enum.Enum):
    """Text alignment modes"""

    LEFT = "left"
    RIGHT = "right"
    CENTER = "center"


class VAlign(str, enum.Enum):
    """Filler alignment"""

    TOP = "top"
    MIDDLE = "middle"
    BOTTOM = "bottom"


class WrapMode(str, enum.Enum):
    """Text wrapping modes"""

    SPACE = "space"
    ANY = "any"
    CLIP = "clip"
    ELLIPSIS = "ellipsis"


class WHSettings(str, enum.Enum):
    """Width and Height settings"""

    PACK = "pack"
    GIVEN = "given"
    RELATIVE = "relative"
    WEIGHT = "weight"
    CLIP = "clip"  # Sizing settings also use clip


# Backward compatibility
FLOW = Sizing.FLOW
BOX = Sizing.BOX
FIXED = Sizing.FIXED

LEFT = Align.LEFT
RIGHT = Align.RIGHT
CENTER = Align.CENTER

TOP = VAlign.TOP
MIDDLE = VAlign.MIDDLE
BOTTOM = VAlign.BOTTOM

SPACE = WrapMode.SPACE
ANY = WrapMode.ANY
CLIP = WrapMode.CLIP
ELLIPSIS = WrapMode.ELLIPSIS

PACK = WHSettings.PACK
GIVEN = WHSettings.GIVEN
RELATIVE = WHSettings.RELATIVE
RELATIVE_100 = (WHSettings.RELATIVE, 100)
WEIGHT = WHSettings.WEIGHT


class WidgetMeta(MetaSuper, signals.MetaSignals):
    """
    Bases: :class:`MetaSuper`, :class:`MetaSignals`

    Automatic caching of render and rows methods.

    Class variable *no_cache* is a list of names of methods to not cache
    automatically.  Valid method names for *no_cache* are ``'render'`` and
    ``'rows'``.

    Class variable *ignore_focus* if defined and set to ``True`` indicates
    that the canvas this widget renders is not affected by the focus
    parameter, so it may be ignored when caching.
    """

    def __init__(cls, name, bases, d):
        no_cache = d.get("no_cache", [])

        super().__init__(name, bases, d)

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
    Raise a WidgetError if a canv does not match size.
    """
    if (size and size[1:] != (0,) and size[0] != canv.cols()) or (len(size) > 1 and size[1] != canv.rows()):
        raise WidgetError(
            f"Widget {widget!r} rendered ({canv.cols():d} x {canv.rows():d}) canvas when passed size {size!r}!"
        )


def cache_widget_render(cls):
    """
    Return a function that wraps the cls.render() method
    and fetches and stores canvases with CanvasCache.
    """
    ignore_focus = bool(getattr(cls, "ignore_focus", False))
    fn = cls.render

    @functools.wraps(fn)
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
    return cached_render


def nocache_widget_render(cls):
    """
    Return a function that wraps the cls.render() method
    and finalizes the canvas that it returns.
    """
    fn = cls.render
    if hasattr(fn, "original_fn"):
        fn = fn.original_fn

    @functools.wraps(fn)
    def finalize_render(self, size, focus=False):
        canv = fn(self, size, focus=focus)
        if canv.widget_info:
            canv = CompositeCanvas(canv)
        validate_size(self, size, canv)
        canv.finalize(self, size, focus)
        return canv

    finalize_render.original_fn = fn
    return finalize_render


def nocache_widget_render_instance(self):
    """
    Return a function that wraps the cls.render() method
    and finalizes the canvas that it returns, but does not
    cache the canvas.
    """
    fn = self.render.original_fn

    @functools.wraps(fn)
    def finalize_render(size, focus=False):
        canv = fn(self, size, focus=focus)
        if canv.widget_info:
            canv = CompositeCanvas(canv)
        canv.finalize(self, size, focus)
        return canv

    finalize_render.original_fn = fn
    return finalize_render


def cache_widget_rows(cls):
    """
    Return a function that wraps the cls.rows() method
    and returns rows from the CanvasCache if available.
    """
    ignore_focus = bool(getattr(cls, "ignore_focus", False))
    fn = cls.rows

    @functools.wraps(fn)
    def cached_rows(self, size, focus=False):
        focus = focus and not ignore_focus
        canv = CanvasCache.fetch(self, cls, size, focus)
        if canv:
            return canv.rows()

        return fn(self, size, focus)

    return cached_rows


class Widget(metaclass=WidgetMeta):
    """
    Widget base class

    .. attribute:: _selectable
       :annotation: = False

       The default :meth:`.selectable` method returns this
       value.

    .. attribute:: _sizing
       :annotation: = frozenset(['flow', 'box', 'fixed'])

       The default :meth:`.sizing` method returns this value.

    .. attribute:: _command_map
       :annotation: = urwid.command_map

       A shared :class:`CommandMap` instance. May be redefined
       in subclasses or widget instances.

    .. method:: render(size, focus=False)

       .. note::

          This method is not implemented in :class:`.Widget` but
          must be implemented by any concrete subclass

       :param size: One of the following,
                    *maxcol* and *maxrow* are integers > 0:

                    (*maxcol*, *maxrow*)
                      for box sizing -- the parent chooses the exact
                      size of this widget

                    (*maxcol*,)
                      for flow sizing -- the parent chooses only the
                      number of columns for this widget

                    ()
                      for fixed sizing -- this widget is a fixed size
                      which can't be adjusted by the parent
       :type size: widget size
       :param focus: set to ``True`` if this widget or one of its children
                     is in focus
       :type focus: bool

       :returns: A :class:`Canvas` subclass instance containing the
                 rendered content of this widget

       :class:`Text` widgets return a :class:`TextCanvas` (arbitrary text and
       display attributes), :class:`SolidFill` widgets return a
       :class:`SolidCanvas` (a single character repeated across
       the whole surface) and container widgets return a
       :class:`CompositeCanvas` (one or more other canvases
       arranged arbitrarily).

       If *focus* is ``False``, the returned canvas may not have a cursor
       position set.

       There is some metaclass magic defined in the :class:`Widget`
       metaclass :class:`WidgetMeta` that causes the
       result of this method to be cached by :class:`CanvasCache`.
       Later calls will automatically look up the value in the cache first.

       As a small optimization the class variable :attr:`ignore_focus`
       may be defined and set to ``True`` if this widget renders the same
       canvas regardless of the value of the *focus* parameter.

       Any time the content of a widget changes it should call
       :meth:`_invalidate` to remove any cached canvases, or the widget
       may render the cached canvas instead of creating a new one.


    .. method:: rows(size, focus=False)

       .. note::

          This method is not implemented in :class:`.Widget` but
          must be implemented by any flow widget.  See :meth:`.sizing`.

       See :meth:`Widget.render` for parameter details.

       :returns: The number of rows required for this widget given a number
                 of columns in *size*

       This is the method flow widgets use to communicate their size to other
       widgets without having to render a canvas. This should be a quick
       calculation as this function may be called a number of times in normal
       operation. If your implementation may take a long time you should add
       your own caching here.

       There is some metaclass magic defined in the :class:`Widget`
       metaclass :class:`WidgetMeta` that causes the
       result of this function to be retrieved from any
       canvas cached by :class:`CanvasCache`, so if your widget
       has been rendered you may not receive calls to this function. The class
       variable :attr:`ignore_focus` may be defined and set to ``True`` if this
       widget renders the same size regardless of the value of the *focus*
       parameter.


    .. method:: keypress(size, key)

       .. note::

          This method is not implemented in :class:`.Widget` but
          must be implemented by any selectable widget.
          See :meth:`.selectable`.

       :param size: See :meth:`Widget.render` for details
       :type size: widget size
       :param key: a single keystroke value; see :ref:`keyboard-input`
       :type key: bytes or unicode

       :returns: ``None`` if *key* was handled by this widget or
                 *key* (the same value passed) if *key* was not handled
                 by this widget

       Container widgets will typically call the :meth:`keypress` method on
       whichever of their children is set as the focus.

       The standard widgets use :attr:`_command_map` to
       determine what action should be performed for a given *key*. You may
       modify these values to your liking globally, at some level in the
       widget hierarchy or on individual widgets. See :class:`CommandMap`
       for the defaults.

       In your own widgets you may use whatever logic you like: filtering or
       translating keys, selectively passing along events etc.



    .. method:: mouse_event(size, event, button, col, row, focus)

       .. note::

          This method is not implemented in :class:`.Widget` but
          may be implemented by a subclass.  Not implementing this
          method is equivalent to having a method that always returns
          ``False``.

       :param size: See :meth:`Widget.render` for details.
       :type size: widget size
       :param event: Values such as ``'mouse press'``, ``'ctrl mouse press'``,
                     ``'mouse release'``, ``'meta mouse release'``,
                     ``'mouse drag'``; see :ref:`mouse-input`
       :type event: mouse event
       :param button: 1 through 5 for press events, often 0 for release events
                      (which button was released is often not known)
       :type button: int
       :param col: Column of the event, 0 is the left edge of this widget
       :type col: int
       :param row: Row of the event, 0 it the top row of this widget
       :type row: int
       :param focus: Set to ``True`` if this widget or one of its children
                     is in focus
       :type focus: bool

       :returns: ``True`` if the event was handled by this widget, ``False``
                 otherwise

       Container widgets will typically call the :meth:`mouse_event` method on
       whichever of their children is at the position (*col*, *row*).


    .. method:: get_cursor_coords(size)

       .. note::

          This method is not implemented in :class:`.Widget` but
          must be implemented by any widget that may return cursor
          coordinates as part of the canvas that :meth:`render` returns.

       :param size: See :meth:`Widget.render` for details.
       :type size: widget size

       :returns: (*col*, *row*) if this widget has a cursor, ``None`` otherwise

       Return the cursor coordinates (*col*, *row*) of a cursor that will appear
       as part of the canvas rendered by this widget when in focus, or ``None``
       if no cursor is displayed.

       The :class:`ListBox` widget
       uses this method to make sure a cursor in the focus widget is not
       scrolled out of view.  It is a separate method to avoid having to render
       the whole widget while calculating layout.

       Container widgets will typically call the :meth:`.get_cursor_coords`
       method on their focus widget.


    .. method:: get_pref_col(size)

       .. note::

          This method is not implemented in :class:`.Widget` but
          may be implemented by a subclass.

       :param size: See :meth:`Widget.render` for details.
       :type size: widget size

       :returns: a column number or ``'left'`` for the leftmost available
                 column or ``'right'`` for the rightmost available column

       Return the preferred column for the cursor to be displayed in this
       widget. This value might not be the same as the column returned from
       :meth:`get_cursor_coords`.

       The :class:`ListBox` and :class:`Pile`
       widgets call this method on a widget losing focus and use the value
       returned to call :meth:`.move_cursor_to_coords` on the widget becoming
       the focus. This allows the focus to move up and down through widgets
       while keeping the cursor in approximately the same column on screen.


    .. method:: move_cursor_to_coords(size, col, row)

       .. note::

          This method is not implemented in :class:`.Widget` but
          may be implemented by a subclass.  Not implementing this
          method is equivalent to having a method that always returns
          ``False``.

       :param size: See :meth:`Widget.render` for details.
       :type size: widget size
       :param col: new column for the cursor, 0 is the left edge of this widget
       :type col: int
       :param row: new row for the cursor, 0 it the top row of this widget
       :type row: int

       :returns: ``True`` if the position was set successfully anywhere on
                 *row*, ``False`` otherwise
    """

    _selectable = False
    _sizing = frozenset([Sizing.FLOW, Sizing.BOX, Sizing.FIXED])
    _command_map = command_map

    def _invalidate(self) -> None:
        """
        Mark cached canvases rendered by this widget as dirty so that
        they will not be used again.
        """
        CanvasCache.invalidate(self)

    def _emit(self, name: str, *args):
        """
        Convenience function to emit signals with self as first
        argument.
        """
        signals.emit_signal(self, name, self, *args)

    def selectable(self):
        """
        :returns: ``True`` if this is a widget that is designed to take the
                  focus, i.e. it contains something the user might want to
                  interact with, ``False`` otherwise,

        This default implementation returns :attr:`._selectable`.
        Subclasses may leave these is if the are not selectable,
        or if they are always selectable they may
        set the :attr:`_selectable` class variable to ``True``.

        If this method returns ``True`` then the :meth:`.keypress` method
        must be implemented.

        Returning ``False`` does not guarantee that this widget will never be in
        focus, only that this widget will usually be skipped over when changing
        focus. It is still possible for non selectable widgets to have the focus
        (typically when there are no other selectable widgets visible).
        """
        return self._selectable

    def sizing(self):
        """
        :returns: A frozenset including one or more of ``'box'``, ``'flow'`` and
                  ``'fixed'``.  Default implementation returns the value of
                  :attr:`._sizing`, which for this class includes all three.

        The sizing modes returned indicate the modes that may be
        supported by this widget, but is not sufficient to know
        that using that sizing mode will work.  Subclasses should
        make an effort to remove sizing modes they know will not
        work given the state of the widget, but many do not yet
        do this.

        If a sizing mode is missing from the set then the widget
        should fail when used in that mode.

        If ``'flow'`` is among the values returned then the other
        methods in this widget must be able to accept a
        single-element tuple (*maxcol*,) to their ``size``
        parameter, and the :meth:`rows` method must be defined.

        If ``'box'`` is among the values returned then the other
        methods must be able to accept a two-element tuple
        (*maxcol*, *maxrow*) to their size parameter.

        If ``'fixed'`` is among the values returned then the other
        methods must be able to accept an empty tuple () to
        their size parameter, and the :meth:`pack` method must
        be defined.
        """
        return self._sizing

    def pack(self, size: tuple[()] | tuple[int] | tuple[int, int], focus: bool = False) -> tuple[int, int]:
        """
        See :meth:`Widget.render` for parameter details.

        :returns: A "packed" size (*maxcol*, *maxrow*) for this widget

        Calculate and return a minimum
        size where all content could still be displayed. Fixed widgets must
        implement this method and return their size when ``()`` is passed as the
        *size* parameter.

        This default implementation returns the *size* passed, or the *maxcol*
        passed and the value of :meth:`rows` as the *maxrow* when (*maxcol*,)
        is passed as the *size* parameter.

        .. note::

           This is a new method that hasn't been fully implemented across the
           standard widget types. In particular it has not yet been
           implemented for container widgets.

        :class:`Text` widgets have implemented this method.
        You can use :meth:`Text.pack` to calculate the minimum
        columns and rows required to display a text widget without wrapping,
        or call it iteratively to calculate the minimum number of columns
        required to display the text wrapped into a target number of rows.
        """
        if not size:
            if Sizing.FIXED in self.sizing():
                raise NotImplementedError("Fixed widgets must override Widget.pack()")
            raise WidgetError(f"Cannot pack () size, this is not a fixed widget: {self!r}")

        if len(size) == 1:
            if Sizing.FLOW in self.sizing():
                return (*size, self.rows(size, focus))

            raise WidgetError(f"Cannot pack (maxcol,) size, this is not a flow widget: {self!r}")

        return size

    @property
    def base_widget(self) -> Widget:
        """
        Read-only property that steps through decoration widgets
        and returns the one at the base.  This default implementation
        returns self.
        """
        return self

    @property
    def focus(self) -> Widget | None:
        """
        Read-only property returning the child widget in focus for
        container widgets.  This default implementation
        always returns ``None``, indicating that this widget has no children.
        """
        return None

    def _not_a_container(self, val=None):
        raise IndexError(f"No focus_position, {self!r} is not a container widget")

    focus_position = property(
        _not_a_container,
        _not_a_container,
        doc="""
        Property for reading and setting the focus position for
        container widgets. This default implementation raises
        :exc:`IndexError`, making normal widgets fail the same way
        accessing :attr:`.focus_position` on an empty container widget would.
        """,
    )

    def __repr__(self):
        """
        A friendly __repr__ for widgets, designed to be extended
        by subclasses with _repr_words and _repr_attr methods.
        """
        return split_repr(self)

    def _repr_words(self):
        words = []
        if self.selectable():
            words = ["selectable", *words]
        if self.sizing() and self.sizing() != frozenset([Sizing.FLOW, Sizing.BOX, Sizing.FIXED]):
            words.append("/".join(sorted(self.sizing())))
        return [*words, "widget"]

    def _repr_attrs(self):
        return {}


class FlowWidget(Widget):
    """
    Deprecated.  Inherit from Widget and add:

        _sizing = frozenset(['flow'])

    at the top of your class definition instead.

    Base class of widgets that determine their rows from the number of
    columns available.
    """

    _sizing = frozenset([Sizing.FLOW])

    def __init__(self, *args, **kwargs):
        warnings.warn(
            """
            FlowWidget is deprecated. Inherit from Widget and add:

                _sizing = frozenset(['flow'])

            at the top of your class definition instead.""",
            DeprecationWarning,
            stacklevel=3,
        )

    def rows(self, size: int, focus: bool = False) -> int:
        """
        All flow widgets must implement this function.
        """
        raise NotImplementedError()

    def render(self, size: tuple[int], focus: bool = False):
        """
        All widgets must implement this function.
        """
        raise NotImplementedError()


class BoxWidget(Widget):
    """
    Deprecated.  Inherit from Widget and add:

        _sizing = frozenset(['box'])
        _selectable = True

    at the top of your class definition instead.

    Base class of width and height constrained widgets such as
    the top level widget attached to the display object
    """

    _selectable = True
    _sizing = frozenset([Sizing.BOX])

    def __init__(self, *args, **kwargs):
        warnings.warn(
            """
            BoxWidget is deprecated. Inherit from Widget and add:

                _sizing = frozenset(['box'])
                _selectable = True

            at the top of your class definition instead.""",
            DeprecationWarning,
            stacklevel=3,
        )

    def render(self, size: tuple[int, int], focus: bool = False):
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
        raise ValueError(f"FixedWidget takes only () for size.passed: {size!r}")


class FixedWidget(Widget):
    """
    Deprecated.  Inherit from Widget and add:

        _sizing = frozenset(['fixed'])

    at the top of your class definition instead.

    Base class of widgets that know their width and height and
    cannot be resized
    """

    _sizing = frozenset([Sizing.FIXED])

    def __init__(self, *args, **kwargs):
        warnings.warn(
            """
            FixedWidget is deprecated. Inherit from Widget and add:

                _sizing = frozenset(['fixed'])

            at the top of your class definition instead.""",
            DeprecationWarning,
            stacklevel=3,
        )

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


class Divider(Widget):
    """
    Horizontal divider widget
    """

    _sizing = frozenset([Sizing.FLOW])

    ignore_focus = True

    def __init__(
        self,
        div_char: str | bytes = " ",
        top: int = 0,
        bottom: int = 0,
    ) -> None:
        """
        :param div_char: character to repeat across line
        :type div_char: bytes or unicode

        :param top: number of blank lines above
        :type top: int

        :param bottom: number of blank lines below
        :type bottom: int

        >>> Divider()
        <Divider flow widget>
        >>> Divider(u'-')
        <Divider flow widget '-'>
        >>> Divider(u'x', 1, 2)
        <Divider flow widget 'x' bottom=2 top=1>
        """
        super().__init__()
        self.div_char = div_char
        self.top = top
        self.bottom = bottom

    def _repr_words(self):
        return super()._repr_words() + [repr(self.div_char)] * (self.div_char != " ")

    def _repr_attrs(self):
        attrs = dict(super()._repr_attrs())
        if self.top:
            attrs["top"] = self.top
        if self.bottom:
            attrs["bottom"] = self.bottom
        return attrs

    def rows(self, size: tuple[int], focus: bool = False) -> int:
        """
        Return the number of lines that will be rendered.

        >>> Divider().rows((10,))
        1
        >>> Divider(u'x', 1, 2).rows((10,))
        4
        """
        (maxcol,) = size
        return self.top + 1 + self.bottom

    def render(self, size: tuple[int], focus: bool = False):
        """
        Render the divider as a canvas and return it.

        >>> Divider().render((10,)).text # ... = b in Python 3
        [...'          ']
        >>> Divider(u'-', top=1).render((10,)).text
        [...'          ', ...'----------']
        >>> Divider(u'x', bottom=2).render((5,)).text
        [...'xxxxx', ...'     ', ...'     ']
        """
        (maxcol,) = size
        canv = CompositeCanvas(SolidCanvas(self.div_char, maxcol, 1))
        if self.top or self.bottom:
            canv.pad_trim_top_bottom(self.top, self.bottom)
        return canv


class SolidFill(Widget):
    """
    A box widget that fills an area with a single character
    """

    _selectable = False
    ignore_focus = True
    _sizing = frozenset([Sizing.BOX])

    def __init__(self, fill_char: str = " ") -> None:
        """
        :param fill_char: character to fill area with
        :type fill_char: bytes or unicode

        >>> SolidFill(u'8')
        <SolidFill box widget '8'>
        """
        super().__init__()
        self.fill_char = fill_char

    def _repr_words(self) -> list[str]:
        return [*super()._repr_words(), repr(self.fill_char)]

    def render(self, size: tuple[int, int], focus: bool = False) -> SolidCanvas:
        """
        Render the Fill as a canvas and return it.

        >>> SolidFill().render((4,2)).text # ... = b in Python 3
        [...'    ', ...'    ']
        >>> SolidFill('#').render((5,3)).text
        [...'#####', ...'#####', ...'#####']
        """
        maxcol, maxrow = size
        return SolidCanvas(self.fill_char, maxcol, maxrow)


class TextError(Exception):
    pass


class Text(Widget):
    """
    a horizontally resizeable text widget
    """

    _sizing = frozenset([Sizing.FLOW])

    ignore_focus = True
    _repr_content_length_max = 140

    def __init__(
        self,
        markup,
        align: Literal["left", "center", "right"] | Align = Align.LEFT,
        wrap: Literal["space", "any", "clip", "ellipsis"] | WrapMode = WrapMode.SPACE,
        layout=None,
    ) -> None:
        """
        :param markup: content of text widget, one of:

            bytes or unicode
              text to be displayed

            (*display attribute*, *text markup*)
              *text markup* with *display attribute* applied to all parts
              of *text markup* with no display attribute already applied

            [*text markup*, *text markup*, ... ]
              all *text markup* in the list joined together

        :type markup: :ref:`text-markup`
        :param align: typically ``'left'``, ``'center'`` or ``'right'``
        :type align: text alignment mode
        :param wrap: typically ``'space'``, ``'any'``, ``'clip'`` or ``'ellipsis'``
        :type wrap: text wrapping mode
        :param layout: defaults to a shared :class:`StandardTextLayout` instance
        :type layout: text layout instance

        >>> Text(u"Hello")
        <Text flow widget 'Hello'>
        >>> t = Text(('bold', u"stuff"), 'right', 'any')
        >>> t
        <Text flow widget 'stuff' align='right' wrap='any'>
        >>> print(t.text)
        stuff
        >>> t.attrib
        [('bold', 5)]
        """
        super().__init__()
        self._cache_maxcol = None
        self.set_text(markup)
        self.set_layout(align, wrap, layout)

    def _repr_words(self) -> list[str]:
        """
        Show the text in the repr in python3 format (b prefix for byte strings) and truncate if it's too long
        """
        first = super()._repr_words()
        text = self.get_text()[0]
        rest = repr(text)
        if len(rest) > self._repr_content_length_max:
            rest = (
                rest[: self._repr_content_length_max * 2 // 3 - 3] + "..." + rest[-self._repr_content_length_max // 3 :]
            )
        return [*first, rest]

    def _repr_attrs(self):
        attrs = dict(
            super()._repr_attrs(),
            align=self._align_mode,
            wrap=self._wrap_mode,
        )
        return remove_defaults(attrs, Text.__init__)

    def _invalidate(self) -> None:
        self._cache_maxcol = None
        super()._invalidate()

    def set_text(self, markup):
        """
        Set content of text widget.

        :param markup: see :class:`Text` for description.
        :type markup: text markup

        >>> t = Text(u"foo")
        >>> print(t.text)
        foo
        >>> t.set_text(u"bar")
        >>> print(t.text)
        bar
        >>> t.text = u"baz"  # not supported because text stores text but set_text() takes markup
        Traceback (most recent call last):
        AttributeError: can't set attribute
        """
        self._text, self._attrib = decompose_tagmarkup(markup)
        self._invalidate()

    def get_text(self):
        """
        :returns: (*text*, *display attributes*)

            *text*
              complete bytes/unicode content of text widget

            *display attributes*
              run length encoded display attributes for *text*, eg.
              ``[('attr1', 10), ('attr2', 5)]``

        >>> Text(u"Hello").get_text() # ... = u in Python 2
        (...'Hello', [])
        >>> Text(('bright', u"Headline")).get_text()
        (...'Headline', [('bright', 8)])
        >>> Text([('a', u"one"), u"two", ('b', u"three")]).get_text()
        (...'onetwothree', [('a', 3), (None, 3), ('b', 5)])
        """
        return self._text, self._attrib

    @property
    def text(self) -> str:
        """
        Read-only property returning the complete bytes/unicode content
        of this widget
        """
        return self.get_text()[0]

    @property
    def attrib(self):
        """
        Read-only property returning the run-length encoded display
        attributes of this widget
        """
        return self.get_text()[1]

    def set_align_mode(self, mode: Literal["left", "center", "right"] | Align) -> None:
        """
        Set text alignment mode. Supported modes depend on text layout
        object in use but defaults to a :class:`StandardTextLayout` instance

        :param mode: typically ``'left'``, ``'center'`` or ``'right'``
        :type mode: text alignment mode

        >>> t = Text(u"word")
        >>> t.set_align_mode('right')
        >>> t.align
        'right'
        >>> t.render((10,)).text # ... = b in Python 3
        [...'      word']
        >>> t.align = 'center'
        >>> t.render((10,)).text
        [...'   word   ']
        >>> t.align = 'somewhere'
        Traceback (most recent call last):
        TextError: Alignment mode 'somewhere' not supported.
        """
        if not self.layout.supports_align_mode(mode):
            raise TextError(f"Alignment mode {mode!r} not supported.")
        self._align_mode = mode
        self._invalidate()

    def set_wrap_mode(self, mode: Literal["space", "any", "clip", "ellipsis"] | WrapMode) -> None:
        """
        Set text wrapping mode. Supported modes depend on text layout
        object in use but defaults to a :class:`StandardTextLayout` instance

        :param mode: typically ``'space'``, ``'any'``, ``'clip'`` or ``'ellipsis'``
        :type mode: text wrapping mode

        >>> t = Text(u"some words")
        >>> t.render((6,)).text # ... = b in Python 3
        [...'some  ', ...'words ']
        >>> t.set_wrap_mode('clip')
        >>> t.wrap
        'clip'
        >>> t.render((6,)).text
        [...'some w']
        >>> t.wrap = 'any'  # Urwid 0.9.9 or later
        >>> t.render((6,)).text
        [...'some w', ...'ords  ']
        >>> t.wrap = 'somehow'
        Traceback (most recent call last):
        TextError: Wrap mode 'somehow' not supported.
        """
        if not self.layout.supports_wrap_mode(mode):
            raise TextError(f"Wrap mode {mode!r} not supported.")
        self._wrap_mode = mode
        self._invalidate()

    def set_layout(
        self,
        align: Literal["left", "center", "right"] | Align,
        wrap: Literal["space", "any", "clip", "ellipsis"] | WrapMode,
        layout=None,
    ) -> None:
        """
        Set the text layout object, alignment and wrapping modes at
        the same time.

        :type align: text alignment mode
        :param wrap: typically 'space', 'any', 'clip' or 'ellipsis'
        :type wrap: text wrapping mode
        :param layout: defaults to a shared :class:`StandardTextLayout` instance
        :type layout: text layout instance

        >>> t = Text(u"hi")
        >>> t.set_layout('right', 'clip')
        >>> t
        <Text flow widget 'hi' align='right' wrap='clip'>
        """
        if layout is None:
            layout = text_layout.default_layout
        self._layout = layout
        self.set_align_mode(align)
        self.set_wrap_mode(wrap)

    align = property(lambda self: self._align_mode, set_align_mode)
    wrap = property(lambda self: self._wrap_mode, set_wrap_mode)

    @property
    def layout(self):
        return self._layout

    def render(self, size: tuple[int], focus: bool = False) -> TextCanvas:
        """
        Render contents with wrapping and alignment.  Return canvas.

        See :meth:`Widget.render` for parameter details.

        >>> Text(u"important things").render((18,)).text # ... = b in Python 3
        [...'important things  ']
        >>> Text(u"important things").render((11,)).text
        [...'important  ', ...'things     ']
        """
        (maxcol,) = size
        text, attr = self.get_text()
        # assert isinstance(text, unicode)
        trans = self.get_line_translation(maxcol, (text, attr))
        return apply_text_layout(text, attr, trans, maxcol)

    def rows(self, size: tuple[int], focus: bool = False) -> int:
        """
        Return the number of rows the rendered text requires.

        See :meth:`Widget.rows` for parameter details.

        >>> Text(u"important things").rows((18,))
        1
        >>> Text(u"important things").rows((11,))
        2
        """
        (maxcol,) = size
        return len(self.get_line_translation(maxcol))

    def get_line_translation(self, maxcol: int, ta=None):
        """
        Return layout structure used to map self.text to a canvas.
        This method is used internally, but may be useful for
        debugging custom layout classes.

        :param maxcol: columns available for display
        :type maxcol: int
        :param ta: ``None`` or the (*text*, *display attributes*) tuple
                   returned from :meth:`.get_text`
        :type ta: text and display attributes
        """
        if not self._cache_maxcol or self._cache_maxcol != maxcol:
            self._update_cache_translation(maxcol, ta)
        return self._cache_translation

    def _update_cache_translation(self, maxcol: int, ta):
        if ta:
            text, attr = ta
        else:
            text, attr = self.get_text()
        self._cache_maxcol = maxcol
        self._cache_translation = self.layout.layout(text, maxcol, self._align_mode, self._wrap_mode)

    def pack(self, size: tuple[int] | None = None, focus: bool = False) -> tuple[int, int]:
        """
        Return the number of screen columns and rows required for
        this Text widget to be displayed without wrapping or
        clipping, as a single element tuple.

        :param size: ``None`` for unlimited screen columns or (*maxcol*,) to
                     specify a maximum column size
        :type size: widget size

        >>> Text(u"important things").pack()
        (16, 1)
        >>> Text(u"important things").pack((15,))
        (9, 2)
        >>> Text(u"important things").pack((8,))
        (8, 2)
        """
        text, attr = self.get_text()

        if size is not None:
            (maxcol,) = size
            if not hasattr(self.layout, "pack"):
                return size
            trans = self.get_line_translation(maxcol, (text, attr))
            cols = self.layout.pack(maxcol, trans)
            return (cols, len(trans))

        i = 0
        cols = 0
        while i < len(text):
            j = text.find("\n", i)
            if j == -1:
                j = len(text)
            c = calc_width(text, i, j)
            if c > cols:
                cols = c
            i = j + 1
        return (cols, text.count("\n") + 1)


class EditError(TextError):
    pass


class Edit(Text):
    """
    Text editing widget implements cursor movement, text insertion and
    deletion.  A caption may prefix the editing area.  Uses text class
    for text layout.

    Users of this class may listen for ``"change"`` or ``"postchange"``
    events.  See :func:``connect_signal``.

    * ``"change"`` is sent just before the value of edit_text changes.
      It receives the new text as an argument.  Note that ``"change"`` cannot
      change the text in question as edit_text changes the text afterwards.
    * ``"postchange"`` is sent after the value of edit_text changes.
      It receives the old value of the text as an argument and thus is
      appropriate for changing the text.  It is possible for a ``"postchange"``
      event handler to get into a loop of changing the text and then being
      called when the event is re-emitted.  It is up to the event
      handler to guard against this case (for instance, by not changing the
      text if it is signaled for for text that it has already changed once).
    """

    _selectable = True
    ignore_focus = False
    # (this variable is picked up by the MetaSignals metaclass)
    signals: typing.ClassVar[list[str]] = ["change", "postchange"]

    def valid_char(self, ch: str) -> bool:
        """
        Filter for text that may be entered into this widget by the user

        :param ch: character to be inserted
        :type ch: str

        This implementation returns True for all printable characters.
        """
        return is_wide_char(ch, 0) or (len(ch) == 1 and ord(ch) >= 32)

    def __init__(
        self,
        caption="",
        edit_text: str | bytes = "",
        multiline: bool = False,
        align: Literal["left", "center", "right"] | Align = Align.LEFT,
        wrap: Literal["space", "any", "clip", "ellipsis"] | WrapMode = WrapMode.SPACE,
        allow_tab: bool = False,
        edit_pos: int | None = None,
        layout=None,
        mask: str | bytes | None = None,
    ) -> None:
        """
        :param caption: markup for caption preceding edit_text, see
                        :class:`Text` for description of text markup.
        :type caption: text markup
        :param edit_text: initial text for editing, type (bytes or unicode)
                          must match the text in the caption
        :type edit_text: bytes or unicode
        :param multiline: True: 'enter' inserts newline  False: return it
        :type multiline: bool
        :param align: typically 'left', 'center' or 'right'
        :type align: text alignment mode
        :param wrap: typically 'space', 'any' or 'clip'
        :type wrap: text wrapping mode
        :param allow_tab: True: 'tab' inserts 1-8 spaces  False: return it
        :type allow_tab: bool
        :param edit_pos: initial position for cursor, None:end of edit_text
        :type edit_pos: int
        :param layout: defaults to a shared :class:`StandardTextLayout` instance
        :type layout: text layout instance
        :param mask: hide text entered with this character, None:disable mask
        :type mask: bytes or unicode

        >>> Edit()
        <Edit selectable flow widget '' edit_pos=0>
        >>> Edit(u"Y/n? ", u"yes")
        <Edit selectable flow widget 'yes' caption='Y/n? ' edit_pos=3>
        >>> Edit(u"Name ", u"Smith", edit_pos=1)
        <Edit selectable flow widget 'Smith' caption='Name ' edit_pos=1>
        >>> Edit(u"", u"3.14", align='right')
        <Edit selectable flow widget '3.14' align='right' edit_pos=4>
        """

        super().__init__("", align, wrap, layout)
        self.multiline = multiline
        self.allow_tab = allow_tab
        self._edit_pos = 0
        self.set_caption(caption)
        self._edit_text = ""
        self.set_edit_text(edit_text)
        if edit_pos is None:
            edit_pos = len(edit_text)
        self.set_edit_pos(edit_pos)
        self.set_mask(mask)
        self._shift_view_to_cursor = False

    def _repr_words(self) -> list[str]:
        return (
            super()._repr_words()[:-1]
            + [repr(self._edit_text)]
            + [f"caption={self._caption!r}"] * bool(self._caption)
            + ["multiline"] * (self.multiline is True)
        )

    def _repr_attrs(self):
        attrs = dict(super()._repr_attrs(), edit_pos=self._edit_pos)
        return remove_defaults(attrs, Edit.__init__)

    def get_text(self):
        """
        Returns ``(text, display attributes)``. See :meth:`Text.get_text`
        for details.

        Text returned includes the caption and edit_text, possibly masked.

        >>> Edit(u"What? ","oh, nothing.").get_text() # ... = u in Python 2
        (...'What? oh, nothing.', [])
        >>> Edit(('bright',u"user@host:~$ "),"ls").get_text()
        (...'user@host:~$ ls', [('bright', 13)])
        >>> Edit(u"password:", u"seekrit", mask=u"*").get_text()
        (...'password:*******', [])
        """

        if self._mask is None:
            return self._caption + self._edit_text, self._attrib

        return self._caption + (self._mask * len(self._edit_text)), self._attrib

    def set_text(self, markup) -> None:
        """
        Not supported by Edit widget.

        >>> Edit().set_text("test")
        Traceback (most recent call last):
        EditError: set_text() not supported.  Use set_caption() or set_edit_text() instead.
        """
        # FIXME: this smells. reimplement Edit as a WidgetWrap subclass to
        # clean this up

        # hack to let Text.__init__() work
        if not hasattr(self, "_text") and markup == "":
            self._text = None
            return

        raise EditError("set_text() not supported.  Use set_caption() or set_edit_text() instead.")

    def get_pref_col(self, size: tuple[int]) -> int:
        """
        Return the preferred column for the cursor, or the
        current cursor x value.  May also return ``'left'`` or ``'right'``
        to indicate the leftmost or rightmost column available.

        This method is used internally and by other widgets when
        moving the cursor up or down between widgets so that the
        column selected is one that the user would expect.

        >>> size = (10,)
        >>> Edit().get_pref_col(size)
        0
        >>> e = Edit(u"", u"word")
        >>> e.get_pref_col(size)
        4
        >>> e.keypress(size, 'left')
        >>> e.get_pref_col(size)
        3
        >>> e.keypress(size, 'end')
        >>> e.get_pref_col(size)
        <Align.RIGHT: 'right'>
        >>> e = Edit(u"", u"2\\nwords")
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

        return pref_col

    def set_caption(self, caption) -> None:
        """
        Set the caption markup for this widget.

        :param caption: markup for caption preceding edit_text, see
                        :meth:`Text.__init__` for description of text markup.

        >>> e = Edit("")
        >>> e.set_caption("cap1")
        >>> print(e.caption)
        cap1
        >>> e.set_caption(('bold', "cap2"))
        >>> print(e.caption)
        cap2
        >>> e.attrib
        [('bold', 4)]
        >>> e.caption = "cap3"  # not supported because caption stores text but set_caption() takes markup
        Traceback (most recent call last):
        AttributeError: can't set attribute
        """
        self._caption, self._attrib = decompose_tagmarkup(caption)
        self._invalidate()

    @property
    def caption(self) -> str:
        """
        Read-only property returning the caption for this widget.
        """
        return self._caption

    def set_edit_pos(self, pos: int) -> None:
        """
        Set the cursor position with a self.edit_text offset.
        Clips pos to [0, len(edit_text)].

        :param pos: cursor position
        :type pos: int

        >>> e = Edit(u"", u"word")
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

    edit_pos = property(
        lambda self: self._edit_pos,
        set_edit_pos,
        doc="""
        Property controlling the edit position for this widget.
        """,
    )

    def set_mask(self, mask: str | bytes | None) -> None:
        """
        Set the character for masking text away.

        :param mask: hide text entered with this character, None:disable mask
        :type mask: bytes or unicode
        """

        self._mask = mask
        self._invalidate()

    def set_edit_text(self, text: str | bytes) -> None:
        """
        Set the edit text for this widget.

        :param text: text for editing, type (bytes or unicode)
                     must match the text in the caption
        :type text: bytes or unicode

        >>> e = Edit()
        >>> e.set_edit_text(u"yes")
        >>> print(e.edit_text)
        yes
        >>> e
        <Edit selectable flow widget 'yes' edit_pos=0>
        >>> e.edit_text = u"no"  # Urwid 0.9.9 or later
        >>> print(e.edit_text)
        no
        """
        text = self._normalize_to_caption(text)
        self.highlight = None
        self._emit("change", text)
        old_text = self._edit_text
        self._edit_text = text
        if self.edit_pos > len(text):
            self.edit_pos = len(text)
        self._emit("postchange", old_text)
        self._invalidate()

    def get_edit_text(self) -> str:
        """
        Return the edit text for this widget.

        >>> e = Edit(u"What? ", u"oh, nothing.")
        >>> print(e.get_edit_text())
        oh, nothing.
        >>> print(e.edit_text)
        oh, nothing.
        """
        return self._edit_text

    edit_text = property(
        get_edit_text,
        set_edit_text,
        doc="""
        Property controlling the edit text for this widget.
        """,
    )

    def insert_text(self, text: str | bytes) -> None:
        """
        Insert text at the cursor position and update cursor.
        This method is used by the keypress() method when inserting
        one or more characters into edit_text.

        :param text: text for inserting, type (bytes or unicode)
                     must match the text in the caption
        :type text: bytes or unicode

        >>> e = Edit(u"", u"42")
        >>> e.insert_text(u".5")
        >>> e
        <Edit selectable flow widget '42.5' edit_pos=4>
        >>> e.set_edit_pos(2)
        >>> e.insert_text(u"a")
        >>> print(e.edit_text)
        42a.5
        """
        text = self._normalize_to_caption(text)
        result_text, result_pos = self.insert_text_result(text)
        self.set_edit_text(result_text)
        self.set_edit_pos(result_pos)
        self.highlight = None

    def _normalize_to_caption(self, text: str | bytes) -> str | bytes:
        """
        Return text converted to the same type as self.caption
        (bytes or unicode)
        """
        tu = isinstance(text, str)
        cu = isinstance(self._caption, str)
        if tu == cu:
            return text
        if tu:
            return text.encode("ascii")  # follow python2's implicit conversion
        return text.decode("ascii")

    def insert_text_result(self, text: str | bytes) -> tuple[str | bytes, int]:
        """
        Return result of insert_text(text) without actually performing the
        insertion.  Handy for pre-validation.

        :param text: text for inserting, type (bytes or unicode)
                     must match the text in the caption
        :type text: bytes or unicode
        """

        # if there's highlighted text, it'll get replaced by the new text
        text = self._normalize_to_caption(text)
        if self.highlight:
            start, stop = self.highlight
            btext, etext = self.edit_text[:start], self.edit_text[stop:]
            result_text = btext + etext
            result_pos = start
        else:
            result_text = self.edit_text
            result_pos = self.edit_pos

        try:
            result_text = result_text[:result_pos] + text + result_text[result_pos:]
        except (IndexError, TypeError) as exc:
            raise ValueError(repr((self.edit_text, result_text, text))).with_traceback(exc.__traceback__) from exc

        result_pos += len(text)
        return (result_text, result_pos)

    def keypress(self, size: tuple[int], key: str) -> str | None:
        """
        Handle editing keystrokes, return others.

        >>> e, size = Edit(), (20,)
        >>> e.keypress(size, 'x')
        >>> e.keypress(size, 'left')
        >>> e.keypress(size, '1')
        >>> print(e.edit_text)
        1x
        >>> e.keypress(size, 'backspace')
        >>> e.keypress(size, 'end')
        >>> e.keypress(size, '2')
        >>> print(e.edit_text)
        x2
        >>> e.keypress(size, 'shift f1')
        'shift f1'
        """
        (maxcol,) = size

        pos = self.edit_pos
        if self.valid_char(key):
            if isinstance(key, str) and not isinstance(self._caption, str):
                # screen is sending us unicode input, must be using utf-8
                # encoding because that's all we support, so convert it
                # to bytes to match our caption's type
                key = key.encode("utf-8")
            self.insert_text(key)
            return None

        if key == "tab" and self.allow_tab:
            key = " " * (8 - (self.edit_pos % 8))
            self.insert_text(key)
            return None

        if key == "enter" and self.multiline:
            key = "\n"
            self.insert_text(key)
            return None

        if self._command_map[key] == Command.LEFT:
            if pos == 0:
                return key
            pos = move_prev_char(self.edit_text, 0, pos)
            self.set_edit_pos(pos)
            return None

        if self._command_map[key] == Command.RIGHT:
            if pos >= len(self.edit_text):
                return key
            pos = move_next_char(self.edit_text, pos, len(self.edit_text))
            self.set_edit_pos(pos)
            return None

        if self._command_map[key] in (Command.UP, Command.DOWN):
            self.highlight = None

            x, y = self.get_cursor_coords((maxcol,))
            pref_col = self.get_pref_col((maxcol,))
            if pref_col is None:
                raise ValueError(pref_col)

            # if pref_col is None:
            #    pref_col = x

            if self._command_map[key] == Command.UP:
                y -= 1
            else:
                y += 1

            if not self.move_cursor_to_coords((maxcol,), pref_col, y):
                return key
            return None

        if key == "backspace":
            self.pref_col_maxcol = None, None
            if not self._delete_highlighted():
                if pos == 0:
                    return key
                pos = move_prev_char(self.edit_text, 0, pos)
                self.set_edit_text(self.edit_text[:pos] + self.edit_text[self.edit_pos :])
                self.set_edit_pos(pos)
                return None
            return None

        if key == "delete":
            self.pref_col_maxcol = None, None
            if not self._delete_highlighted():
                if pos >= len(self.edit_text):
                    return key
                pos = move_next_char(self.edit_text, pos, len(self.edit_text))
                self.set_edit_text(self.edit_text[: self.edit_pos] + self.edit_text[pos:])
                return None
            return None

        if self._command_map[key] in (Command.MAX_LEFT, Command.MAX_RIGHT):
            self.highlight = None
            self.pref_col_maxcol = None, None

            x, y = self.get_cursor_coords((maxcol,))

            if self._command_map[key] == Command.MAX_LEFT:
                self.move_cursor_to_coords((maxcol,), Align.LEFT, y)
            else:
                self.move_cursor_to_coords((maxcol,), Align.RIGHT, y)
            return None

        # key wasn't handled
        return key

    def move_cursor_to_coords(
        self,
        size: tuple[int],
        x: int | Literal[Align.LEFT, Align.RIGHT],
        y: int,
    ) -> bool:
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

        pos = text_layout.calc_pos(self.get_text()[0], trans, x, y)
        e_pos = pos - len(self.caption)
        if e_pos < 0:
            e_pos = 0
        if e_pos > len(self.edit_text):
            e_pos = len(self.edit_text)
        self.edit_pos = e_pos
        self.pref_col_maxcol = x, maxcol
        self._invalidate()
        return True

    def mouse_event(self, size: tuple[int], event, button: int, x: int, y: int, focus: bool) -> bool:
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
        if button == 1:
            return self.move_cursor_to_coords((maxcol,), x, y)
        return False

    def _delete_highlighted(self) -> bool:
        """
        Delete all highlighted text and update cursor position, if any
        text is highlighted.
        """
        if not self.highlight:
            return False
        start, stop = self.highlight
        btext, etext = self.edit_text[:start], self.edit_text[stop:]
        self.set_edit_text(btext + etext)
        self.edit_pos = start
        self.highlight = None
        return True

    def render(self, size: tuple[int], focus: bool = False) -> TextCanvas | CompositeCanvas:
        """
        Render edit widget and return canvas.  Include cursor when in
        focus.

        >>> c = Edit("? ","yes").render((10,), focus=True)
        >>> c.text # ... = b in Python 3
        [...'? yes     ']
        >>> c.cursor
        (5, 0)
        """
        (maxcol,) = size
        self._shift_view_to_cursor = bool(focus)

        canv: TextCanvas | CompositeCanvas = Text.render(self, (maxcol,))
        if focus:
            canv = CompositeCanvas(canv)
            canv.cursor = self.get_cursor_coords((maxcol,))

        # .. will need to FIXME if I want highlight to work again
        # if self.highlight:
        #    hstart, hstop = self.highlight_coords()
        #    d.coords['highlight'] = [ hstart, hstop ]
        return canv

    def get_line_translation(self, maxcol: int, ta=None):
        trans = Text.get_line_translation(self, maxcol, ta)
        if not self._shift_view_to_cursor:
            return trans

        text, ignore = self.get_text()
        x, y = text_layout.calc_coords(text, trans, self.edit_pos + len(self.caption))
        if x < 0:
            return [
                *trans[:y],
                *[text_layout.shift_line(trans[y], -x)],
                *trans[y + 1 :],
            ]

        if x >= maxcol:
            return [
                *trans[:y],
                *[text_layout.shift_line(trans[y], -(x - maxcol + 1))],
                *trans[y + 1 :],
            ]

        return trans

    def get_cursor_coords(self, size: tuple[int]) -> tuple[int, int]:
        """
        Return the (*x*, *y*) coordinates of cursor within widget.

        >>> Edit("? ","yes").get_cursor_coords((10,))
        (5, 0)
        """
        (maxcol,) = size

        self._shift_view_to_cursor = True
        return self.position_coords(maxcol, self.edit_pos)

    def position_coords(self, maxcol: int, pos) -> tuple[int, int]:
        """
        Return (*x*, *y*) coordinates for an offset into self.edit_text.
        """

        p = pos + len(self.caption)
        trans = self.get_line_translation(maxcol)
        x, y = text_layout.calc_coords(self.get_text()[0], trans, p)
        return x, y


class IntEdit(Edit):
    """Edit widget for integer values"""

    def valid_char(self, ch):
        """
        Return true for decimal digits.
        """
        return len(ch) == 1 and ch in "0123456789"

    def __init__(self, caption="", default: int | str | None = None) -> None:
        """
        caption -- caption markup
        default -- default edit value

        >>> IntEdit(u"", 42)
        <IntEdit selectable flow widget '42' edit_pos=2>
        """
        if default is not None:
            val = str(default)
        else:
            val = ""
        super().__init__(caption, val)

    def keypress(self, size: tuple[int], key: str) -> str | None:
        """
        Handle editing keystrokes.  Remove leading zeros.

        >>> e, size = IntEdit(u"", 5002), (10,)
        >>> e.keypress(size, 'home')
        >>> e.keypress(size, 'delete')
        >>> print(e.edit_text)
        002
        >>> e.keypress(size, 'end')
        >>> print(e.edit_text)
        2
        """
        (maxcol,) = size
        unhandled = Edit.keypress(self, (maxcol,), key)

        if not unhandled:
            # trim leading zeros
            while self.edit_pos > 0 and self.edit_text[:1] == "0":
                self.set_edit_pos(self.edit_pos - 1)
                self.set_edit_text(self.edit_text[1:])

        return unhandled

    def value(self) -> int:
        """
        Return the numeric value of self.edit_text.

        >>> e, size = IntEdit(), (10,)
        >>> e.keypress(size, '5')
        >>> e.keypress(size, '1')
        >>> e.value() == 51
        True
        """
        if self.edit_text:
            return int(self.edit_text)

        return 0


def delegate_to_widget_mixin(attribute_name: str):
    """
    Return a mixin class that delegates all standard widget methods
    to an attribute given by attribute_name.

    This mixin is designed to be used as a superclass of another widget.
    """
    # FIXME: this is so common, let's add proper support for it
    # when layout and rendering are separated

    get_delegate = attrgetter(attribute_name)

    class DelegateToWidgetMixin(Widget):
        no_cache: typing.ClassVar[list[str]] = ["rows"]  # crufty metaclass work-around

        def render(self, size, focus: bool = False) -> CompositeCanvas:
            canv = get_delegate(self).render(size, focus=focus)
            return CompositeCanvas(canv)

        @property
        def selectable(self) -> Callable[[], bool]:
            return get_delegate(self).selectable

        @property
        def get_cursor_coords(self):
            return get_delegate(self).get_cursor_coords

        @property
        def get_pref_col(self):
            return get_delegate(self).get_pref_col

        @property
        def keypress(self):
            return get_delegate(self).keypress

        @property
        def move_cursor_to_coords(self):
            return get_delegate(self).move_cursor_to_coords

        @property
        def rows(self):
            return get_delegate(self).rows

        @property
        def mouse_event(
            self,
        ) -> Callable[[tuple[()] | tuple[int] | tuple[int, int], str, int, int, int, bool], bool | None,]:
            return get_delegate(self).mouse_event

        @property
        def sizing(self):
            return get_delegate(self).sizing

        @property
        def pack(self):
            return get_delegate(self).pack

    return DelegateToWidgetMixin


class WidgetWrapError(Exception):
    pass


class WidgetWrap(delegate_to_widget_mixin("_wrapped_widget"), Widget):
    def __init__(self, w: Widget):
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
        self._wrapped_widget = w

    @property
    def _w(self) -> Widget:
        return self._wrapped_widget

    @_w.setter
    def _w(self, new_widget: Widget) -> None:
        """
        Change the wrapped widget.  This is meant to be called
        only by subclasses.

        >>> size = (10,)
        >>> ww = WidgetWrap(Edit("hello? ","hi"))
        >>> ww.render(size).text # ... = b in Python 3
        [...'hello? hi ']
        >>> ww.selectable()
        True
        >>> ww._w = Text("goodbye") # calls _set_w()
        >>> ww.render(size).text
        [...'goodbye   ']
        >>> ww.selectable()
        False
        """
        self._wrapped_widget = new_widget
        self._invalidate()

    def _set_w(self, w):
        """
        Change the wrapped widget.  This is meant to be called
        only by subclasses.

        >>> size = (10,)
        >>> ww = WidgetWrap(Edit("hello? ","hi"))
        >>> ww.render(size).text # ... = b in Python 3
        [...'hello? hi ']
        >>> ww.selectable()
        True
        >>> ww._w = Text("goodbye") # calls _set_w()
        >>> ww.render(size).text
        [...'goodbye   ']
        >>> ww.selectable()
        False
        """
        warnings.warn(
            "_set_w is deprecated. Please use 'WidgetWrap._w' property directly",
            DeprecationWarning,
            stacklevel=2,
        )
        self._wrapped_widget = w
        self._invalidate()


def _test():
    import doctest

    doctest.testmod()


if __name__ == "__main__":
    _test()

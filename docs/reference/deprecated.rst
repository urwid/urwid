Deprecated Classes
------------------

.. currentmodule:: urwid

.. autoclass:: AttrWrap

.. data:: MetaSuper

   Alias of :class:`type`, kept so that class definitions naming it keep importing.
   Drop it from ``metaclass=`` arguments and from base lists; while it is still listed as a base, it has to be the last one.
   The name will be removed in version 7.0.

.. deprecated:: 4.1.7
    :class:`GLibEventLoop`, with no replacement.
    It will be removed in version 6.0.

Deprecated Modules
------------------

.. deprecated:: 5.1.0
    The LCD display module :mod:`urwid.display.lcd`, with :class:`~urwid.display.lcd.CF635Screen`,
    will be removed in version 6.0, with no replacement.

Deprecated Import Paths
-----------------------

.. deprecated:: 2.4.0
    The display modules moved into the :mod:`urwid.display` package.
    The old names will be removed in version 7.0.

    .. list-table::
       :header-rows: 1

       * - Old import
         - New import
       * - ``urwid.display_common``
         - ``urwid.display.common``
       * - ``urwid.raw_display``
         - ``urwid.display.raw``
       * - ``urwid.curses_display``
         - ``urwid.display.curses``
       * - ``urwid.escape``
         - ``urwid.display.escape``

.. deprecated:: 2.6.0
    Names defined in ``urwid.str_util`` and reachable as attributes of ``urwid.util`` (``from urwid.util import ...``)
    have to be imported from ``urwid`` instead.
    The old import path will be removed in version 6.0.

Deprecated Functions, Methods and Names
---------------------------------------

.. deprecated:: 3.0.4
    ``urwid.str_util.get_char_width()`` and ``urwid.str_util.get_width()``.
    Use ``wcwidth.width()`` instead.
    They will be removed in version 6.0.

.. deprecated:: 4.1.4
    ``urwid.str_util.decode_one_uni()`` and ``urwid.str_util.decode_one_right()``, with no replacement.
    They will be removed in version 6.0.

.. deprecated:: 4.1.4
    :meth:`Pile.get_item_size`.
    Use :meth:`Pile.get_rows_sizes` instead.
    It will be removed in version 7.0.

.. deprecated:: 4.1.8
    :func:`display.html_fragment.screenshot_init`, which replaces the curses and raw screens in place.
    Assign a :class:`display.html_fragment.HtmlGenerator` to the application's screen instead.
    It will be removed in version 6.0.

.. deprecated:: 5.0.0
    The ``_MOUSE_*_FLAG`` and ``_MOUSE_BUTTON_MASK`` names of ``urwid.display.escape``.
    Use the members of ``urwid.display.escape.MouseBit`` instead.
    The old names will be removed in version 6.0.

Deprecated Arguments
--------------------

.. deprecated:: 2.2.3
    The camelCase keyword arguments of the numeric edit widgets:
    ``trimLeadingZeros`` of ``urwid.numedit.NumEdit``,
    and ``preserveSignificance`` and ``decimalSeparator`` of :class:`numedit.FloatEdit`.
    Use ``trim_leading_zeros``, ``preserve_significance`` and ``decimal_separator`` instead.
    Support will be removed in version 7.0.

.. deprecated:: 2.4.0
    Passing an object that does not implement the Widget API as a child widget,
    to :class:`WidgetWrap`, a decoration widget, or the contents of a container widget.
    Pass a :class:`Widget` instead.
    Support will be removed in version 7.0.

.. deprecated:: 4.0.2
    Passing a :class:`ListBox` *body* that is not a :class:`ListWalker` but has a ``get_focus`` method.
    Pass a :class:`ListWalker`, or a sequence of widgets, instead.
    Support will be removed in version 7.0.

.. deprecated:: 4.0.4
    Passing a :class:`TreeWidget` a *node* that is not a :class:`ParentNode` but defines ``get_first_child``.
    Make the node a :class:`ParentNode` instead.
    No removal release is decided.

.. deprecated:: 5.0.0
    Passing *reverse* to ``positions()`` of :class:`SimpleListWalker`, :class:`SimpleFocusListWalker`,
    :class:`SimpleDequeWalker` and :class:`SimpleFocusDequeWalker` positionally.
    Pass it by keyword instead.
    Support will be removed in version 8.0.

Deprecated Extension Points
---------------------------

.. deprecated:: 4.0.10
    Overriding ``get_data()`` in a :class:`BarGraph` subclass, or assigning ``get_data`` on an instance.
    Call :meth:`BarGraph.set_data` instead.
    Support will be removed in version 7.0.

.. deprecated:: 5.0
    Defining ``get_input_nonblocking()`` in a subclass of :class:`display.raw.Screen`.
    Override ``get_available_raw_input()`` instead.
    Support will be removed in version 7.0.

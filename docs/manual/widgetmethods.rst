.. _widget-methods:

******************
  Widget Methods  
******************

Widgets in Urwid are easiest to create by extending other widgets. If you are
making a new type of widget that can use other widgets to display its content,
like a new type of button or control, then you should start by extending
:class:`~urwid.widget.WidgetWrap` and passing the display widget to its
constructor.

This section describes the :class:`~urwid.widget.Widget` interface in detail
and is useful if you're looking to modify the behavior of an existing widget,
build a new widget class from scratch or just want a better understanding of
the library.

One design choice that stands out is that widgets in Urwid typically have no
size. Widgets don't store the size they will be displayed at, and instead are
passed that information when they need it.

This choice has some advantages:

* widgets may be reused in different locations
* reused widgets only need to be rendered once per size displayed
* widgets don't need to know their parents
* less data to store and update
* no worrying about widgets that haven't received their size yet
* same widgets could be displayed at different sizes to different users
  simultaneously

It also has disadvantages:

* difficult to determine a widget's size on screen
* more parameters to parse
* duplicated size calculations across methods

For determining a widget's size on screen it is possible to look up the size(s)
it was rendered at in the :class:`~urwid.canvas.CanvasCache`. There are plans
to address some of the duplicated size handling code in the container widgets
in a future Urwid release.

The same holds true for a widget's focus state, so that too is passed in to
functions that need it.

The :class:`~urwid.widget.Widget` base class has some metaclass magic that
creates a :attr:`__super` attribute for calling your superclass:
:attr:`self.__super` is the same as the usual ``super(MyClassName, self)``.

.. seealso::

    class :class:`.Widget`
        Widget base class reference



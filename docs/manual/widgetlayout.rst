.. _widget-layout:

*****************
  Widget Layout
*****************

Urwid uses widgets to divide up the available screen space. This makes it easy
to create a fluid interface that moves and changes with the user's terminal and
font size.

.. image:: images/widget_layout.png

The result of rendering a widget is a canvas suitable for displaying on the
screen. When we render the topmost widget:

1. The topmost widget *(a)* is rendered the full size of the screen
2. *(a)* renders *(b)* any size up to the full size of the screen
3. *(b)* renders *(c)*, *(d)* and *(e)* dividing its available screen columns
   between them
4. *(e)* renders *(f)* and *(g)* dividing its available screen rows between
   them
5. *(e)* combines the canvases from *(f)* and *(g)* and returns them
6. *(b)* combines the canvases from *(c)*, *(d)* and *(e)* and returns them
7. *(a)* possibly modifies the canvas from *(b)* and returns it

Widgets *(a)*, *(b)* and *(e)* are called container widgets because they
contain other widgets. Container widgets choose the size and position their
contained widgets.

Container widgets must also keep track of which one of their contained widgets
is in focus. The focus is used when handling keyboard input. If in the above
example *(b)* 's focus widget is *(e)* and *(e)* 's focus widget is
*(f)* then keyboard input will be handled this way:

1. The keypress is passed to the topmost widget *(a)*
2. *(a)* passes the keypress to *(b)*
3. *(b)* passes the keypress to *(e)*, its focus widget
4. *(e)* passes the keypress to *(f)*, its focus widget
5. *(f)* either handles the keypress or returns it
6. *(e)* has an opportunity to handle the keypress if it was returned from
   *(f)*
7. *(b)* has an opportunity to handle the keypress if it was returned from
   *(e)*
8. *(a)* has an opportunity to handle the keypress if it was returned from
   *(b)*

Box, Flow and Fixed Widgets
===========================

The size of a widget is measured in screen columns and rows. Widgets that are
given an exact number of screen columns and rows are called box widgets. The
topmost widget is always a box widget.

Much of the information displayed in a console user interface is text and the
best way to display text is to have it flow from one screen row to the next.
Widgets like this that require a variable number of screen rows are called flow
widgets. Flow widgets are given a number of screen columns and can calculate
how many screen rows they need.

Occasionally it is also useful to have a widget that knows how many screen
columns and rows it requires, regardless of the space available. This is
called a fixed widget.

It is an Urwid convention to use the variables :attr:`maxcol` and
:attr:`maxrow` to store a widget's size. Box widgets require both of ``(maxcol,
maxrow)`` to be specified.

Flow widgets expect a single-element tuple ``(maxcol,)`` instead because they
calculate their :attr:`maxrow` based on the :attr:`maxcol` value.

Fixed widgets expect the value ``()`` to be passed in to functions that take
a size because they know their :attr:`maxcol` and :attr:`maxrow` values.

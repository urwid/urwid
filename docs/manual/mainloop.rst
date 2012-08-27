.. _main-loop:

*************
  Main Loop
*************

The :class:`~urwid.main_loop.MainLoop` class ties together a :ref:`display
module <display-modules>`, a set of widgets and an :ref:`event loop
<event-loops>`. It handles passing input from the display module to the
widgets, rendering the widgets and passing the rendered canvas to the display
module to be drawn.

You may filter the user's input before it is passed to the widgets with your
own code by using :func:`input_filter() <urwid.main_loop.MainLoop>`, or have
special code to handle input not handled by the widgets by using
:func:`unhandled_input() <urwid.main_loop.MainLoop>`.

You may set alarms to create timed events using
:meth:`~urwid.main_loop.MainLoop.set_alarm_at` or
:meth:`~urwid.main_loop.MainLoop.set_alarm_in`. These methods automatically add
a call to :func:`~urwid.main_loop.MainLoop.draw_screen` after calling your
callback. :meth:`~urwid.main_loop.MainLoop.remove_alarm` may be used to remove
alarms.

When the main loop is running, any code that raises an
:exc:`~urwid.main_loop.ExitMainLoop` exception will cause the loop to
exit cleanly. If any other exception reaches the main loop code, it will shut
down the screen to avoid leaving the terminal in an unusual state then re-raise
the exception for normal handling.

Using :class:`~urwid.main_loop.MainLoop` is highly recommended, but if it does
not fit the needs of your application you may choose to use your own code
instead. There are no dependencies on :class:`~urwid.main_loop.MainLoop` in
other parts of Urwid.

Widgets Displayed
=================

The topmost widget displayed by :class:`~urwid.main_loop.MainLoop` must be
passed as the first parameter to the constructor. If you want to change the
topmost widget while running, you can assign a new widget to the
:class:`~urwid.main_loop.MainLoop` object's
:attr:`~urwid.main_loop.MainLoop.widget` attribute. This is useful for
applications that have a number of different modes or views.

The displayed widgets will be handling user input, so it is better to extend
the widgets that are displayed with your application-specific input handling so
that the application's behaviour changes when the widgets change. If all your
custom input handling is done from :func:`unhandled_input()
<urwid.main_loop.MainLoop>`, it will be difficult to extend as your application
gets more complicated. 

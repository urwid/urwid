.. _main-loop:

*************
  Main Loop
*************

.. currentmodule:: urwid

The :class:`MainLoop` class ties together a :ref:`display
module <display-modules>`, a set of widgets and an :ref:`event loop
<event-loops>`. It handles passing input from the display module to the
widgets, rendering the widgets and passing the rendered canvas to the display
module to be drawn.

You may filter the user's input before it is passed to the widgets with your
own code by using :meth:`MainLoop.input_filter`, or have
special code to handle input not handled by the widgets by using
:func:`MainLoop.unhandled_input`.

You may set alarms to create timed events using
:meth:`MainLoop.set_alarm_at` or
:meth:`MainLoop.set_alarm_in`. These methods automatically add
a call to :func:`MainLoop.draw_screen` after calling your
callback. :meth:`MainLoop.remove_alarm` may be used to remove
alarms.

When the main loop is running, any code that raises an
:exc:`ExitMainLoop` exception will cause the loop to
exit cleanly. If any other exception reaches the main loop code, it will shut
down the screen to avoid leaving the terminal in an unusual state then re-raise
the exception for normal handling.

Using :class:`MainLoop` is highly recommended, but if it does
not fit the needs of your application you may choose to use your own code
instead. There are no dependencies on :class:`MainLoop` in
other parts of Urwid.

Widgets Displayed
=================

The topmost widget displayed by :class:`MainLoop` must be
passed as the first parameter to the constructor. If you want to change the
topmost widget while running, you can assign a new widget to the
:class:`MainLoop` object's
:attr:`MainLoop.widget` attribute. This is useful for
applications that have a number of different modes or views.

The displayed widgets will be handling user input, so it is better to extend
the widgets that are displayed with your application-specific input handling so
that the application's behaviour changes when the widgets change. If all your
custom input handling is done from :meth:`MainLoop.unhandled_input`,
it will be difficult to extend as your application gets more complicated.


.. _event-loops:

Event Loops
===========

Urwid's event loop classes handle waiting for things for the
:class:`MainLoop`. The different event loops allow you to
integrate with Asyncio_, Twisted_, Glib_, Tornado_, ZMQ_ libraries,
or use a simple ``select``-based loop.
Event loop classes abstract the particulars of waiting for input and
calling functions as a result of timeouts.

You will typically only have a single event loop in your application, even if
you have more than one :class:`MainLoop` running.

You can add your own files to watch to your event loop, with the
:meth:`watch_file() <SelectEventLoop.watch_file>` method.
Using this interface gives you the special handling
of :exc:`ExitMainLoop` and other exceptions when using Glib_, Twisted_ or
Tornado_ callbacks.

.. _Asyncio: https://docs.python.org/3/library/asyncio.html
.. _Twisted: http://twistedmatrix.com/trac/
.. _Glib: http://developer.gnome.org/glib/stable/
.. _Tornado: http://www.tornadoweb.org/
.. _ZMQ: https://pyzmq.readthedocs.io/en/latest/

``SelectEventLoop``
-------------------

This event loop is based on ``select.select()``. This is the default event loop
created if none is passed to :class:`~urwid.main_loop.MainLoop`.

::

    # same as urwid.MainLoop(widget, event_loop=urwid.SelectEventLoop())
    loop = urwid.MainLoop(widget)

.. seealso::

  :class:`SelectEventLoop reference <SelectEventLoop>`

``AsyncioEventLoop``
--------------------

This event loop integrates with the asyncio module in Python.

::

    import asyncio
    evl = urwid.AsyncioEventLoop(loop=asyncio.get_event_loop())
    loop = urwid.MainLoop(widget, event_loop=evl)

.. note::

    In case of multithreading or multiprocessing usage required, do not use executor directly!
    Use instead method :meth:`run_in_executor` of :class:`AsyncioEventLoop`,
    which forward API of the same method from asyncio Event Loop run_in_executor_.

.. warning::

    For input handling, selectors based logic is used.
    Under Windows OS only `SelectorEventLoop`_ is supported.

.. note:: `uvloop` event loop is not supported officially.

.. _run_in_executor: https://docs.python.org/3/library/asyncio-eventloop.html#asyncio.loop.run_in_executor
.. _SelectorEventLoop: https://docs.python.org/3/library/asyncio-eventloop.html?highlight=selectoreventloop#asyncio.SelectorEventLoop

.. seealso::

  :class:`AsyncioEventLoop reference <AsyncioEventLoop>`

``TwistedEventLoop``
--------------------

This event loop uses Twisted's reactor. It has been set up to emulate
:class:`SelectEventLoop`'s behaviour and will start the
reactor and stop it on an error. This is not the standard way of using
Twisted's reactor, so you may need to modify this behaviour for your
application.

::

    loop = urwid.MainLoop(widget, event_loop=urwid.TwistedEventLoop())

.. note::

    In case of threading usage required, please use twisted deferToThread_ method. It supports callbacks if needed.
    Executors from `concurrent.futures` are not supported.

.. _deferToThread: https://docs.twisted.org/en/stable/core/howto/threading.html#getting-results

.. seealso::

  :class:`TwistedEventLoop reference <TwistedEventLoop>`

``GLibEventLoop``
-----------------

This event loop uses GLib's event loop. This is useful if you are building an
application that depends on DBus events, but don't want to base your
application on Twisted.

::

    loop = urwid.MainLoop(widget, event_loop=urwid.GLibEventLoop())

.. seealso::

  :class:`GLibEventLoop reference <GLibEventLoop>`

``TornadoEventLoop``
--------------------

This event loop integrates with Tornado.

::

    from tornado.ioloop import IOLoop
    evl = urwid.TornadoEventLoop(IOLoop())
    loop = urwid.MainLoop(widget, event_loop=evl)

.. note::

    In case of multithreading or multiprocessing usage required, do not use executor directly!
    Use instead method :meth:`run_in_executor` of :class:`TornadoEventLoop`,
    which forward API of the same method from `tornado.ioloop.IOLoop` (and internally use asyncio run_in_executor_).

.. seealso::

  :class:`TornadoEventLoop reference <TornadoEventLoop>`

``ZMQEventLoop``
----------------

This event loop integrates with 0MQ.

::

    evl = urwid.ZMQEventLoop()
    loop = urwid.MainLoop(widget, event_loop=evl)

.. seealso::

  :class:`ZMQEventLoop reference <ZMQEventLoop>`
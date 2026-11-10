.. _testing:

*********************
  Testing Widgets
*********************

.. currentmodule:: urwid.testing

A widget renders to a canvas and handles keys and mouse events through plain method calls, so a test needs no
terminal. The :mod:`urwid.testing` module collects the helpers such tests keep rewriting. It is not imported by
:mod:`urwid`, so the examples below start with::

    from urwid.testing import (
        ScriptedScreen,
        VirtualClockEventLoop,
        attrs_for_text,
        check_sizing,
        press,
        render_runs,
        render_text,
    )

Every check raises :exc:`AssertionError` with a message that names the call and the mismatch, and the module
imports no test framework, so the helpers work with :mod:`unittest`, pytest or any other runner.

Rendering
=========

:func:`render_text` renders a widget and returns its rows as text, and :func:`render_runs` returns each row as
``(attr, text)`` runs::

    >>> from urwid import Text
    >>> render_text(Text("ab cd"), (3,))
    ['ab ', 'cd ']
    >>> render_runs(Text([("bold", "Hi"), "!"]), (3,))
    [[('bold', 'Hi'), (None, '!')]]

:func:`attrs_for_text` returns the attributes of the runs that contain a text, to check how one label is drawn
without spelling out the whole row::

    >>> attrs_for_text(Text([("bold", "Hi"), "!"]), (3,), "Hi")
    frozenset({'bold'})

:func:`resolve_attr` and :func:`resolve_runs` show the colors a screen with a given palette draws those attributes
with.

Sizing checks
=============

:func:`check_sizing` renders a widget at the degenerate and full sizes of each of its sizing modes, with focus off
and on, and checks that the canvas has the size the widget promised and a cursor inside it::

    >>> from urwid import Pile
    >>> check_sizing(Pile([Text("x")]))

The checks empty the canvas cache before every case, so they belong in tests, not in a running application.

Input
=====

:func:`press` sends keys and returns the ones the widget did not handle; :func:`click` sends one mouse event with
named arguments::

    >>> from urwid import Edit
    >>> press(Edit("> "), (10,), "a", "b", "esc")
    ['esc']

Whole applications
==================

:class:`ScriptedScreen` stands in for the terminal of a :class:`~urwid.MainLoop`. It returns a fixed screen size,
feeds scripted batches of input, stops the loop once they are used up, and records every distinct frame drawn::

    >>> from urwid import Filler, MainLoop
    >>> screen = ScriptedScreen(size=(6, 1), inputs=[["a", "b"], ["backspace"]])
    >>> MainLoop(Filler(Edit("> ")), screen=screen).run()
    >>> screen.last_text
    ['> a   ']

Alarms
======

:class:`VirtualClockEventLoop` runs the alarms of a :class:`~urwid.MainLoop` on a clock of its own.
:meth:`~VirtualClockEventLoop.advance` moves that clock ahead and fires every alarm that comes due on the way,
so a widget that expires, blinks or polls is tested without waiting for it::

    >>> from urwid import Notifications, SolidFill
    >>> event_loop = VirtualClockEventLoop()
    >>> loop = MainLoop(SolidFill(), screen=ScriptedScreen(), event_loop=event_loop)
    >>> notifications = Notifications(loop=loop, timeout=5)
    >>> _ = notifications.notify("saved")
    >>> event_loop.advance(5)
    >>> notifications.notifications
    ()

When a test needs the state after everything an application has scheduled, rather than at a chosen time,
:meth:`~VirtualClockEventLoop.run_until_idle` fires the alarms until none is pending and returns with the clock at the
last one.
Its ``pause`` argument watches the files for that many seconds of real time before each jump of the clock,
so a worker thread polled by an alarm can hand back its result through :meth:`~urwid.MainLoop.call_from_thread`.

The clock is the loop's own: a widget that reads :func:`time.monotonic` itself, such as :class:`~urwid.Spinner`
choosing its frame, does not see it move.

To keep the frames as HTML for documentation instead, use :class:`urwid.display.html_fragment.HtmlGenerator`.

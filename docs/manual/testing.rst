.. _testing:

*********************
  Testing Widgets
*********************

.. currentmodule:: urwid.testing

A widget renders to a canvas and handles keys and mouse events through plain method calls, so a test needs no
terminal. The :mod:`urwid.testing` module collects the helpers such tests keep rewriting. It is not imported by
:mod:`urwid`, so the examples below start with::

    from urwid.testing import ScriptedScreen, check_sizing, press, render_runs, render_text

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

To keep the frames as HTML for documentation instead, use :class:`urwid.display.html_fragment.HtmlGenerator`.

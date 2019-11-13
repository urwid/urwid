Library Overview
================

.. currentmodule:: urwid

Urwid is a console user interface library for `Python`_. Urwid offers an
alternative to using Python's curses module directly and handles many of the
difficult and tedious tasks for you.

.. _Python: http://www.python.org/

.. image:: images/introduction.png

Each Urwid component is loosely coupled and designed to be extended by the
user.

:ref:`Display modules <display-modules>` are responsible for accepting
:ref:`user input <user-input>` and converting escape sequences to lists of
keystrokes and mouse events. They also draw the screen contents and convert
attributes used in the canvases rendered to the actual colors that appear on
screen.

The included widgets are simple building blocks and examples that try not to
impose a particular style of interface.
It may be helpful to think of Urwid as a console widget construction set rather
than a finished UI library like GTK or Qt. The :class:`Widget base class
<Widget>` describes the widget interface and :ref:`widget layout
<widget-layout>` describes how widgets are nested and arranged on the screen.

Text is the bulk of what will be displayed in any console user interface.
Urwid supports a number of :ref:`text encodings <text-encodings>` and Urwid
comes with a configurable :ref:`text layout <text-layout>` that handles the
most of the common alignment and wrapping modes. If you need more flexibility
you can also write your own text layout classes.

Urwid supports a range of common :ref:`display attributes <display-attributes>`,
including 24-bit and 256-color foreground and background settings, bold,
underline and standout settings for displaying text. Not all of these are
supported by all terminals, so Urwid helps you write applications that support
different color modes depending on what the user's terminal supports and what
they choose to enable.

:class:`ListBox` is one of Urwid's most powerful widgets,
and you may control of the :ref:`listbox contents <listbox-contents>` by using
a built-in list walker class or by writing one yourself. This is very useful
for scrolling through lists of any significant length, or with nesting, folding
and other similar features.

When a widget renders a canvas to be drawn on screen, a weak reference to it is
stored in the :ref:`canvas cache <canvas-cache>`. This cache is used any time a
widget needs to be rendered again, reducing the amount of work required to
update the screen. Since only weak references are used, Urwid's display modules
will hold on to a reference to the canvas that they are currently displaying as
a way to keep the cache alive and populated with current data.

Urwid's :ref:`main loop <main-loop>` simplifies handling of input and updating
the screen.  It also lets you use one of a number of :ref:`the event loops
<event-loops>`, allowing integration with Twisted_'s reactor or Glib_'s event
loop if desired.

.. _Glib: http://developer.gnome.org/glib/stable/glib-The-Main-Event-Loop.html
.. _Twisted: http://twistedmatrix.com/documents/current/core/howto/reactor-basics.html

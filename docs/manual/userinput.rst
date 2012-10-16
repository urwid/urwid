.. vim: set fileencoding=utf-8:

.. _user-input:

**************
  User Input
**************

.. currentmodule:: urwid

All input from the user is parsed by a display module, and returned from either
the :meth:`get_input() <raw_display.Screen.get_input>` or
:meth:`get_input_nonblocking() <raw_display.Screen.get_input_nonblocking>` methods as a list.
Window resize events are also included in the user input.

The :class:`MainLoop` class will take this input and pass each
item to the widget methods :meth:`keypress() <Widget.keypress>` or
:meth:`mouse_event() <Widget.mouse_event>`. You may
filter input (possibly removing or altering it) before it is passed to the
widgets, or can catch unhandled input by passing functions into the
:class:`MainLoop` constructor. If the window was resized
:class:`MainLoop` will query the new display size and update
the screen.

There may be more than one keystroke or mouse event processed at a time, and
each is sent as a separate item in the list.

.. _keyboard-input:

Keyboard Input
==============

Not all keystrokes are sent by a user's terminal to the program, and which keys
are sent varies from terminal to terminal, but Urwid will report any keys that
are sent.

============= =================
Key pressed   Input returned
============= =================
H             ``'h'``
SHIFT+H       ``'H'``
SPACE         ``' '``
ENTER         ``'enter'``
UP            ``'up'``
PAGE DOWN     ``'page down'``
F5            ``'f5'``
SHIFT+F5      ``'shift f5'``
CTRL+SHIFT+F5 ``'shift ctrl f5'``
ALT+J         ``'meta j'``
============= =================

With Unicode :ref:`text encoding <text-encodings>` you will also receive
Unicode strings for any non-ASCII characters:

=========== ==============
Key pressed Input returned
=========== ==============
é           ``u'é'``
Ж           ``u'Ж'``
カ          ``u'カ'``
=========== ==============

With non-Unicode :ref:`text encoding <text-encodings>` characters will be sent
as-is in the original encoding.

=========== =========================================
Key pressed Input returned (each in its own encoding)
=========== =========================================
é           ``'é'``
Ж           ``'Ж'``
カ          ``'カ'`` (two bytes)
=========== =========================================

Urwid does not try to convert this text to Unicode to avoid losing any
information. If you want the input converted to Unicode in all cases you may
create an input filter to do so.


.. _mouse-input:

Mouse Input
===========

Mouse input is sent as a (*event*, *button*, *x*, *y*) tuple. *event* is a string
describing the event. If the *SHIFT*, *ALT* or *CTRL* keys are held when a mouse
event is sent then *event* may be prefixed by ``'shift '``, ``'meta '`` or
``'ctrl'``. *button* is a number from 1 to 5. *x* and *y* are character
coordinates starting from ``(0, 0)`` at the top-left of the screen.

Support for the right-mouse button and use of modifier keys is poor in many
terminals and some users don't have a middle mouse button, so these shouldn't
be relied on.

``'mouse press'`` Events
------------------------

A mouse button was pressed.

=============== ======================
`button` number Mouse button
=============== ======================
1               Left button
2               Middle button
3               Right button
4               Scroll wheel up [#first]_
5               Scroll wheel down [#first]_
=============== ======================

.. [#first] typically no corresponding release event is sent

``'mouse release'`` Events
--------------------------

Mouse release events will often not have information about which button was
released. In this case *button* will be set to 0.

``'mouse drag'`` Events
-----------------------

In the rare event that your user is using a terminal that can send these events
you can use them to track their mouse dragging from one character cell to the
next across the screen. Be aware that you might see *x* and/or *y* coordinates
one position off the screen if the user drags their mouse to the edge.

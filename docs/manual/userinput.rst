.. vim: set fileencoding=utf-8:

.. _user-input:

**************
  User Input
**************

.. currentmodule:: urwid

All input from the user is parsed by a display module, and returned as a list,
either from the :meth:`get_input() <display.raw.Screen.get_input>` method or to the callback registered with
:meth:`hook_event_loop() <display.raw.Screen.hook_event_loop>`, which :class:`MainLoop` uses.
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

A control sequence that Urwid does not recognise is returned as a single key
holding the characters after ``ESC [``, so that its characters are not received
as typed text: ``ESC [ 1;2X`` returns ``'<csi 1;2X>'``.

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


.. _extended-keys:

Extended Keys
-------------

In the legacy encodings several keys send the same bytes: CTRL+I is TAB,
CTRL+M and CTRL+ENTER are ENTER, CTRL+[ is ESC. Terminals that implement the
`kitty keyboard protocol <https://sw.kovidgoyal.net/kitty/keyboard-protocol/>`_
or xterm's *modifyOtherKeys* can report these keys apart. The raw display turns
this on when it is created with ``extended_keys=True``::

    screen = urwid.display.raw.Screen(extended_keys=True)

The screen then asks the terminal for both protocols and turns on the one the
terminal answers for, preferring the kitty keyboard protocol. It does not wait
for the answer: keys typed before it arrives are reported as before. The state
the terminal had is restored when the screen stops. Which protocols the terminal
supports is kept in ``screen.modes.kitty_keyboard`` and
``screen.modes.modify_other_keys``.

=============== ====================== ===================
Key pressed     Legacy input           Extended input
=============== ====================== ===================
CTRL+I          ``'tab'``              ``'ctrl i'``
CTRL+M          ``'enter'``            ``'ctrl m'``
CTRL+ENTER      ``'enter'``            ``'ctrl enter'``
SHIFT+ENTER     ``'enter'``            ``'shift enter'``
CTRL+SHIFT+TAB  ``'shift tab'``        ``'shift ctrl tab'``
CTRL+/          ``'ctrl _'``           ``'ctrl /'``
CTRL+SHIFT+A    ``'ctrl a'``           ``'ctrl A'``
ALT+SHIFT+A     ``'meta A'``           ``'meta A'``
=============== ====================== ===================

A shifted letter or symbol is named by the character it types, as the legacy
encodings name it. The kitty keyboard protocol also reports the *super* and
*hyper* modifiers, as the ``'super '`` and ``'hyper '`` prefixes, and its ESC key
arrives without the short wait an escape sequence needs.

.. note::

   With either protocol on, the terminal sends CTRL+C, CTRL+Z and CTRL+\\ as
   ``'ctrl c'``, ``'ctrl z'`` and ``'ctrl \'`` keys, so they no longer raise
   ``SIGINT``, suspend the program or raise ``SIGQUIT``. An application that
   turns on extended keys handles these keys itself.

A :class:`Terminal` widget implements the kitty keyboard protocol for its child.
The child can query, push, pop and set the protocol's flags, and the main and
the alternate screen each keep their own stack of them. While the child has
*disambiguate escape codes* or *report all keys as escape codes* set, the
Terminal sends keys as the protocol reports them, so ``'ctrl enter'`` and
``'super a'`` reach the child as they were pressed. With *report alternate keys*
an upper case letter carries its shifted key, and with *report associated text*
a key that types text carries that text. urwid reports key presses only, so the
child gets no repeat or release events even with *report event types* set. The
keypad keys are sent as the main keys, which urwid names them as, and pasted
text is sent as text.

Without these flags, the Terminal passes ENTER, TAB, BACKSPACE and ESC with
modifiers, and CTRL with SPACE, /, ? or ~, to its child as a legacy terminal
sends them under the ``linux`` terminal type, so ``'ctrl enter'`` arrives as
ENTER. It returns the other new keys, such as ``'super a'``.


.. _flow-control-keys:

Flow Control Keys
-----------------

By default the tty treats CTRL+S and CTRL+Q as XOFF and XON: CTRL+S stops the
terminal output until CTRL+Q resumes it, and the application never receives
either key. To receive them as ``'ctrl s'`` and ``'ctrl q'``, unmap them from
flow control with the screen's ``tty_signal_keys()`` method before the
main loop starts, and put the old settings back once it ends::

    screen = urwid.display.raw.Screen()
    loop = urwid.MainLoop(widget, screen=screen)
    old_keys = screen.tty_signal_keys(start="undefined", stop="undefined")
    try:
        loop.run()
    finally:
        if old_keys:
            screen.tty_signal_keys(*old_keys)

The screen does not undo the change when it stops, which is what the
``finally`` block is for. A shell such as bash puts its own tty settings back
when CTRL+Z suspends the program, so after a resume CTRL+S and CTRL+Q are flow
control again.
``tty_signal_keys()`` returns ``None`` when the input is not a tty. Passing
``intr``, ``quit`` and ``susp`` as ``"undefined"`` too stops CTRL+C, CTRL+\\
and CTRL+Z from raising signals, as ``examples/input_test.py`` does.


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

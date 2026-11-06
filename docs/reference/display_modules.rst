Display Modules
===============

.. currentmodule:: urwid

.. autoclass:: BaseScreen

.. autoclass:: urwid.display.PaletteEntrySpecs

RAW display
-----------

.. module:: urwid.display.raw

.. autoclass:: Screen

Curses display
--------------

.. module:: urwid.display.curses

.. autoclass:: Screen

WEB display
-----------

.. module:: urwid.display.web

.. autoclass:: Screen

WebSocket display
-----------------

.. module:: urwid.display.websocket

.. autoclass:: Screen
    :members: feed, close, closed

.. autoclass:: Transport
    :members:

.. autoexception:: InvalidMessageError

.. autofunction:: html_page

.. autodata:: STATIC_FILES
    :no-value:

.. autoclass:: StaticFile
    :members:

.. autodata:: MAX_MESSAGE_LENGTH

.. autodata:: MAX_PENDING_INPUT

HTML fragment
-------------

.. module:: urwid.display.html_fragment

.. autoclass:: HtmlGenerator

.. autofunction:: screenshot_init

.. autofunction:: screenshot_collect

LCD display
-----------

.. module:: urwid.display.lcd

.. autoclass:: LCDScreen

.. autoclass:: CFLCDScreen

.. autoclass:: CF635Screen

.. autoclass:: KeyRepeatSimulator

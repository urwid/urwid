Constants
=========

.. note::

   These constants may be used, but using the string values themselves in
   your program is equally supported.  These constants are used internally
   by urwid just to avoid possible misspelling, but the example programs
   and tutorials tend to use the string values.

Widget Sizing Methods
---------------------

One or more of these values returned by :meth:`Widget.sizing` to indicate
supported sizing methods.

.. data:: urwid.FLOW
   :annotation: = 'flow'

   Widget that is given a number of columns by its parent widget and
   calculates the number of rows it requires for rendering
   e.g. :class:`Text`

.. data:: urwid.BOX
   :annotation: = 'box'

   Widget that is given a number of columns and rows by its parent
   widget and must render that size
   e.g. :class:`ListBox`

.. data:: urwid.FIXED
   :annotation: = 'fixed'

   Widget that knows the number of columns and rows it requires and will
   only render at that exact size
   e.g. :class:`BigText`


Horizontal Alignment
--------------------

Used to horizontally align text in :class:`Text` widgets and child widgets
of :class:`Padding` and :class:`Overlay`.

.. data:: urwid.LEFT
   :annotation: = 'left'

.. data:: urwid.CENTER
   :annotation: = 'center'

.. data:: urwid.RIGHT
   :annotation: = 'right'

Veritcal Alignment
------------------

Used to vertically align child widgets of :class:`Filler` and
:class:`Overlay`.

.. data:: urwid.TOP
   :annotation: = 'top'

.. data:: urwid.MIDDLE
   :annotation: = 'middle'

.. data:: urwid.BOTTOM
   :annotation: = 'bottom'

Width and Height Settings
-------------------------

Used to distribute or set widths and heights of child widgets of
:class:`Padding`, :class:`Filler`, :class:`Columns`,
:class:`Pile` and :class:`Overlay`.

.. data:: urwid.PACK
   :annotation: = 'pack'

   Ask the child widget to calculate the number of columns or rows it needs

.. data:: urwid.GIVEN
   :annotation: = 'given'

   A set number of columns or rows, e.g. ('given', 10) will have exactly
   10 columns or rows given to the child widget

.. data:: urwid.RELATIVE
   :annotation: = 'relative'

   A percentage of the total space, e.g. ('relative', 50) will give half
   of the total columns or rows to the child widget

.. data:: urwid.RELATIVE_100
   :annotation: = ('relative', 100)

.. data:: urwid.WEIGHT
   :annotation: = 'weight'

   A weight value for distributing columns or rows, e.g. ('weight', 3)
   will give 3 times as many columns or rows as another widget in the same
   container with ('weight', 1).


Text Wrapping Modes
-------------------

.. data:: urwid.SPACE
   :annotation: = 'space'

   wrap text on space characters or at the boundaries of wide characters

.. data:: urwid.ANY
   :annotation: = 'any'

   wrap before any wide or narrow character that would exceed the available
   screen columns

.. data:: urwid.CLIP
   :annotation: = 'clip'

   clip before any wide or narrow character that would exceed the available
   screen columns ad don't display the remaining text on the line


Foreground and Background Colors
--------------------------------

Standard background and foreground colors
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. data:: urwid.BLACK
   :annotation: = 'black'

.. data:: urwid.DARK_RED
   :annotation: = 'dark red'

.. data:: urwid.DARK_GREEN
   :annotation: = 'dark green'

.. data:: urwid.BROWN
   :annotation: = 'brown'

.. data:: urwid.DARK_BLUE
   :annotation: = 'dark blue'

.. data:: urwid.DARK_MAGENTA
   :annotation: = 'dark magenta'

.. data:: urwid.DARK_CYAN
   :annotation: = 'dark cyan'

.. data:: urwid.LIGHT_GRAY
   :annotation: = 'light gray'

Standard foreground colors (not safe to use as background)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. data:: urwid.DARK_GRAY
   :annotation: = 'dark gray'

.. data:: urwid.LIGHT_RED
   :annotation: = 'light red'

.. data:: urwid.LIGHT_GREEN
   :annotation: = 'light green'

.. data:: urwid.YELLOW
   :annotation: = 'yellow'

.. data:: urwid.LIGHT_BLUE
   :annotation: = 'light blue'

.. data:: urwid.LIGHT_MAGENTA
   :annotation: = 'light magenta'

.. data:: urwid.LIGHT_CYAN
   :annotation: = 'light cyan'

.. data:: urwid.WHITE
   :annotation: = 'white'

User's terminal configuration default foreground or background
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. note::

   There is no way to tell if the user's terminal has a light
   or dark color as their default foreground or background, so
   it is highly recommended to use this setting for both foreground
   and background when you do use it.

.. data:: urwid.DEFAULT
   :annotation: = 'default'


256 and 88 Color Foregrounds and Backgrounds
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Constants are not defined for these colors.

.. seealso::

   :ref:`high-colors`
 


Signal Names
------------

.. data:: urwid.UPDATE_PALETTE_ENTRY
   :annotation: = 'update palette entry'

   sent by :class:`BaseScreen` (and subclasses like 
   :class:`raw_display.Screen`) when a palette entry is changed.
   :class:`MainLoop` handles this signal by redrawing the whole
   screen.

.. data:: urwid.INPUT_DESCRIPTORS_CHANGED
   :annotation: = 'input descriptors changed'

   sent by :class:`BaseScreen` (and subclasses like 
   :class:`raw_display.Screen`) when the list of input file descriptors
   has changed.  :class:`urwid.MainLoop` handles this signal by updating
   the file descriptors being watched by its event loop.


Command Names
-------------

Command names are used as values in :class:`CommandMap` instances.
Widgets look up the command associated with keypresses in their
:meth:`Widget.keypress` methods.

You may define any new command names as you wish and look for them in
your own widget code.  These are the standard ones expected by code
included in Urwid.

.. data:: urwid.REDRAW_SCREEN
   :annotation: = 'redraw screen'

   Default associated keypress: 'ctrl l'

   :meth:`MainLoop.process_input` looks for this command to force
   a screen refresh. This is useful in case the screen becomes
   corrupted.

.. data:: urwid.CURSOR_UP
   :annotation: = 'cursor up'

   Default associated keypress: 'up'

   Move the cursor or selection up one row.

.. data:: urwid.CURSOR_DOWN
   :annotation: = 'cursor down'

   Default associated keypress: 'down'

   Move the cursor or selection down one row.

.. data:: urwid.CURSOR_LEFT
   :annotation: = 'cursor left'

   Default associated keypress: 'left'

   Move the cursor or selection left one column.

.. data:: urwid.CURSOR_RIGHT
   :annotation: = 'cursor right'

   Default associated keypress: 'right'

   Move the cursor or selection right one column.

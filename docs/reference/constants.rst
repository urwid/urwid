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

   ask the child widget to calculate the number of columns or rows it needs

.. data:: urwid.GIVEN
   :annotation: = 'given'

   a set number of columns or rows, e.g. ('given', 10) will have exactly
   10 columns or rows given to the child widget

.. data:: urwid.RELATIVE
   :annotation: = 'relative'

   a percentage of the total space, e.g. ('relative', 50) will give half
   of the total columns or rows to the child widget

.. data:: urwid.RELATIVE_100
   :annotation: = ('relative', 100)

.. data:: urwid.WEIGHT
   :annotation: = 'weight'

   a weight value for distributing columns or rows, e.g. ('weight', 3)
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


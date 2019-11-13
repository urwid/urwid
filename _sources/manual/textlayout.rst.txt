.. _text-layout:

***************
  Text Layout
***************

.. currentmodule:: urwid

Mapping a text string to screen coordinates within a widget is called text
layout. The :class:`Text` widget's default layout class supports
aligning text to the left, center or right, and can wrap text on space
characters, at any location, or clip text that is off the edge, optionally
inserting an ellipsis character.

::

    Text("Showing some different alignment modes", align=...)

    align='left' (default)
    +----------------+   +------------------------+
    |Showing some    |   |Showing some different  |
    |different       |   |alignment modes         |
    |alignment modes |   +------------------------+
    +----------------+

    align='center'
    +----------------+   +------------------------+
    |  Showing some  |   | Showing some different |
    |   different    |   |    alignment modes     |
    |alignment modes |   +------------------------+
    +----------------+

    align='right'
    +----------------+   +------------------------+
    |    Showing some|   |  Showing some different|
    |       different|   |         alignment modes|
    | alignment modes|   +------------------------+
    +----------------+

::

    Text("Showing some different wrapping modes\nnewline", wrap=...)

    wrap='space' (default)
    +----------------+   +------------------------+
    |Showing some    |   |Showing some different  |
    |different       |   |wrapping modes          |
    |wrapping modes  |   |newline                 |
    |newline         |   +------------------------+
    +----------------+

    wrap='any'
    +----------------+   +------------------------+
    |Showing some dif|   |Showing some different w|
    |ferent wrapping |   |rapping modes           |
    |modes           |   |newline                 |
    |newline         |   +------------------------+
    +----------------+

    wrap='clip'
    +----------------+   +------------------------+
    |Showing some dif|   |Showing some different w|
    |newline         |   |newline                 |
    +----------------+   +------------------------+

    wrap='ellipsis'
    +----------------+   +------------------------+
    |Showing some di…|   |Showing some different …|
    |newline         |   |newline                 |
    +----------------+   +------------------------+

If this is good enough for your application feel free to skip the rest of this
section.

.. seealso::
   :class:`Text widget reference <Text>`


Custom Text Layouts
===================

The :class:`StandardTextLayout` is set as the class variable
:attr:`Text.layout`. Individual :class:`Text`
widgets may use a different layout class, or you can change the default by
setting the :attr:`Text.layout` class variable itself.

A custom text layout class should extend the
:class:`TextLayout` base class and return text layout
structures from its ``layout()`` method.

.. seealso::
   :class:`TextLayout reference <TextLayout>`


Text Layout Structures
======================

::

    "This is how a string of text might be displayed"
    0----5---10---15---20---25---30---35---40---45--

    0----5---10---15---+   right_aligned_text_layout = [
    |     This is how a|     [(5, 0), (13, 0, 13)],
    |    string of text|     [(4, 13), (14, 14, 28)],
    |might be displayed|     [(18, 29, 47)]
    +------------------+   ]

The mapping from a text string to where that text will be displayed in the
widget is expressed as a text layout structure.

Text layout structures are used both for rendering :class:`Text`
widgets and for mapping ``(x, y)`` positions within a widget back to the
corresponding offsets in the text. The latter is used when moving the cursor in
:class:`Edit` widgets up and down or by clicking with the mouse.

A text layout structure is a list of one or more line layouts. Each line layout
corresponds to a row of text in the widget, starting from its top.

A line layout is a list zero or more of the following tuples, each expressing
text to be displayed from left to right:

A. (*column width*, *starting text offset*, *ending text offset*)
B. (*column width of space characters to insert*, *text offset* or ``None``)
C. (*column width*, *text offset*, *new text to insert*)``

Tuple A displays a segment of text from the :class:`Text` widget.
Column width is explicitly specified because some characters within the text
may be zero width or double width.

Tuple B inserts any number of space characters, and if those characters
correspond to an offset within the text, that may be specified.

Tuple C allows insertion of arbitrary text. This could be used for hyphenating
split words or any other effect not covered by A or B. The
:class:`StandardTextLayout` does not currently use this
tuple in its line layouts.

.. seealso::
   :class:`TextLayout reference <TextLayout>`,
   :class:`StandardTextLayout reference <StandardTextLayout>`


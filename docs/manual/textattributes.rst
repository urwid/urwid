.. _text-attributes:

*******************
  Text Attributes  
*******************

A :class:`Text` widget can take plain or unicode strings, but you can also
specify which attributes to display each part of that text by using "text
markup" format. Text markup made up of lists and tuples. Tuples contain an
attribute and text markup to apply it to. Lists used to concatenate text
markup.

The normal text formatting rules apply and the attributes will follow the text
when it is split or wrapped to the next line.

`Text reference <http://excess.org/urwid/reference.html#Text>`_

::

    Text("a simple string with default attributes")

The string and space around will appear in the default foreground and
background.

::

    Text(('attr1', "a string in attribute attr1"))

The string will appear with foreground and backgrounds specified in the display
module's palette for ``'attr1'``, but the space around (before/after) the text
will appear with the default foreground and background.

If you want the whole :class:`Text` widget, including the space around the
text, to appear as a single attribute you should put your widget inside an
:class:`AttrMap` widget.

`AttrMap reference <http://excess.org/urwid/reference.html#AttrMap>`_

::

    Text(["a simple string ", ('attr1', "ending in attr1")])

The first three words have the default attribute and the last three words have
attribute ``'attr1'``.

::

    Text([('attr1', "start in attr1 "), ('attr2', "end in attr2")])

The first three words have attribute ``'attr1'`` and the last three words have
attribute ``'attr2'``.

::

    Text(('attr1', ["nesting example ", ('attr2', "inside"), " outside"]))

When markup is nested only the innermost attribute applies. Here ``"inside"``
has attribute ``'attr2'`` and all the rest of the text has attribute
``'attr1'``.

.. _listbox-contents:

************************
  ``ListBox`` Contents  
************************

The :class:`~urwid.listbox.ListBox` is a box widget that contains flow widgets.
Its contents are displayed stacked vertically, and the
:class:`~urwid.listbox.ListBox` allows the user to scroll through its content.
One of the flow widgets displayed in the :class:`~urwid.listbox.ListBox` is its
focus widget.

List Walkers
============

The :class:`~urwid.listbox.ListBox` does not manage the widgets it displays
directly, instead it passes that task to a class called a "list walker". List
walkers keep track of the widget in focus and provide an opaque position object
that the :class:`~urwid.listbox.ListBox` may use to iterate through widgets
above and below the focus widget.

A `SimpleListWalker <http://excess.org/urwid/reference.html#SimpleListWalker>`_
is a list walker that behaves like a normal Python list. It may be used any
time you will be displaying a moderate number of widgets.

If you need to display a large number of widgets you should implement your own
list walker that manages creating widgets as they are requested and destroying
them later to avoid excessive memory use.

List walkers may also be used to display tree or other structures within a
:class:`~urwid.listbox.ListBox`. A number of the `example programs
<http://excess.org/urwid/examples.html#>`_ demonstrate the use of custom list
walker classes.

`List walker interface definition
<http://excess.org/urwid/reference.html#List_Walker_interface_definition>`_

Focus & Scrolling Behavior
==========================

The :class:`~urwid.listbox.ListBox` passes all key presses it receives first to
its focus widget. If its focus widget does not handle a keypress then the
:class:`~urwid.listbox.ListBox` may handle the keypress by scrolling and/or
selecting another widget to become its new focus widget.

The :class:`~urwid.listbox.ListBox` tries to do *the most sensible thing* when
scrolling and changing focus. When the widgets displayed are all
:class:`~urwid.widget.Text` widgets or other unselectable widgets then the
:class:`~urwid.listbox.ListBox` will behave like a web browser does when the
user presses *UP*, *DOWN*, *PAGE UP* and *PAGE DOWN*: new text is immediately
scrolled in from the top or bottom. The :class:`~urwid.listbox.ListBox` chooses
one of the visible widgets as its focus widget when scrolling. When scrolling
up the :class:`~urwid.listbox.ListBox` chooses the topmost widget as the focus,
and when scrolling down the :class:`~urwid.listbox.ListBox` chooses the
bottommost widget as the focus.

The :class:`~urwid.listbox.ListBox` remembers the visible location of its focus
widget as either an "offset" or an "inset". An offset is the number of rows
between the top of the :class:`~urwid.listbox.ListBox` and the beginning of the
focus widget. An offset of zero corresponds to a widget with its top aligned
with the top of the :class:`~urwid.listbox.ListBox`. An inset is the fraction
of rows of the focus widget that are "above" the top of the
:class:`~urwid.listbox.ListBox` and not visible. The
:class:`~urwid.listbox.ListBox` uses this method of remembering the focus
widget location so that when the :class:`~urwid.listbox.ListBox` is resized the
the text will remain roughly in the same position of the visible area.

When there are selectable widgets visible in the
:class:`~urwid.listbox.ListBox` the focus will move between the selectable
widgets, skipping the unselectable widgets.  The
:class:`~urwid.listbox.ListBox` will try to scroll all the rows of a selectable
widget into view so that the user can see the new focus widget in its entirety.
This behavior can be used to bring more than a single widget into view by using
a :class:`~urwid.container.Pile` or other container widget to combine a
selectable widget with other widgets that should be visible at the same time.

`Tutorial chapters covering ListBox usage <http://excess.org/urwid/tutorial.html#frlb>`_

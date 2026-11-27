.. _widget-classes:

Widget Classes
==============

.. currentmodule:: urwid

Widget Base Classes
-------------------

Widget
~~~~~~

.. autoclass:: Widget
   :private-members: _invalidate, _emit

WidgetWrap
~~~~~~~~~~

.. autoclass:: WidgetWrap

WidgetDecoration
~~~~~~~~~~~~~~~~

.. autoclass:: WidgetDecoration

WidgetContainerMixin
~~~~~~~~~~~~~~~~~~~~

.. autoclass:: WidgetContainerMixin

SelectNavigationMixin
~~~~~~~~~~~~~~~~~~~~~

.. autoclass:: SelectNavigationMixin
   :private-members: _select_candidates, _select_enter_focus, _select_keypress_unhandled

SelectNavigationListContentsMixin
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. autoclass:: SelectNavigationListContentsMixin


Basic Widget Classes
--------------------

Text
~~~~

.. autoclass:: Text

Edit
~~~~

.. autoclass:: Edit
   :inherited-members:
   :exclude-members: base_widget, enter_selectable, focus, focus_position, pack, request_focus

IntEdit
~~~~~~~

.. autoclass:: IntEdit

TreeWidget
~~~~~~~~~~

.. autoclass:: TreeWidget

.. autoclass:: urwid.widget.treetools.TreeSymbols
   :undoc-members:


.. currentmodule:: urwid.numedit

Extended Numerical Editing Classes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

IntegerEdit
~~~~~~~~~~~

.. autoclass:: IntegerEdit

FloatEdit
~~~~~~~~~~~

.. autoclass:: FloatEdit


File Chooser Classes
--------------------

.. currentmodule:: urwid

FileChooser
~~~~~~~~~~~

.. autoclass:: FileChooser
   :exclude-members: base_widget, focus, pack, render, rows, selectable, sizing

PathCompleter
~~~~~~~~~~~~~

.. autoclass:: PathCompleter
   :special-members: __call__

FileKind
~~~~~~~~

.. autoclass:: FileKind
   :undoc-members:

FileEntry
~~~~~~~~~

.. autoclass:: urwid.widget.FileEntry

DirectoryReader
~~~~~~~~~~~~~~~

.. autoclass:: urwid.widget.DirectoryReader


Control Widget Classes
----------------------

.. currentmodule:: urwid

Button
~~~~~~

.. autoclass:: Button

CheckBox
~~~~~~~~

.. autoclass:: CheckBox

RadioButton
~~~~~~~~~~~

.. autoclass:: RadioButton

DropDown
~~~~~~~~

.. autoclass:: DropDown

ActionMenu
~~~~~~~~~~

.. autoclass:: ActionMenu

MenuItem
~~~~~~~~

.. autoclass:: MenuItem


Special cases text widgets
--------------------------

.. currentmodule:: urwid

SelectableIcon
~~~~~~~~~~~~~~

.. autoclass:: SelectableIcon

ANSIText
~~~~~~~~

.. autoclass:: ANSIText


Decoration Widget Classes
-------------------------

AttrMap
~~~~~~~

.. autoclass:: AttrMap

Padding
~~~~~~~

.. autoclass:: Padding

Filler
~~~~~~

.. autoclass:: Filler

Divider
~~~~~~~

.. autoclass:: Divider

LineBox
~~~~~~~

.. autoclass:: LineBox

SolidFill
~~~~~~~~~

.. autoclass:: SolidFill

Pop-up Widget Classes
---------------------

PopUpLauncher
~~~~~~~~~~~~~

.. autoclass:: PopUpLauncher

PopUpTarget
~~~~~~~~~~~

.. autoclass:: PopUpTarget

PopUpPlacement
~~~~~~~~~~~~~~

.. autoclass:: PopUpPlacement

Special Widget Classes
----------------------

Notifications
~~~~~~~~~~~~~

.. autoclass:: Notifications

Notification
~~~~~~~~~~~~

.. autoclass:: Notification

WidgetDisable
~~~~~~~~~~~~~

.. autoclass:: WidgetDisable

WidgetPlaceholder
~~~~~~~~~~~~~~~~~

.. autoclass:: WidgetPlaceholder

Container Widget Classes
------------------------

Frame
~~~~~

.. autoclass:: Frame

ListBox
~~~~~~~

.. autoclass:: ListBox

TreeListBox
~~~~~~~~~~~

.. autoclass:: TreeListBox

Columns
~~~~~~~

.. autoclass:: Columns

   .. autoproperty:: focus_position

Pile
~~~~

.. autoclass:: Pile

   .. autoproperty:: focus_position

GridFlow
~~~~~~~~

.. autoclass:: GridFlow

   .. autoproperty:: focus_position

Table
~~~~~

.. autoclass:: Table

TableRow
~~~~~~~~

.. autoclass:: TableRow

TableColumn
~~~~~~~~~~~

.. autoclass:: TableColumn

TableLayout
~~~~~~~~~~~

.. autoclass:: urwid.widget.TableLayout

Tabs
~~~~

.. autoclass:: Tabs

   .. autoproperty:: focus_position

.. autoclass:: urwid.widget.tabs.TabsSymbols

BoxAdapter
~~~~~~~~~~

.. autoclass:: BoxAdapter

Overlay
~~~~~~~

.. autoclass:: Overlay

OverlayStack
~~~~~~~~~~~~

.. autoclass:: OverlayStack

Graphic Widget Classes
----------------------

BarGraph
~~~~~~~~

.. autoclass:: BarGraph

GraphVScale
~~~~~~~~~~~

.. autoclass:: GraphVScale

ProgressBar
~~~~~~~~~~~

.. autoclass:: ProgressBar

Spinner
~~~~~~~

.. autoclass:: Spinner

.. autoclass:: urwid.widget.spinner.SpinnerFrames

BigText
~~~~~~~

.. autoclass:: BigText

.. autofunction:: get_all_fonts

Terminal
~~~~~~~~

.. autoclass:: Terminal

.. autoclass:: TerminalOutput


Scroll Widget Classes
---------------------

Scrollable
~~~~~~~~~~

.. autoclass:: Scrollable

ScrollBar
~~~~~~~~~

.. autoclass:: ScrollBar

.. autoclass:: urwid.widget.scrollable.ScrollbarSymbols
   :undoc-members:

.. currentmodule:: urwid

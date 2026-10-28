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

IntEdit
~~~~~~~

.. autoclass:: IntEdit

TreeWidget
~~~~~~~~~~

.. autoclass:: TreeWidget


.. currentmodule:: urwid.numedit

Extended Numerical Editing Classes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

IntegerEdit
~~~~~~~~~~~

.. autoclass:: IntegerEdit

FloatEdit
~~~~~~~~~~~

.. autoclass:: FloatEdit


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

Special Widget Classes
----------------------

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

Pile
~~~~

.. autoclass:: Pile

GridFlow
~~~~~~~~

.. autoclass:: GridFlow

BoxAdapter
~~~~~~~~~~

.. autoclass:: BoxAdapter

Overlay
~~~~~~~

.. autoclass:: Overlay

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

BigText
~~~~~~~

.. autoclass:: BigText

.. autofunction:: get_all_fonts

Terminal
~~~~~~~~

.. autoclass:: Terminal


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

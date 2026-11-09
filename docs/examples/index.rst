.. _example-programs:

********************
  Example Programs
********************

.. currentmodule:: urwid

These example programs may be found in the `examples directory
<https://github.com/urwid/urwid/tree/master/examples>`_ of the Urwid repository.

tour.py
-------

Source: :doc:`code/tour`

.. image:: tour1.png
   :scale: 50%
.. image:: tour2.png
   :scale: 50%
.. image:: tour3.png
   :scale: 50%

Show how many of the standard widgets may be arranged
on the screen, including a DropDown with its list open


graph.py
--------

Source: :doc:`code/graph`

.. image:: graph2.png
   :scale: 50%

Demonstrate BarGraph widget and alarms used for animation


edit.py
-------

Source: :doc:`code/edit`

.. image:: edit1.png
   :scale: 50%
.. image:: edit2.png
   :scale: 50%

A simple text editor with lazy loading


browse.py
---------

Source: :doc:`code/browse`

.. image:: browse2.png
   :scale: 50%

A lazy directory browser with file selection, tree-view, custom widgets
and list walker


subproc.py
----------

Source: :doc:`code/subproc`

.. image:: subproc1.png
   :scale: 50%
.. image:: subproc2.png
   :scale: 50%

Monitor and display results from a subprocess


calc.py
-------

Source: :doc:`code/calc`

.. image:: calc3.png
   :scale: 50%
.. image:: calc4.png
   :scale: 50%
.. image:: calc5.png
   :scale: 50%
.. image:: calc6.png
   :scale: 50%

A calculator with a decimal and a programmer tab over one display of big
digits, which carries the number shown to the selected tab. It takes numeric
keypad input, and has a theme pop-up that previews the palette until OK or
Cancel, and a help dialog. The calculator logic is plain Python, kept apart
from the user interface in the same file


notifications.py
----------------

Source: :doc:`code/notifications`

Messages of each severity in the footer of a window, each one dismissed after
five seconds, and a message that stays until it is dismissed


spinner.py
----------

Source: :doc:`code/spinner`

A spinner for every frame preset, started, stopped, stepped and sped up together


external_editor.py
------------------

Source: :doc:`code/external_editor`

Hand the terminal to an external editor and show the text written in it


thread_worker.py
----------------

Source: :doc:`code/thread_worker`

Run a slow computation on a worker thread and show its progress and result


palette_test.py
---------------

Source: :doc:`code/palette_test`

.. image:: palette_test2.png
   :scale: 50%

Show available colors in various screen modes


bigtext.py
----------

Source: :doc:`code/bigtext`

.. image:: bigtext2.png
   :scale: 50%
.. image:: bigtext3.png
   :scale: 50%

demonstrate the BigText widget

.. toctree::
   :hidden:

   code/tour
   code/graph
   code/edit
   code/browse
   code/subproc
   code/calc
   code/notifications
   code/spinner
   code/external_editor
   code/thread_worker
   code/palette_test
   code/bigtext

Testing Helpers
===============

.. module:: urwid.testing

Rendering
---------

.. autofunction:: render_text

.. autofunction:: render_runs

.. autofunction:: resolve_attr

.. autofunction:: resolve_runs

Sizing checks
-------------

.. autofunction:: check_sizing

.. autofunction:: check_box_sizing

.. autofunction:: check_flow_sizing

.. autofunction:: check_fixed_sizing

Input
-----

.. autofunction:: press

.. autofunction:: click

Harness screen
--------------

.. autoclass:: ScriptedScreen
   :members: last_text, get_cols_rows, draw_screen, get_input, hook_event_loop, unhook_event_loop

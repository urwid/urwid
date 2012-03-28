Main Loop and Event Loop Reference
==================================

.. autoexception:: urwid.ExitMainLoop

.. autoclass:: urwid.MainLoop
   :members: set_alarm_in, set_alarm_at, remove_alarm,
             watch_pipe, remove_watch_pipe,
             run, process_input, input_filter, unhandled_input,
             entering_idle, draw_screen,

   .. attribute:: widget

      Property for the topmost widget used. This must be a box widget.

.. autoclass:: urwid.SelectEventLoop
   :members: alarm, remove_alarm, watch_file, remove_watch_file,
             enter_idle, remove_enter_idle, run

.. autoclass:: urwid.GLibEventLoop
   :members: alarm, remove_alarm, watch_file, remove_watch_file,
             enter_idle, remove_enter_idle, run, handle_exit

.. autoclass:: urwid.TwistedEventLoop
   :members: alarm, remove_alarm, watch_file, remove_watch_file,
             enter_idle, remove_enter_idle, run, handle_exit


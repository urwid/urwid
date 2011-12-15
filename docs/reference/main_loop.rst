:mod:`urwid.main_loop` --- Standard Uwrid main loop
===================================================

.. module:: urwid.main_loop
   :synopsis: Standard Urwid main loop

.. exception:: ExitMainLoop

   When this exception is not handled, the main loop exits.

.. class:: MainLoop(widget[, palette=[], screen=None, handle_mouse=True, \
                    input_filter=None, unhandled_input=None, event_loop=None, \
                    pop_ups=False])

   This is the standard main loop implementation with a single screen.

   *widget* is the topmost widget used for painting the screen, stored as
   self.widget and may be modified. Must be a box widget.

   *palette* -- initial palette for screen.

   *screen* -- screen object or None to use raw_display.Screen, stored as
   self.screen

   *handle_mouse* -- ``True`` to process mouse events, passed to
   ``self.screen``

   *input_filter* -- a function to filter input before sending it to
   ``self.widget``, called from ``self.input_filter``

   *unhandled_input* -- a function called when input is not handled by
   ``self.widget``, called from ``self.unhandled_input``

   *event_loop* -- if screen supports external an event loop it may be given
   here, or leave as None to use

   *SelectEventLoop*, stored as ``self.event_loop``

   *pop_ups* -- ``True`` to wrap ``self.widget`` with a ``PopUpTarget``
   instance to allow any widget to open a pop-up anywhere on the screen

   .. attribute:: widget

      Property for the topmost widget used. This must be a box widget.

   .. attribute:: pop_ups

      Property for the pop_ups flag.

   .. method:: set_alarm_in(sec, callback, user_data=None)

         Schedule an alarm in *sec* seconds that will call *callback* from the
         within the :meth:`run` function.

         *sec* floating point seconds until alarm. *callback* a callable which
         accept two arguments, the main loop and the object *user_data*.

   .. method:: set_alarm_at(tm, callback, user_data=None)

         Schedule at *tm* time that will call *callback* from the within the
         :meth`run` function. Returns a handle that may be passed to
         :meth:`remove_alarm`.

         *tm* is a floating point local time of alarm. *callback* is a callable
         which accept two parameters, the main loop and the *user_data* object.

   .. method:: remove_alarm(handle)

         Remove an alarm. Return ``True`` if the handle was found, ``False``
         otherwise.

   .. method:: watch_pipe(callback)

        Create a pipe for use by a subprocess or thread to trigger a callback
        in the process/thread running the *MainLoop*.

        *callback* -- function to call :meth:`MainLoop.run` thread/process

        This function returns a file descriptor attached to the write end of a
        pipe. The read end of the pipe is added to the list of files the event
        loop is watching. When data is written to the pipe the callback
        function will be called and passed a single value containing data read.

        This method should be used any time you want to update widgets from
        another thread or subprocess.

        Data may be written to the returned file descriptor with os.write(fd,
        data). Ensure that data is less than 512 bytes (or 4K on Linux) so
        that the callback will be triggered just once with the complete value
        of data passed in.

        If the callback returns ``False`` then the watch will be removed and the
        read end of the pipe will be closed. You are responsible for closing
        the write end of the pipe.

   .. method:: remove_watch_pipe(write_fd)

        Close the read end of the pipe and remove the watch created by
        :meth:`watch_pipe`. You are responsible for closing the write end of
        the pipe.

        Returns ``True`` if the watch pipe exists, ``False`` otherwise

   .. method:: watch_file(fd, callback)

        Call *callback* when *fd* has some data to read. No parameters are
        passed to callback.

        Returns a handle that may be passed to :meth:`remove_watch_file`.

   .. method:: remove_watch_file(handle)

        Remove a watch file. Returns ``True`` if the watch file
        exists,``False`` otherwise.

   .. method:: run()

         Start the main loop handling input events and updating the screen. The
         loop will continue until an :exc:`ExitMainLoop` exception is raised.

         This function will call :meth:`screen.run_wrapper` if
         :meth:`screen.start` has not already been called.

   .. method:: _run()

      TODO

   .. method:: _update(timeout=False)

      TODO

   .. method:: _run_screen_event_loop()

      This method is used when the screen does not support using external event
      loops.

      The alarms stored in the SelectEventLoop in self.event_loop are modified
      by this method.

   .. method:: process_input(keys)

      This function will pass keyboard input and mouse events to *self.widget*.
      This function is called automatically from the :meth:`run` method when
      there is input, but may also be called to simulate input from the user.

      *keys* is a list of input returned from :meth:`Screen.get_input`.

      Returns ``True`` if any key was handled by a widget or the
      :meth:`unhandled_input` method.

   .. method:: input_filter(keys, raw)

      This function is passed each all the input events and raw keystroke
      values. These values are passed to the :func:`input_filter` function
      passed to the constructor. That function must return a list of keys to
      be passed to the widgets to handle. If no :func:`input_filter` was
      defined this implementation will return all the input events.

   .. method:: unhandled_input(input)

      This function is called with any input that was not handled by the
      widgets, and calls the :func:`unhandled_input` function passed to the
      constructor. If no :func:`unhandled_input` was defined then the input
      will be ignored.

      *input* is the keyboard or mouse input.

      The :func:`unhandled_input` method should return ``True`` if it handled
      the input.

   .. method:: entering_idle()

      This function is called whenever the event loop is about to enter the
      idle state. :meth:`MainLoop.draw_screen` is called here to update the
      screen if anything has changed.

   .. method:: draw_screen()

      Renter the widgets and paint the screen. This function is called
      automatically from :meth:`run` but may be called additional times if
      repainting is required without also processing input.

.. class:: SelectEventLoop()

   Event loop based on :func:`select.select`

.. class:: GLibEventLoop()

      Event loop based on :class:`gobject.MainLoop`

   .. method:: handle_exit(f)

      Decorator that cleanly exits the :class:`GLibEventLoop` if
      :exc:`ExitMainLoop` is thrown inside of the wrapped function. Store the
      exception info if some other exception occurs, it will be reraised after
      the loop quits.

      *f* -- function to be wrapped

.. class:: TwistedInputDescriptor(reactor, fd, cb)

   TODO

.. class:: TwistedEventLoop(reactor=None, manage_reactor=True)

      Event loop based on Twisted_

      *reactor* -- reactor object to use, if ``None`` defaults to
      ``twisted.internet.reactor``.  *manage_reactor* -- ``True`` if you want
      this event loop to run and stop the reactor.

      .. WARNING::
         Twisted's reactor doesn't like to be stopped and run again.  If you
         need to stop and run your :class:`MainLoop`, consider setting
         ``manage_reactor=False`` and take care of running/stopping the reactor
         at the beginning/ending of your program yourself.

   .. method:: _enable_twisted_idle()

      Twisted's reactors don't have an idle or enter-idle callback
      so the best we can do for now is to set a timer event in a very
      short time to approximate an enter-idle callback.

      .. WARNING::
         This will perform worse than the other event loops until we can find a
         fix or workaround

   .. method:: handle_exit(f, enable_idle=True)

      Decorator that cleanly exits the :class:`TwistedEventLoop` if
      :class:`ExitMainLoop` is thrown inside of the wrapped function. Store the
      exception info if some other exception occurs, it will be reraised after
      the loop quits.

      *f* -- function to be wrapped

.. _Twisted: http://twistedmatrix.com/trac/

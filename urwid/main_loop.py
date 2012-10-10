#!/usr/bin/python
#
# Urwid main loop code
#    Copyright (C) 2004-2012  Ian Ward
#    Copyright (C) 2008 Walter Mundt
#    Copyright (C) 2009 Andrew Psaltis
#
#    This library is free software; you can redistribute it and/or
#    modify it under the terms of the GNU Lesser General Public
#    License as published by the Free Software Foundation; either
#    version 2.1 of the License, or (at your option) any later version.
#
#    This library is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#    Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public
#    License along with this library; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#
# Urwid web site: http://excess.org/urwid/


import time
import heapq
import select
import fcntl
import os

from urwid.util import is_mouse_event
from urwid.compat import PYTHON3
from urwid.command_map import command_map, REDRAW_SCREEN
from urwid.wimp import PopUpTarget
from urwid import signals
from urwid.display_common import INPUT_DESCRIPTORS_CHANGED

PIPE_BUFFER_READ_SIZE = 4096 # can expect this much on Linux, so try for that

class ExitMainLoop(Exception):
    """
    When this exception is raised within a main loop the main loop
    will exit cleanly.
    """
    pass

class MainLoop(object):
    """
    This is the standard main loop implementation for a single interactive
    session.

    :param widget: the topmost widget used for painting the screen, stored as
                   :attr:`widget` and may be modified. Must be a box widget.
    :type widget: widget instance

    :param palette: initial palette for screen
    :type palette: iterable of palette entries

    :param screen: screen to use, default is a new :class:`raw_display.Screen`
                   instance; stored as :attr:`screen`
    :type screen: display module screen instance

    :param handle_mouse: ``True`` to ask :attr:`.screen` to process mouse events
    :type handle_mouse: bool

    :param input_filter: a function to filter input before sending it to
                   :attr:`.widget`, called from :meth:`.input_filter`
    :type input_filter: callable

    :param unhandled_input: a function called when input is not handled by
                            :attr:`.widget`, called from :meth:`.unhandled_input`
    :type unhandled_input: callable

    :param event_loop: if :attr:`.screen` supports external an event loop it may be
                       given here, default is a new :class:`SelectEventLoop` instance;
                       stored as :attr:`.event_loop`
    :type event_loop: event loop instance

    :param pop_ups: `True` to wrap :attr:`.widget` with a :class:`PopUpTarget`
                    instance to allow any widget to open a pop-up anywhere on the screen
    :type pop_ups: boolean


    .. attribute:: screen

        The screen object this main loop uses for screen updates and reading input

    .. attribute:: event_loop

        The event loop object this main loop uses for waiting on alarms and IO
    """

    def __init__(self, widget, palette=(), screen=None,
            handle_mouse=True, input_filter=None, unhandled_input=None,
            event_loop=None, pop_ups=False):
        self._widget = widget
        self.handle_mouse = handle_mouse
        self.pop_ups = pop_ups # triggers property setting side-effect

        if not screen:
            from urwid import raw_display
            screen = raw_display.Screen()

        if palette:
            screen.register_palette(palette)

        self.screen = screen
        self.screen_size = None

        self._unhandled_input = unhandled_input
        self._input_filter = input_filter

        if not hasattr(screen, 'get_input_descriptors'
                ) and event_loop is not None:
            raise NotImplementedError("screen object passed "
                "%r does not support external event loops" % (screen,))
        if event_loop is None:
            event_loop = SelectEventLoop()
        self.event_loop = event_loop

        self._input_timeout = None
        self._watch_pipes = {}

    def _set_widget(self, widget):
        self._widget = widget
        if self.pop_ups:
            self._topmost_widget.original_widget = self._widget
        else:
            self._topmost_widget = self._widget
    widget = property(lambda self:self._widget, _set_widget, doc=
       """
       Property for the topmost widget used to draw the screen.
       This must be a box widget.
       """)

    def _set_pop_ups(self, pop_ups):
        self._pop_ups = pop_ups
        if pop_ups:
            self._topmost_widget = PopUpTarget(self._widget)
        else:
            self._topmost_widget = self._widget
    pop_ups = property(lambda self:self._pop_ups, _set_pop_ups)

    def set_alarm_in(self, sec, callback, user_data=None):
        """
        Schedule an alarm in *sec* seconds that will call *callback* from the
        within the :meth:`run` method.

        :param sec: seconds until alarm
        :type sec: float
        :param callback: function to call with two parameters: this main loop
                         object and *user_data*
        :type callback: callable
        """
        def cb():
            callback(self, user_data)
        return self.event_loop.alarm(sec, cb)

    def set_alarm_at(self, tm, callback, user_data=None):
        """
        Schedule an alarm at *tm* time that will call *callback* from the
        within the :meth`run` function. Returns a handle that may be passed to
        :meth:`remove_alarm`.

        :param tm: time to call callback e.g. ``time.time() + 5``
        :type tm: float
        :param callback: function to call with two parameters: this main loop
                         object and *user_data*
        :type callback: callable
        """
        def cb():
            callback(self, user_data)
        return self.event_loop.alarm(tm - time.time(), cb)

    def remove_alarm(self, handle):
        """
        Remove an alarm. Return ``True`` if *handle* was found, ``False``
        otherwise.
        """
        return self.event_loop.remove_alarm(handle)

    def watch_pipe(self, callback):
        """
        Create a pipe for use by a subprocess or thread to trigger a callback
        in the process/thread running the main loop.

        :param callback: function taking one parameter to call from within
                         the process/thread running the main loop
        :type callback: callable

        This method returns a file descriptor attached to the write end of a
        pipe. The read end of the pipe is added to the list of files
        :attr:`event_loop` is watching. When data is written to the pipe the
        callback function will be called and passed a single value containing
        data read from the pipe.

        This method may be used any time you want to update widgets from
        another thread or subprocess.

        Data may be written to the returned file descriptor with
        ``os.write(fd, data)``. Ensure that data is less than 512 bytes (or 4K
        on Linux) so that the callback will be triggered just once with the
        complete value of data passed in.

        If the callback returns ``False`` then the watch will be removed from
        :attr:`event_loop` and the read end of the pipe will be closed. You
        are responsible for closing the write end of the pipe with
        ``os.close(fd)``.
        """
        pipe_rd, pipe_wr = os.pipe()
        fcntl.fcntl(pipe_rd, fcntl.F_SETFL, os.O_NONBLOCK)
        watch_handle = None

        def cb():
            data = os.read(pipe_rd, PIPE_BUFFER_READ_SIZE)
            rval = callback(data)
            if rval is False:
                self.event_loop.remove_watch_file(watch_handle)
                os.close(pipe_rd)

        watch_handle = self.event_loop.watch_file(pipe_rd, cb)
        self._watch_pipes[pipe_wr] = (watch_handle, pipe_rd)
        return pipe_wr

    def remove_watch_pipe(self, write_fd):
        """
        Close the read end of the pipe and remove the watch created by
        :meth:`watch_pipe`. You are responsible for closing the write end of
        the pipe.

        Returns ``True`` if the watch pipe exists, ``False`` otherwise
        """
        try:
            watch_handle, pipe_rd = self._watch_pipes.pop(write_fd)
        except KeyError:
            return False

        if not self.event_loop.remove_watch_file(watch_handle):
            return False
        os.close(pipe_rd)
        return True

    def watch_file(self, fd, callback):
        """
        Call *callback* when *fd* has some data to read. No parameters are
        passed to callback.

        Returns a handle that may be passed to :meth:`remove_watch_file`.
        """
        return self.event_loop.watch_file(fd, callback)

    def remove_watch_file(self, handle):
        """
        Remove a watch file. Returns ``True`` if the watch file
        exists, ``False`` otherwise.
        """
        return self.event_loop.remove_watch_file(handle)


    def run(self):
        """
        Start the main loop handling input events and updating the screen. The
        loop will continue until an :exc:`ExitMainLoop` exception is raised.

        This method will use :attr:`screen`'s run_wrapper() method if
        :attr:`screen`'s start() method has not already been called.
        """
        try:
            if self.screen.started:
                self._run()
            else:
                self.screen.run_wrapper(self._run)
        except ExitMainLoop:
            pass

    def _test_run(self):
        """
        >>> w = _refl("widget")   # _refl prints out function calls
        >>> w.render_rval = "fake canvas"  # *_rval is used for return values
        >>> scr = _refl("screen")
        >>> scr.get_input_descriptors_rval = [42]
        >>> scr.get_cols_rows_rval = (20, 10)
        >>> scr.started = True
        >>> scr._urwid_signals = {}
        >>> evl = _refl("event_loop")
        >>> evl.enter_idle_rval = 1
        >>> evl.watch_file_rval = 2
        >>> ml = MainLoop(w, [], scr, event_loop=evl)
        >>> ml.run()    # doctest:+ELLIPSIS
        screen.set_mouse_tracking()
        screen.get_cols_rows()
        widget.render((20, 10), focus=True)
        screen.draw_screen((20, 10), 'fake canvas')
        screen.get_input_descriptors()
        event_loop.watch_file(42, <bound method ...>)
        event_loop.enter_idle(<bound method ...>)
        event_loop.run()
        event_loop.remove_enter_idle(1)
        event_loop.remove_watch_file(2)
        >>> scr.started = False
        >>> ml.run()    # doctest:+ELLIPSIS
        screen.run_wrapper(<bound method ...>)
        """

    def _run(self):
        if self.handle_mouse:
            self.screen.set_mouse_tracking()

        if not hasattr(self.screen, 'get_input_descriptors'):
            return self._run_screen_event_loop()

        self.draw_screen()

        fd_handles = []
        def reset_input_descriptors(only_remove=False):
            for handle in fd_handles:
                self.event_loop.remove_watch_file(handle)
            if only_remove:
                del fd_handles[:]
            else:
                fd_handles[:] = [
                    self.event_loop.watch_file(fd, self._update)
                    for fd in self.screen.get_input_descriptors()]
            if not fd_handles and self._input_timeout is not None:
                self.event_loop.remove_alarm(self._input_timeout)

        try:
            signals.connect_signal(self.screen, INPUT_DESCRIPTORS_CHANGED,
                reset_input_descriptors)
        except NameError:
            pass
        # watch our input descriptors
        reset_input_descriptors()
        idle_handle = self.event_loop.enter_idle(self.entering_idle)

        # Go..
        self.event_loop.run()

        # tidy up
        self.event_loop.remove_enter_idle(idle_handle)
        reset_input_descriptors(True)
        signals.disconnect_signal(self.screen, INPUT_DESCRIPTORS_CHANGED,
            reset_input_descriptors)

    def _update(self, timeout=False):
        """
        >>> w = _refl("widget")
        >>> w.selectable_rval = True
        >>> w.mouse_event_rval = True
        >>> scr = _refl("screen")
        >>> scr.get_cols_rows_rval = (15, 5)
        >>> scr.get_input_nonblocking_rval = 1, ['y'], [121]
        >>> evl = _refl("event_loop")
        >>> ml = MainLoop(w, [], scr, event_loop=evl)
        >>> ml._input_timeout = "old timeout"
        >>> ml._update()    # doctest:+ELLIPSIS
        event_loop.remove_alarm('old timeout')
        screen.get_input_nonblocking()
        event_loop.alarm(1, <function ...>)
        screen.get_cols_rows()
        widget.selectable()
        widget.keypress((15, 5), 'y')
        >>> scr.get_input_nonblocking_rval = None, [("mouse press", 1, 5, 4)
        ... ], []
        >>> ml._update()
        screen.get_input_nonblocking()
        widget.mouse_event((15, 5), 'mouse press', 1, 5, 4, focus=True)
        >>> scr.get_input_nonblocking_rval = None, [], []
        >>> ml._update()
        screen.get_input_nonblocking()
        """
        if self._input_timeout is not None and not timeout:
            # cancel the timeout, something else triggered the update
            self.event_loop.remove_alarm(self._input_timeout)
        self._input_timeout = None

        max_wait, keys, raw = self.screen.get_input_nonblocking()
        
        if max_wait is not None:
            # if get_input_nonblocking wants to be called back
            # make sure it happens with an alarm
            self._input_timeout = self.event_loop.alarm(max_wait, 
                lambda: self._update(timeout=True)) 

        keys = self.input_filter(keys, raw)

        if keys:
            self.process_input(keys)
            if 'window resize' in keys:
                self.screen_size = None

    def _run_screen_event_loop(self):
        """
        This method is used when the screen does not support using
        external event loops.

        The alarms stored in the SelectEventLoop in :attr:`event_loop`
        are modified by this method.
        """
        next_alarm = None

        while True:
            self.draw_screen()

            if not next_alarm and self.event_loop._alarms:
                next_alarm = heapq.heappop(self.event_loop._alarms)

            keys = None
            while not keys:
                if next_alarm:
                    sec = max(0, next_alarm[0] - time.time())
                    self.screen.set_input_timeouts(sec)
                else:
                    self.screen.set_input_timeouts(None)
                keys, raw = self.screen.get_input(True)
                if not keys and next_alarm: 
                    sec = next_alarm[0] - time.time()
                    if sec <= 0:
                        break

            keys = self.input_filter(keys, raw)

            if keys:
                self.process_input(keys)

            while next_alarm:
                sec = next_alarm[0] - time.time()
                if sec > 0:
                    break
                tm, callback = next_alarm
                callback()

                if self.event_loop._alarms:
                    next_alarm = heapq.heappop(self.event_loop._alarms)
                else:
                    next_alarm = None

            if 'window resize' in keys:
                self.screen_size = None

    def _test_run_screen_event_loop(self):
        """
        >>> w = _refl("widget")
        >>> scr = _refl("screen")
        >>> scr.get_cols_rows_rval = (10, 5)
        >>> scr.get_input_rval = [], []
        >>> ml = MainLoop(w, screen=scr)
        >>> def stop_now(loop, data):
        ...     raise ExitMainLoop()
        >>> handle = ml.set_alarm_in(0, stop_now)
        >>> try:
        ...     ml._run_screen_event_loop()
        ... except ExitMainLoop:
        ...     pass
        screen.get_cols_rows()
        widget.render((10, 5), focus=True)
        screen.draw_screen((10, 5), None)
        screen.set_input_timeouts(0)
        screen.get_input(True)
        """

    def process_input(self, keys):
        """
        This method will pass keyboard input and mouse events to :attr:`widget`.
        This method is called automatically from the :meth:`run` method when
        there is input, but may also be called to simulate input from the user.

        *keys* is a list of input returned from :attr:`screen`'s get_input()
        or get_input_nonblocking() methods.

        Returns ``True`` if any key was handled by a widget or the
        :meth:`unhandled_input` method.
        """
        if not self.screen_size:
            self.screen_size = self.screen.get_cols_rows()

        something_handled = False

        for k in keys:
            if k == 'window resize':
                continue
            if is_mouse_event(k):
                event, button, col, row = k
                if self._topmost_widget.mouse_event(self.screen_size,
                    event, button, col, row, focus=True ):
                    k = None
            elif self._topmost_widget.selectable():
                k = self._topmost_widget.keypress(self.screen_size, k)
            if k:
                if command_map[k] == REDRAW_SCREEN:
                    self.screen.clear()
                    something_handled = True
                else:
                    something_handled |= bool(self.unhandled_input(k))
            else:
                something_handled = True

        return something_handled

    def _test_process_input(self):
        """
        >>> w = _refl("widget")
        >>> w.selectable_rval = True
        >>> scr = _refl("screen")
        >>> scr.get_cols_rows_rval = (10, 5)
        >>> ml = MainLoop(w, [], scr)
        >>> ml.process_input(['enter', ('mouse drag', 1, 14, 20)])
        screen.get_cols_rows()
        widget.selectable()
        widget.keypress((10, 5), 'enter')
        widget.mouse_event((10, 5), 'mouse drag', 1, 14, 20, focus=True)
        True
        """

    def input_filter(self, keys, raw):
        """
        This function is passed each all the input events and raw keystroke
        values. These values are passed to the *input_filter* function
        passed to the constructor. That function must return a list of keys to
        be passed to the widgets to handle. If no *input_filter* was
        defined this implementation will return all the input events.
        """
        if self._input_filter:
            return self._input_filter(keys, raw)
        return keys

    def unhandled_input(self, input):
        """
        This function is called with any input that was not handled by the
        widgets, and calls the *unhandled_input* function passed to the
        constructor. If no *unhandled_input* was defined then the input
        will be ignored.

        *input* is the keyboard or mouse input.

        The *unhandled_input* function should return ``True`` if it handled
        the input.
        """
        if self._unhandled_input:
            return self._unhandled_input(input)

    def entering_idle(self):
        """
        This method is called whenever the event loop is about to enter the
        idle state. :meth:`draw_screen` is called here to update the
        screen when anything has changed.
        """
        if self.screen.started:
            self.draw_screen()

    def draw_screen(self):
        """
        Render the widgets and paint the screen. This method is called
        automatically from :meth:`entering_idle`.

        If you modify the widgets displayed outside of handling input or
        responding to an alarm you will need to call this method yourself
        to repaint the screen.
        """
        if not self.screen_size:
            self.screen_size = self.screen.get_cols_rows()

        canvas = self._topmost_widget.render(self.screen_size, focus=True)
        self.screen.draw_screen(self.screen_size, canvas)





class SelectEventLoop(object):
    """
    Event loop based on :func:`select.select`
    """

    def __init__(self):
        self._alarms = []
        self._watch_files = {}
        self._idle_handle = 0
        self._idle_callbacks = {}

    def _test_event_loop(self):
        """
        >>> import os
        >>> rd, wr = os.pipe()
        >>> evl = SelectEventLoop()
        >>> def step1():
        ...     print "writing"
        ...     os.write(wr, "hi".encode('ascii'))
        >>> def step2():
        ...     print os.read(rd, 2).decode('ascii')
        ...     raise ExitMainLoop
        >>> handle = evl.alarm(0, step1)
        >>> handle = evl.watch_file(rd, step2)
        >>> evl.run()
        writing
        hi
        """

    def alarm(self, seconds, callback):
        """
        Call callback() given time from from now.  No parameters are
        passed to callback.

        Returns a handle that may be passed to remove_alarm()

        seconds -- floating point time to wait before calling callback
        callback -- function to call from event loop
        """
        tm = time.time() + seconds
        heapq.heappush(self._alarms, (tm, callback))
        return (tm, callback)

    def remove_alarm(self, handle):
        """
        Remove an alarm.

        Returns True if the alarm exists, False otherwise
        """
        try:
            self._alarms.remove(handle)
            heapq.heapify(self._alarms)
            return True
        except ValueError:
            return False

    def _test_remove_alarm(self):
        """
        >>> evl = SelectEventLoop()
        >>> handle = evl.alarm(50, lambda: None)
        >>> evl.remove_alarm(handle)
        True
        >>> evl.remove_alarm(handle)
        False
        """

    def watch_file(self, fd, callback):
        """
        Call callback() when fd has some data to read.  No parameters
        are passed to callback.

        Returns a handle that may be passed to remove_watch_file()

        fd -- file descriptor to watch for input
        callback -- function to call when input is available
        """
        self._watch_files[fd] = callback
        return fd

    def remove_watch_file(self, handle):
        """
        Remove an input file.

        Returns True if the input file exists, False otherwise
        """
        if handle in self._watch_files:
            del self._watch_files[handle]
            return True
        return False

    def _test_remove_watch_file(self):
        """
        >>> evl = SelectEventLoop()
        >>> handle = evl.watch_file(5, lambda: None)
        >>> evl.remove_watch_file(handle)
        True
        >>> evl.remove_watch_file(handle)
        False
        """

    def enter_idle(self, callback):
        """
        Add a callback for entering idle.

        Returns a handle that may be passed to remove_idle()
        """
        self._idle_handle += 1
        self._idle_callbacks[self._idle_handle] = callback
        return self._idle_handle

    def remove_enter_idle(self, handle):
        """
        Remove an idle callback.

        Returns True if the handle was removed.
        """
        try:
            del self._idle_callbacks[handle]
        except KeyError:
            return False
        return True

    def _entering_idle(self):
        """
        Call all the registered idle callbacks.
        """
        for callback in self._idle_callbacks.values():
            callback()

    def run(self):
        """
        Start the event loop.  Exit the loop when any callback raises
        an exception.  If ExitMainLoop is raised, exit cleanly.
        """
        try:
            self._did_something = True
            while True:
                try:
                    self._loop()
                except select.error, e:
                    if e.args[0] != 4:
                        # not just something we need to retry
                        raise
        except ExitMainLoop:
            pass

    def _test_run(self):
        """
        >>> import os
        >>> rd, wr = os.pipe()
        >>> os.write(wr, "data".encode('ascii')) # something to read from rd
        4
        >>> evl = SelectEventLoop()
        >>> def say_hello():
        ...     print "hello"
        >>> def say_waiting():
        ...     print "waiting"
        >>> def exit_clean():
        ...     print "clean exit"
        ...     raise ExitMainLoop
        >>> def exit_error():
        ...     1/0
        >>> handle = evl.alarm(0.01, exit_clean)
        >>> handle = evl.alarm(0.005, say_hello)
        >>> evl.enter_idle(say_waiting)
        1
        >>> evl.run()
        waiting
        hello
        waiting
        clean exit
        >>> handle = evl.watch_file(rd, exit_clean)
        >>> evl.run()
        clean exit
        >>> evl.remove_watch_file(handle)
        True
        >>> handle = evl.alarm(0, exit_error)
        >>> evl.run()
        Traceback (most recent call last):
           ...
        ZeroDivisionError: integer division or modulo by zero
        >>> handle = evl.watch_file(rd, exit_error)
        >>> evl.run()
        Traceback (most recent call last):
           ...
        ZeroDivisionError: integer division or modulo by zero
        """

    def _loop(self):
        """
        A single iteration of the event loop
        """
        fds = self._watch_files.keys()
        if self._alarms or self._did_something:
            if self._alarms:
                tm = self._alarms[0][0]
                timeout = max(0, tm - time.time())
            if self._did_something and (not self._alarms or 
                    (self._alarms and timeout > 0)):
                timeout = 0
                tm = 'idle'
            ready, w, err = select.select(fds, [], fds, timeout)
        else:
            tm = None
            ready, w, err = select.select(fds, [], fds)

        if not ready:
            if tm == 'idle':
                self._entering_idle()
                self._did_something = False
            elif tm is not None:
                # must have been a timeout
                tm, alarm_callback = self._alarms.pop(0)
                alarm_callback()
                self._did_something = True

        for fd in ready:
            self._watch_files[fd]()
            self._did_something = True


if not PYTHON3:
    class GLibEventLoop(object):
        """
        Event loop based on gobject.MainLoop
        """

        def __init__(self):
            import gobject
            self.gobject = gobject
            self._alarms = []
            self._watch_files = {}
            self._idle_handle = 0
            self._glib_idle_enabled = False # have we called glib.idle_add?
            self._idle_callbacks = {}
            self._loop = self.gobject.MainLoop()
            self._exc_info = None
            self._enable_glib_idle()

        def _test_event_loop(self):
            """
            >>> import os
            >>> rd, wr = os.pipe()
            >>> evl = GLibEventLoop()
            >>> def step1():
            ...     print "writing"
            ...     os.write(wr, "hi")
            >>> def step2():
            ...     print os.read(rd, 2)
            ...     raise ExitMainLoop
            >>> handle = evl.alarm(0, step1)
            >>> handle = evl.watch_file(rd, step2)
            >>> evl.run()
            writing
            hi
            """

        def alarm(self, seconds, callback):
            """
            Call callback() given time from from now.  No parameters are
            passed to callback.

            Returns a handle that may be passed to remove_alarm()

            seconds -- floating point time to wait before calling callback
            callback -- function to call from event loop
            """
            @self.handle_exit
            def ret_false():
                callback()
                self._enable_glib_idle()
                return False
            fd = self.gobject.timeout_add(int(seconds*1000), ret_false)
            self._alarms.append(fd)
            return (fd, callback)

        def remove_alarm(self, handle):
            """
            Remove an alarm.

            Returns True if the alarm exists, False otherwise
            """
            try:
                self._alarms.remove(handle[0])
                self.gobject.source_remove(handle[0])
                return True
            except ValueError:
                return False

        def _test_remove_alarm(self):
            """
            >>> evl = GLibEventLoop()
            >>> handle = evl.alarm(50, lambda: None)
            >>> evl.remove_alarm(handle)
            True
            >>> evl.remove_alarm(handle)
            False
            """

        def watch_file(self, fd, callback):
            """
            Call callback() when fd has some data to read.  No parameters
            are passed to callback.

            Returns a handle that may be passed to remove_watch_file()

            fd -- file descriptor to watch for input
            callback -- function to call when input is available
            """
            @self.handle_exit
            def io_callback(source, cb_condition):
                callback()
                self._enable_glib_idle()
                return True
            self._watch_files[fd] = \
                 self.gobject.io_add_watch(fd,self.gobject.IO_IN,io_callback)
            return fd

        def remove_watch_file(self, handle):
            """
            Remove an input file.

            Returns True if the input file exists, False otherwise
            """
            if handle in self._watch_files:
                self.gobject.source_remove(self._watch_files[handle])
                del self._watch_files[handle]
                return True
            return False

        def _test_remove_watch_file(self):
            """
            >>> evl = GLibEventLoop()
            >>> handle = evl.watch_file(1, lambda: None)
            >>> evl.remove_watch_file(handle)
            True
            >>> evl.remove_watch_file(handle)
            False
            """

        def enter_idle(self, callback):
            """
            Add a callback for entering idle.

            Returns a handle that may be passed to remove_enter_idle()
            """
            self._idle_handle += 1
            self._idle_callbacks[self._idle_handle] = callback
            return self._idle_handle

        def _enable_glib_idle(self):
            if self._glib_idle_enabled:
                return
            self.gobject.idle_add(self._glib_idle_callback)
            self._glib_idle_enabled = True

        def _glib_idle_callback(self):
            for callback in self._idle_callbacks.values():
                callback()
            self._glib_idle_enabled = False
            return False # ask glib not to call again (or we would be called

        def remove_enter_idle(self, handle):
            """
            Remove an idle callback.

            Returns True if the handle was removed.
            """
            try:
                del self._idle_callbacks[handle]
            except KeyError:
                return False
            return True


        def run(self):
            """
            Start the event loop.  Exit the loop when any callback raises
            an exception.  If ExitMainLoop is raised, exit cleanly.
            """
            try:
                self._loop.run()
            finally:
                if self._loop.is_running():
                    self._loop.quit()
            if self._exc_info:
                # An exception caused us to exit, raise it now
                exc_info = self._exc_info
                self._exc_info = None
                raise exc_info[0], exc_info[1], exc_info[2]

        def _test_run(self):
            """
            >>> import os
            >>> rd, wr = os.pipe()
            >>> os.write(wr, "data") # something to read from rd
            4
            >>> evl = GLibEventLoop()
            >>> def say_hello():
            ...     print "hello"
            >>> def say_waiting():
            ...     print "waiting"
            >>> def exit_clean():
            ...     print "clean exit"
            ...     raise ExitMainLoop
            >>> def exit_error():
            ...     1/0
            >>> handle = evl.alarm(0.01, exit_clean)
            >>> handle = evl.alarm(0.005, say_hello)
            >>> evl.enter_idle(say_waiting)
            1
            >>> evl.run()
            waiting
            hello
            waiting
            clean exit
            >>> handle = evl.watch_file(rd, exit_clean)
            >>> evl.run()
            clean exit
            >>> evl.remove_watch_file(handle)
            True
            >>> handle = evl.alarm(0, exit_error)
            >>> evl.run()
            Traceback (most recent call last):
               ...
            ZeroDivisionError: integer division or modulo by zero
            >>> handle = evl.watch_file(rd, exit_error)
            >>> evl.run()
            Traceback (most recent call last):
               ...
            ZeroDivisionError: integer division or modulo by zero
            """

        def handle_exit(self,f):
            """
            Decorator that cleanly exits the :class:`GLibEventLoop` if
            :exc:`ExitMainLoop` is thrown inside of the wrapped function. Store the
            exception info if some other exception occurs, it will be reraised after
            the loop quits.

            *f* -- function to be wrapped
            """
            def wrapper(*args,**kargs):
                try:
                    return f(*args,**kargs)
                except ExitMainLoop:
                    self._loop.quit()
                except:
                    import sys
                    self._exc_info = sys.exc_info()
                    if self._loop.is_running():
                        self._loop.quit()
                return False
            return wrapper


    try:
        from twisted.internet.abstract import FileDescriptor
    except ImportError:
        FileDescriptor = object

    class TwistedInputDescriptor(FileDescriptor):
        def __init__(self, reactor, fd, cb):
            self._fileno = fd
            self.cb = cb
            FileDescriptor.__init__(self, reactor)

        def fileno(self):
            return self._fileno

        def doRead(self):
            return self.cb()



    class TwistedEventLoop(object):
        """
        Event loop based on Twisted_
        """
        _idle_emulation_delay = 1.0/256 # a short time (in seconds)

        def __init__(self, reactor=None, manage_reactor=True):
            """
            :param reactor: reactor to use
            :type reactor: :class:`twisted.internet.reactor`.
            :param: manage_reactor: `True` if you want this event loop to run
                                    and stop the reactor.
            :type manage_reactor: boolean

            .. WARNING::
               Twisted's reactor doesn't like to be stopped and run again.  If you
               need to stop and run your :class:`MainLoop`, consider setting
               ``manage_reactor=False`` and take care of running/stopping the reactor
               at the beginning/ending of your program yourself.

            .. _Twisted: http://twistedmatrix.com/trac/
            """
            if reactor is None:
                import twisted.internet.reactor
                reactor = twisted.internet.reactor
            self.reactor = reactor
            self._alarms = []
            self._watch_files = {}
            self._idle_handle = 0
            self._twisted_idle_enabled = False
            self._idle_callbacks = {}
            self._exc_info = None
            self.manage_reactor = manage_reactor
            self._enable_twisted_idle()

        def alarm(self, seconds, callback):
            """
            Call callback() given time from from now.  No parameters are
            passed to callback.

            Returns a handle that may be passed to remove_alarm()

            seconds -- floating point time to wait before calling callback
            callback -- function to call from event loop
            """
            handle = self.reactor.callLater(seconds, self.handle_exit(callback))
            return handle

        def remove_alarm(self, handle):
            """
            Remove an alarm.

            Returns True if the alarm exists, False otherwise
            """
            from twisted.internet.error import AlreadyCancelled, AlreadyCalled
            try:
                handle.cancel()
                return True
            except AlreadyCancelled:
                return False
            except AlreadyCalled:
                return False

        def _test_remove_alarm(self):
            """
            >>> evl = TwistedEventLoop()
            >>> handle = evl.alarm(50, lambda: None)
            >>> evl.remove_alarm(handle)
            True
            >>> evl.remove_alarm(handle)
            False
            """

        def watch_file(self, fd, callback):
            """
            Call callback() when fd has some data to read.  No parameters
            are passed to callback.

            Returns a handle that may be passed to remove_watch_file()

            fd -- file descriptor to watch for input
            callback -- function to call when input is available
            """
            ind = TwistedInputDescriptor(self.reactor, fd,
                self.handle_exit(callback))
            self._watch_files[fd] = ind
            self.reactor.addReader(ind)
            return fd

        def remove_watch_file(self, handle):
            """
            Remove an input file.

            Returns True if the input file exists, False otherwise
            """
            if handle in self._watch_files:
                self.reactor.removeReader(self._watch_files[handle])
                del self._watch_files[handle]
                return True
            return False

        def _test_remove_watch_file(self):
            """
            >>> evl = TwistedEventLoop()
            >>> handle = evl.watch_file(1, lambda: None)
            >>> evl.remove_watch_file(handle)
            True
            >>> evl.remove_watch_file(handle)
            False
            """

        def enter_idle(self, callback):
            """
            Add a callback for entering idle.

            Returns a handle that may be passed to remove_enter_idle()
            """
            self._idle_handle += 1
            self._idle_callbacks[self._idle_handle] = callback
            return self._idle_handle

        def _enable_twisted_idle(self):
            """
            Twisted's reactors don't have an idle or enter-idle callback
            so the best we can do for now is to set a timer event in a very
            short time to approximate an enter-idle callback.

            .. WARNING::
               This will perform worse than the other event loops until we can find a
               fix or workaround
            """
            if self._twisted_idle_enabled:
                return
            self.reactor.callLater(self._idle_emulation_delay,
                self.handle_exit(self._twisted_idle_callback, enable_idle=False))
            self._twisted_idle_enabled = True

        def _twisted_idle_callback(self):
            for callback in self._idle_callbacks.values():
                callback()
            self._twisted_idle_enabled = False

        def remove_enter_idle(self, handle):
            """
            Remove an idle callback.

            Returns True if the handle was removed.
            """
            try:
                del self._idle_callbacks[handle]
            except KeyError:
                return False
            return True

        def run(self):
            """
            Start the event loop.  Exit the loop when any callback raises
            an exception.  If ExitMainLoop is raised, exit cleanly.
            """
            if not self.manage_reactor:
                return
            self.reactor.run()
            if self._exc_info:
                # An exception caused us to exit, raise it now
                exc_info = self._exc_info
                self._exc_info = None
                raise exc_info[0], exc_info[1], exc_info[2]

        def _test_run(self):
            """
            >>> import os
            >>> rd, wr = os.pipe()
            >>> os.write(wr, "data") # something to read from rd
            4
            >>> evl = TwistedEventLoop()
            >>> def say_hello_data():
            ...     print "hello data"
            ...     os.read(rd, 4)
            >>> def say_waiting():
            ...     print "waiting"
            >>> def say_hello():
            ...     print "hello"
            >>> handle = evl.watch_file(rd, say_hello_data)
            >>> def say_being_twisted():
            ...     print "oh I'm messed up"
            ...     raise ExitMainLoop
            >>> handle = evl.alarm(0.0625, say_being_twisted)
            >>> handle = evl.alarm(0.03125, say_hello)
            >>> evl.enter_idle(say_waiting)
            1
            >>> evl.run()
            hello data
            waiting
            hello
            waiting
            oh I'm messed up
            """

        def handle_exit(self, f, enable_idle=True):
            """
            Decorator that cleanly exits the :class:`TwistedEventLoop` if
            :class:`ExitMainLoop` is thrown inside of the wrapped function. Store the
            exception info if some other exception occurs, it will be reraised after
            the loop quits.

            *f* -- function to be wrapped
            """
            def wrapper(*args,**kargs):
                rval = None
                try:
                    rval = f(*args,**kargs)
                except ExitMainLoop:
                    if self.manage_reactor:
                        self.reactor.stop()
                except:
                    import sys
                    print sys.exc_info()
                    self._exc_info = sys.exc_info()
                    if self.manage_reactor:
                        self.reactor.crash()
                if enable_idle:
                    self._enable_twisted_idle()
                return rval
            return wrapper



def _refl(name, rval=None, exit=False):
    """
    This function is used to test the main loop classes.

    >>> scr = _refl("screen")
    >>> scr.function("argument")
    screen.function('argument')
    >>> scr.callme(when="now")
    screen.callme(when='now')
    >>> scr.want_something_rval = 42
    >>> x = scr.want_something()
    screen.want_something()
    >>> x
    42

    """
    class Reflect(object):
        def __init__(self, name, rval=None):
            self._name = name
            self._rval = rval
        def __call__(self, *argl, **argd):
            args = ", ".join([repr(a) for a in argl])
            if args and argd:
                args = args + ", "
            args = args + ", ".join([k+"="+repr(v) for k,v in argd.items()])
            print self._name+"("+args+")"
            if exit:
                raise ExitMainLoop()
            return self._rval
        def __getattr__(self, attr):
            if attr.endswith("_rval"):
                raise AttributeError()
            #print self._name+"."+attr
            if hasattr(self, attr+"_rval"):
                return Reflect(self._name+"."+attr, getattr(self, attr+"_rval"))
            return Reflect(self._name+"."+attr)
    return Reflect(name)

def _test():
    import doctest
    doctest.testmod()

if __name__=='__main__':
    _test()

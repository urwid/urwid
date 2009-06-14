#!/usr/bin/python
#
# Urwid main loop code
#    Copyright (C) 2004-2009  Ian Ward
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

from util import *
from command_map import command_map


class ExitMainLoop(Exception):
    pass

class MainLoop(object):
    def __init__(self, widget, palette=[], screen=None, 
        handle_mouse=True, input_filter=None, unhandled_input=None,
        event_loop=None):
        """
        Simple main loop implementation with a single screen.

        widget -- topmost widget used for painting the screen, 
            stored as self.widget, may be modified
        palette -- initial palette for screen
        screen -- screen object or None to use raw_display.Screen,
            stored as self.screen
        handle_mouse -- True to process mouse events, passed to
            self.screen
        input_filter -- a function to filter input before sending
            it to self.widget (return None to remove input), called
            from self.input_filter
        unhandled_input -- a function called when input is not
            handled by self.widget, called from self.unhandled_input
        event_loop -- event loop object or None to use
            SelectEventLoop, stored as self.event_loop
        """
        self.widget = widget
        self.handle_mouse = handle_mouse
        
        if not screen:
            import raw_display
            screen = raw_display.Screen()

        if palette:
            screen.register_palette(palette)

        self.screen = screen
        self.screen_size = None

        self._unhandled_input = unhandled_input
        self._input_filter = input_filter

        if not event_loop:
            event_loop = SelectEventLoop()
        self.event_loop = event_loop

        self._input_timeout = None


    def set_alarm_in(self, sec, callback, user_data=None):
        """
        Schedule an alarm in sec seconds that will call
        callback(main_loop, user_data) from the within the run()
        function.

        sec -- floating point seconds until alarm
        callback -- callback(main_loop, user_data) callback function
        user_data -- object to pass to callback
        """
        def cb():
            callback(self, user_data)
            self.draw_screen()
        return self.event_loop.alarm(sec, cb)

    def set_alarm_at(self, tm, callback, user_data=None):
        """
        Schedule at tm time that will call 
        callback(main_loop, user_data) from the within the run()
        function.

        Returns a handle that may be passed to remove_alarm()

        tm -- floating point local time of alarm
        callback -- callback(main_loop, user_data) callback function
        user_data -- object to pass to callback
        """
        def cb():
            callback(self, user_data)
            self.draw_screen()
        return self.event_loop.alarm(tm - time.time(), cb)

    def remove_alarm(self, handle):
        """
        Remove an alarm. 
        
        Return True if the handle was found, False otherwise.
        """
        return self.event_loop.remove_alarm(handle)


    
    def run(self):
        """
        Start the main loop handling input events and updating 
        the screen.  The loop will continue until an ExitMainLoop 
        exception is raised.  
        
        This function will call screen.run_wrapper() if screen.start() 
        has not already been called.

        >>> w = _refl("widget")   # _refl prints out function calls
        >>> w.render_rval = "fake canvas"  # *_rval is used for return values
        >>> scr = _refl("screen")
        >>> scr.get_input_descriptors_rval = [42]
        >>> scr.get_cols_rows_rval = (20, 10)
        >>> scr.started = True
        >>> evl = _refl("event_loop")
        >>> ml = MainLoop(w, [], scr, event_loop=evl)
        >>> ml.run()    # doctest:+ELLIPSIS
        screen.get_cols_rows()
        widget.render((20, 10), focus=True)
        screen.draw_screen((20, 10), 'fake canvas')
        screen.get_input_descriptors()
        event_loop.watch_file(42, <bound method ...>)
        event_loop.run()
        >>> scr.started = False
        >>> ml.run()    # doctest:+ELLIPSIS
        screen.run_wrapper(<bound method ...>)
        """
        try:
            if self.screen.started:
                self._run()
            else:
                self.screen.run_wrapper(self._run)
        except ExitMainLoop:
            pass
    
    def _run(self):
        self.draw_screen()

        # insert our input descriptors
        fds = self.screen.get_input_descriptors()
        for fd in fds:
            self.event_loop.watch_file(fd, self._update)

        self.event_loop.run()

    def _update(self, timeout=False):
        """
        >>> w = _refl("widget")
        >>> w.render_rval = "fake canvas"
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
        widget.keypress((15, 5), 'y')
        widget.render((15, 5), focus=True)
        screen.draw_screen((15, 5), 'fake canvas')
        >>> scr.get_input_nonblocking_rval = None, [("mouse press", 1, 5, 4)
        ... ], []
        >>> ml._update()
        screen.get_input_nonblocking()
        widget.mouse_event((15, 5), 'mouse press', 1, 5, 4, focus=True)
        widget.render((15, 5), focus=True)
        screen.draw_screen((15, 5), 'fake canvas')
        """
        if self._input_timeout is not None and not timeout:
            # cancel the timeout, something else triggered the update
            self.remove_alarm(self._input_timeout)
        self._input_timeout = None

        max_wait, keys, raw = self.screen.get_input_nonblocking()
        
        if max_wait is not None:
            # if get_input_nonblocking wants to be called back
            # make sure it happens with an alarm
            self._input_timeout = self.set_alarm_in(max_wait, self._update, 
                user_data=True) # call with timeout=True

        if keys:
            self.process_input(keys)
            if 'window resize' in keys:
                self.screen_size = None

        self.draw_screen()


    def process_input(self, keys):
        """
        This function will pass keyboard input and mouse events
        to self.widget.  This function is called automatically
        from the run() method when there is input, but may also be
        called to simulate input from the user.

        keys -- list of input returned from self.screen.get_input()
        
        >>> w = _refl("widget")
        >>> scr = _refl("screen")
        >>> scr.get_cols_rows_rval = (10, 5)
        >>> ml = MainLoop(w, [], scr)
        >>> ml.process_input(['enter', ('mouse drag', 1, 14, 20)])
        screen.get_cols_rows()
        widget.keypress((10, 5), 'enter')
        widget.mouse_event((10, 5), 'mouse drag', 1, 14, 20, focus=True)
        """
        if not self.screen_size:
            self.screen_size = self.screen.get_cols_rows()

        for k in keys:
            k = self.input_filter(k)
            if is_mouse_event(k):
                event, button, col, row = k
                if self.widget.mouse_event(self.screen_size, 
                    event, button, col, row, focus=True ):
                    k = None
            else:
                k = self.widget.keypress(self.screen_size, k)
            if k and command_map[k] == 'redraw screen':
                self.screen.clear()
            elif k:
                self.unhandled_input(k)

    def input_filter(self, input):
        """
        This function is passed each input event and calls the
        input_filter function passed to the constructor.  If that
        function returns None the input will not be passed to the
        widgets to handle.

        input -- keyboard or mouse input
        """
        if self._input_filter:
            return self._input_filter(input)
        return input

    def unhandled_input(self, input):
        """
        This function is called with any input that was not handled
        by the widgets, and calls the unhandled_input function passed
        to the constructor.

        input -- keyboard or mouse input
        """
        if self._unhandled_input:
            return self._unhandled_input(input)

    def draw_screen(self):
        """
        Renter the widgets and paint the screen.  This function is
        called automatically from run() but may be called additional 
        times if repainting is required without also processing input.
        """
        if not self.screen_size:
            self.screen_size = self.screen.get_cols_rows()

        canvas = self.widget.render(self.screen_size, focus=True)
        self.screen.draw_screen(self.screen_size, canvas)



        


class SelectEventLoop(object):
    def __init__(self):
        """
        Event loop based on select.select()

        >>> import os
        >>> rd, wr = os.pipe()
        >>> evl = SelectEventLoop()
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
        self._alarms = []
        self._watch_files = {}

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

        >>> evl = SelectEventLoop()
        >>> handle = evl.alarm(50, lambda: None)
        >>> evl.remove_alarm(handle)
        True
        >>> evl.remove_alarm(handle)
        False
        """
        try:
            self._alarms.remove(handle)
            heapq.heapify(self._alarms)
            return True
        except ValueError:
            return False

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

        >>> evl = SelectEventLoop()
        >>> handle = evl.watch_file(5, lambda: None)
        >>> evl.remove_watch_file(handle)
        True
        >>> evl.remove_watch_file(handle)
        False
        """
        if handle in self._watch_files:
            del self._watch_files[handle]
            return True
        return False

    def run(self):
        """
        Start the event loop.  Exit the loop when any callback raises
        an exception.  If ExitMainLoop is raised, exit cleanly.

        >>> import os
        >>> rd, wr = os.pipe()
        >>> os.write(wr, "data") # something to read from rd
        4
        >>> evl = SelectEventLoop()
        >>> def say_hello():
        ...     print "hello"
        >>> def exit_clean():
        ...     print "clean exit"
        ...     raise ExitMainLoop
        >>> def exit_error():
        ...     1/0
        >>> handle = evl.alarm(0.0625, exit_clean)
        >>> handle = evl.alarm(0, say_hello)
        >>> evl.run()
        hello
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
        try:
            while True:
                try:
                    self._loop()
                except select.error, e:
                    if e.args[0] != 4:
                        # not just something we need to retry
                        raise
        except ExitMainLoop:
            pass
        

    def _loop(self):
        fds = self._watch_files.keys()
        if self._alarms:
            tm = self._alarms[0][0]
            timeout = max(0, tm - time.time())
            ready, w, err = select.select(fds, [], fds, timeout)
        else:
            tm = None
            ready, w, err = select.select(fds, [], fds)

        if not ready and tm is not None:
            # must have been a timeout
            tm, alarm_callback = self._alarms.pop(0)
            alarm_callback()

        for fd in ready:
            self._watch_files[fd]()







def twisted_main_loop(topmost_widget, palette=[], screen=None,
               handle_mouse=True, input_filter=None, unhandled_input=None,
               handle_reactor=True):
    """
    A version of generic_main_loop that uses the twisted library.
    Most parameters are the same as generic_main_loop.

    handle_reactor - if False, rather than looping the function simply 
                     returns a twisted Deferred that will trigger when 
                     the UI shuts down
    """
    from twisted.internet import reactor
    from twisted.internet.defer import Deferred
    from twisted.python.failure import Failure
    from twisted.internet.abstract import FileDescriptor
    
    class InputDescriptor(FileDescriptor):
        def __init__(self, fd, cb):
            self._fileno = fd
            self.cb = cb
            FileDescriptor.__init__(self, reactor)

        def fileno(self):
            return self._fileno

        def doRead(self):
            return self.cb()

    class TwistedLoopManager(object):
        def __init__(self, screen, topmost_widget, input_filter, unhandled_input,
                           need_stop, handle_reactor):
            self.screen = screen
            self.topmost_widget = topmost_widget
            self.failure = None
            self.handle_reactor = handle_reactor
            if input_filter:
                self.input_filter = input_filter
            if unhandled_input:
                self.unhandled_input = unhandled_input
            self.need_stop = need_stop

        def input_filter(self, k):
            return k

        def unhandled_input(self, k):
            pass

        def stop(self, failure=None):
            if self.need_stop:
                self.screen.stop()
                self.need_stop = False
            self.running = False
            if failure:
                self.d.errback(failure)
            else:
                self.d.callback(True)
            if self.handle_reactor:
                reactor.stop()
                self.handle_reactor = False
            elif self.triggerid:
                self.removeSystemEventTrigger(self.triggerid)
                self.triggerid = None

        def refresh(self):
            if not self.running:
                return
            try:
                canvas = self.topmost_widget.render(self.size, focus=True)
                self.screen.draw_screen(self.size, canvas)
            except ExitMainLoop:
                self.stop()
            except:
                self.stop(Failure())

        def onShutdown(self):
            if self.need_stop:
                self.screen.stop()
                self.need_stop = False
            if self.running:
                self.stop()

        def inputCallback(self):
            if self.running:
                timeout, events, raw = self.screen.get_input_nonblocking()
                if events:
                    for event in events:
                        self.onInput(event)
            self.refresh()

        def run(self):
            self.d = Deferred()
            self.running = True
            self.triggerid = reactor.addSystemEventTrigger('before', 'shutdown', self.onShutdown)

            self.size = self.screen.get_cols_rows()
            self.refresh()
            for desc in self.screen.get_input_descriptors():
                id = InputDescriptor(desc, self.inputCallback)
                reactor.addReader(id)

            return self.d

        def onInput(self, event):
            if not self.running:
                return
            try:
                if event == 'window resize':
                    self.size = self.screen.get_cols_rows()
                event = self.input_filter(event)
                if is_mouse_event(event):
                    if self.topmost_widget.mouse_event(self.size, focus=True, *event):
                        event = None
                else:
                    event = self.topmost_widget.keypress(self.size, event)
                if event:
                    self.unhandled_input(event)
            except ExitMainLoop:
                self.stop()
            except:
                self.stop(Failure())

    if not screen:
        import raw_display
        screen = raw_display.Screen()

    if palette:
        screen.register_palette(palette)

    needstop = False
    handleStartStop = not screen.started
    if handleStartStop:
        screen.start()
        needstop = True

    mgr = TwistedLoopManager(screen, topmost_widget, input_filter,
                             unhandled_input, needstop, handle_reactor)

    if handle_mouse:
        screen.set_mouse_tracking()

    d = mgr.run()
    if handle_reactor:
        d.addErrback(lambda fail: fail.printTraceback())
        reactor.run()
    else:
        return d


class GLibMainLoop(object):
    def __init__(self, widget, palette=[], screen=None, 
        handle_mouse=True):
        """
        Initialize a screen object and palette to be used for
        a generic main loop.

        widget -- topmost widget used for painting the screen,
            stored as self.widget, may be modified
        palette -- initial palette for screen
        screen -- screen object or None to use raw_display.Screen,
            stored as self.screen
        handle_mouse -- True to process mouse events
        """
        import gobject
        self.gobject = gobject
        
        self.widget = widget
        self.handle_mouse = handle_mouse
        
        if not screen:
            import raw_display
            screen = raw_display.Screen()

        if palette:
            screen.register_palette(palette)

        self.screen = screen
        self.screen_size = None

        self.update_tag = None
        
        self._timeouts = []

        self._loop = gobject.MainLoop()
        self._exc_info = None

    def _set_screen_alarm(self,sec):
        def ret_false():
            self._run()
            return False
        return self.gobject.timeout_add(sec*1000,ret_false)

    def set_alarm_in(self, sec, callback, user_data=None):
        """
        Schedule an alarm in sec seconds that will call
        callback(main_loop, user_data) as a timeout in the glib mainloop
        in sec seconds.

        This returns the file descriptor that glib gives us.

        sec -- floating point seconds until alarm
        callback -- callback(main_loop, user_data) callback function
        user_data -- object to pass to callback
        """
        def ret_false(callback):
            callback(self,user_data)
            return False
        tag = self.gobject.timeout_add(sec*1000, ret_false)
        self._timeouts.append(tag)
        return tag

    def set_alarm_at(self, tm, callback, user_data=None):
        """
        Schedule an alarm at sec seconds that will call
        callback(main_loop, user_data) as a timeout in the glib mainloop.
        
        This returns the file descriptor that glib gives us.

        tm -- floating point local time of alarm
        callback -- callback(main_loop, user_data) callback function
        user_data -- object to pass to callback
        """
        return self.set_alarm_in(sec-time.time(),callback,user_data)

    def set_timeout(self, tm, callback, user_data=None):
        """
        Sechedule a call to callback(main_loop,user_data) to occur in int
        seconds, repeating every tm seconds until it returns False.  This 
        returns the file descriptor that glib gives us.

        tm -- floating point seconds until timeout is processed
        callback -- callback(main_loop, user_data) callback function
        user_data -- object to pass to callback
        """
        tag = self.gobject.timeout_add(sec*1000, callback,user_data)
        self._timeouts.append(tag)
        return tag

    def remove_timeout(self,tag):
        """
        Remove the timeout (or alarm or whatever) represented by the tag value.

        Calls gobject.source_remove(tag) and returns the tag if we know about
        the tag in question.  Else, return None.

        tag -- tag of the timeout/idle function/io watch to remove
        """
        if tag in _timeouts:
            return self.gobject.source_remove(tag)
        else:
            return None

    def run(self):
        """
        Start a glib main loop handling input events and updating 
        the screen.  The loop will continue until an ExitMainLoop 
        (or some other) exception is raised.  
        
        This function will call screen.run_wrapper() if screen.start() 
        has not already been called.
        """
        if self.handle_mouse:
            self.screen.set_mouse_tracking()

        # Set up the UI, this starts setting up other timeouts/alarms for
        # the input
        try:
            if not self.screen.started:
                self.screen.run_wrapper(self._run)
            else:
                self._run()
        finally:
            if self._loop.is_running():
                self._loop.quit()
        if self._exc_info:
            # An exception caused us to exit, raise it now
            exc_info = self._exc_info
            self._exc_info = None
            raise exc_info[0], exc_info[1], exc_info[2]

        
    def _run(self):
        self.draw_screen()

        # Account for file descriptors
        fds = self.screen.get_input_descriptors()
        for fd in fds:
            self.gobject.io_add_watch(fd, self.gobject.IO_IN, self._call_update)

        self._loop.run()

    def _call_update(self, source, cb_condition):
        try:
            self._update()
        except ExitMainLoop:
            if self._loop.is_running():
                self._loop.quit()
        except:
            # save our exception so it can be re-raised after the
            # loop stops (if we do it here it will just disappear)
            import sys
            self._exc_info = sys.exc_info()
            if self._loop.is_running():
                self._loop.quit()
        return True

    def _update(self):
        max_wait, keys, raw = self.screen.get_input_nonblocking()

        # Resolve any "alarms" in the waiting
        if self.update_tag != None:
            self.remove_timeout(self.update_tag)
        if max_wait is not None:
            self.update_tag = self._set_screen_alarm(max_wait)
        
        if keys:
            self.process_input(keys)
            
            if 'window resize' in keys:
                self.screen_size = None

        self.draw_screen()

    def process_input(self, keys):
        """
        This function will pass keyboard input and mouse events
        to self.widget.  This function is called automatically
        from the run() method when there is input, but may also be
        called to simulate input from the user.

        keys -- list of input returned from self.screen.get_input()
        """
        for k in keys:
            k = self.input_filter(k)
            if is_mouse_event(k):
                event, button, col, row = k
                if self.widget.mouse_event(self.screen_size, 
                    event, button, col, row, focus=True ):
                    k = None
            else:
                k = self.widget.keypress(self.screen_size, k)
            if k:
                k = self.unhandled_input(k)
            if k and command_map[k] == 'redraw screen':
                self.screen.clear()

    def input_filter(self, input):
        """
        This function is passed each input event and returns the
        input or None to not pass this input to the widgets.

        input -- keyboard or mouse input
        """
        return input

    def unhandled_input(self, input):
        """
        This function is called with any input that was not handled
        by the widgets.

        input -- keyboard or mouse input
        """
        pass

    def draw_screen(self):
        """
        Renter the widgets and paint the screen.  This function is
        called automatically from run() but may be called additional 
        times if repainting is required without also processing input.
        """
        if not self.screen_size:
            self.screen_size = self.screen.get_cols_rows()
        canvas = self.widget.render(self.screen_size, focus=True)
        self.screen.draw_screen(self.screen_size, canvas)


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

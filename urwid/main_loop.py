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
        Simple main loop implementation.

        widget -- topmost widget used for painting the screen, 
            stored as self.widget, may be modified
        palette -- initial palette for screen
        screen -- screen object or None to use raw_display.Screen,
            stored as self.screen
        handle_mouse -- True to process mouse events, passed to
            self.screen
        input_filter -- a function to filter input before sending
            it to self.widget, called from self.input_filter
        unhandled_input -- a function called when input is not
            handled by self.widget, called from self.unhandled_input
        event_loop -- if screen supports external an event loop it
            may be given here, or leave as None to use 
            SelectEventLoop, stored as self.event_loop

        This is a standard main loop implementation with a single
        screen. 
        
        The widget passed must be a box widget.

        raw_display.Screen is the only screen type that currently
        supports external event loops.  Other screen types include
        curses_display.Screen, web_display.Screen and
        html_fragment.HtmlGenerator.
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

        if not hasattr(screen, 'get_input_descriptors'
                ) and event_loop is not None:
            raise NotImplementedError("screen object passed "
                "%r does not support external event loops" % (screen,))
        if event_loop is None:
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
        screen.set_mouse_tracking()
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
        if self.handle_mouse:
            self.screen.set_mouse_tracking()

        if not hasattr(self.screen, 'get_input_descriptors'):
            return self._run_screen_event_loop()

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
        >>> w.selectable_rval = True
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

        self.draw_screen()

    def _run_screen_event_loop(self):
        """
        This method is used when the screen does not support using
        external event loops.

        The alarms stored in the SelectEventLoop in self.event_loop 
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
                tm, callback, user_data = next_alarm
                callback(self, user_data)
                
                if self._alarms:
                    next_alarm = heapq.heappop(self.event_loop._alarms)
                else:
                    next_alarm = None
            
            if 'window resize' in keys:
                self.screen_size = None

    def process_input(self, keys):
        """
        This function will pass keyboard input and mouse events
        to self.widget.  This function is called automatically
        from the run() method when there is input, but may also be
        called to simulate input from the user.

        keys -- list of input returned from self.screen.get_input()
        
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
        """
        if not self.screen_size:
            self.screen_size = self.screen.get_cols_rows()

        for k in keys:
            if is_mouse_event(k):
                event, button, col, row = k
                if self.widget.mouse_event(self.screen_size, 
                    event, button, col, row, focus=True ):
                    k = None
            elif self.widget.selectable():
                k = self.widget.keypress(self.screen_size, k)
            if k and command_map[k] == 'redraw screen':
                self.screen.clear()
            elif k:
                self.unhandled_input(k)

    def input_filter(self, keys, raw):
        """
        This function is passed each all the input events and raw
        keystroke values.  These values are passed to the
        input_filter function passed to the constructor.  That
        function must return a list of keys to be passed to the
        widgets to handle.  If no input_filter was defined this
        implementation will return all the input events.

        input -- keyboard or mouse input
        """
        if self._input_filter:
            return self._input_filter(keys, raw)
        return keys

    def unhandled_input(self, input):
        """
        This function is called with any input that was not handled
        by the widgets, and calls the unhandled_input function passed
        to the constructor.  If no unhandled_input was defined then
        the input will be ignored.

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


class GLibEventLoop(object):
    def __init__(self):
        """
        Event loop based on gobject.MainLoop

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
        import gobject
        self.gobject = gobject
        self._alarms = []
        self._watch_files = {}
        self._loop = self.gobject.MainLoop()
        self._exc_info = None

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
            return False
        fd = self.gobject.timeout_add(int(seconds*1000), ret_false)
        self._alarms.append(fd)
        return (fd, callback)

    def remove_alarm(self, handle):
        """
        Remove an alarm.

        Returns True if the alarm exists, False otherwise

        >>> evl = GLibEventLoop()
        >>> handle = evl.alarm(50, lambda: None)
        >>> evl.remove_alarm(handle)
        True
        >>> evl.remove_alarm(handle)
        False
        """
        try:
            self._alarms.remove(handle[0])
            self.gobject.source_remove(handle[0])
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
        @self.handle_exit
        def io_callback(source, cb_condition):
            callback()
            return True
        self._watch_files[fd] = \
             self.gobject.io_add_watch(fd,self.gobject.IO_IN,io_callback)
        return fd

    def remove_watch_file(self, handle):
        """
        Remove an input file.

        Returns True if the input file exists, False otherwise

        >>> evl = GLibEventLoop()
        >>> handle = evl.watch_file(1, lambda: None)
        >>> evl.remove_watch_file(handle)
        True
        >>> evl.remove_watch_file(handle)
        False
        """
        if handle in self._watch_files:
            self.gobject.source_remove(self._watch_files[handle])
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
        >>> evl = GLibEventLoop()
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
        context = self._loop.get_context()
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

    def handle_exit(self,f):
        """
        Decorator that cleanly exits the GLibEventLoop if ExitMainLoop is
        thrown inside of the wrapped function.  Store the exception info if 
        some other exception occurs, it will be reraised after the loop quits.
        f -- function to be wrapped

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
except:
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
    def __init__(self, reactor=None):
        """
        Event loop based on Twisted

        >>> import os
        >>> rd, wr = os.pipe()
        >>> evl = TwistedEventLoop()
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
        if reactor is None:
            import twisted.internet.reactor
            reactor = twisted.internet.reactor
        self.reactor = reactor
        self._alarms = []
        self._watch_files = {}
        self._exc_info = None

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

        >>> evl = TwistedEventLoop()
        >>> handle = evl.alarm(50, lambda: None)
        >>> evl.remove_alarm(handle)
        True
        >>> evl.remove_alarm(handle)
        False
        """
        from twisted.internet.error import AlreadyCancelled, AlreadyCalled
        try:
            handle.cancel()
            return True
        except AlreadyCancelled:
            return False
        except AlreadyCalled:
            return False

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

        >>> evl = TwistedEventLoop()
        >>> handle = evl.watch_file(1, lambda: None)
        >>> evl.remove_watch_file(handle)
        True
        >>> evl.remove_watch_file(handle)
        False
        """
        if handle in self._watch_files:
            self.reactor.removeReader(self._watch_files[handle])
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
        >>> evl = TwistedEventLoop()
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
        self.reactor.run()
        if self._exc_info:
            # An exception caused us to exit, raise it now
            exc_info = self._exc_info
            self._exc_info = None
            raise exc_info[0], exc_info[1], exc_info[2]

    def handle_exit(self,f):
        """
        Decorator that cleanly exits the TwistedEventLoop if ExitMainLoop is
        thrown inside of the wrapped function.  Store the exception info if 
        some other exception occurs, it will be reraised after the loop quits.
        f -- function to be wrapped

        """
        def wrapper(*args,**kargs):
            try:
                return f(*args,**kargs)
            except ExitMainLoop:
                self.reactor.crash()
            except:
                import sys
                print sys.exc_info()
                self._exc_info = sys.exc_info()
                self.reactor.crash()
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

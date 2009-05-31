#!/usr/bin/python
#
# Urwid main loop code
#    Copyright (C) 2004-2008  Ian Ward, Walter Mundt
#    Copyright (C) 2009       Andrew Psaltis
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


from util import *
from command_map import command_map

# These are overridden by whatever loop class is used.
def _handle_exceptions(exc):
    pass

def _quit_loop():
    pass

def wrap_exceptions(func):
    """
    Decorator function used to ensure that wrapped functions die properly
    when an exception is thrown.
    You may need to wrap some alarms/timeouts with this function to ensure
    that your program doesn't break your terminal upon failure, if you use the
    GLib or Twisted MainLoops.
    func -- function to be wrapped
    """
    def wrapper(*args, **kargs):
            try:
                return func(*args, **kargs)
            except ExitMainLoop:
                _quit_loop()
            except Exception as exc:
                _handle_exceptions(exc)

    wrapper.__name__ = func.__name__
    wrapper.__module__ = func.__module__
    wrapper.__dict__ = func.__dict__
    wrapper.__doc__ = func.__doc__
    return wrapper

class ExitMainLoop(Exception):
    pass


class GenericMainLoop(object):
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
        self.widget = widget
        self.handle_mouse = handle_mouse
        
        if not screen:
            import raw_display
            screen = raw_display.Screen()

        if palette:
            screen.register_palette(palette)

        self.screen = screen
        self.screen_size = None

        self._alarms = []
        self._timeouts = []

    def set_alarm_in(self, sec, callback, user_data=None):
        """
        Schedule an alarm in sec seconds that will call
        callback(main_loop, user_data) from the within the run()
        function.

        sec -- floating point seconds until alarm
        callback -- callback(main_loop, user_data) callback function
        user_data -- object to pass to callback
        """
        self.set_alarm_at(time.time() + sec, callback, user_data)

    def set_alarm_at(self, tm, callback, user_data=None):
        """
        Schedule at tm time that will call 
        callback(main_loop, user_data) from the within the run()
        function.

        tm -- floating point local time of alarm
        callback -- callback(main_loop, user_data) callback function
        user_data -- object to pass to callback
        """
        heapq.heappush(self._alarms, (tm, callback, user_data))

    def run(self):
        """
        Start a generic main loop handling input events and updating 
        the screen.  The loop will continue until an ExitMainLoop 
        exception is raised.  
        
        This function will call screen.run_wrapper() if screen.start() 
        has not already been called.
        """
        try:
            if self.screen.started:
                self._run()
            else:
                self.screen.run_wrapper(self._run)
        except ExitMainLoop:
            pass

    def _run(self):
        next_alarm = None
        if self.handle_mouse:
            self.screen.set_mouse_tracking()

        while True:
            self.draw_screen()

            if not next_alarm and self._alarms:
                next_alarm = heapq.heappop(self._alarms)

            keys = None
            while not keys:
                if next_alarm:
                    sec = max(0, next_alarm[0] - time.time())
                    self.screen.set_input_timeouts(sec)
                else:
                    self.screen.set_input_timeouts(None)
                keys = self.screen.get_input()
                if not keys and next_alarm: 
                    sec = next_alarm[0] - time.time()
                    if sec <= 0:
                        break
            
            if keys:
                self.process_input(keys)
            
            while next_alarm:
                sec = next_alarm[0] - time.time()
                if sec > 0:
                    break
                tm, callback, user_data = next_alarm
                callback(self, user_data)
                
                if self._alarms:
                    next_alarm = heapq.heappop(self._alarms)
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

        inout -- keyboard or mouse input
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



def generic_main_loop(topmost_widget, palette=[], screen=None,
    handle_mouse=True, input_filter=None, unhandled_input=None):
    """
    Initialize the palette and start a generic main loop handling
    input events and updating the screen.  The loop will continue
    until an ExitMainLoop exception is raised.  
    
    This function will call screen.run_wrapper() if screen.start() 
    has not already been called.

    topmost_widget -- the widget used to draw the screen and handle input
    palette -- a palette to pass to the screen object's register_palette()
    screen -- a screen object, if None raw_display.Screen will be used.
    handle_mouse -- True: attempt to handle mouse events
    input_filter -- a function that is passed each input event and
        may return a new event or None to remove that event from
        further processing
    unhandled_input -- a function that is passed input events
        that neither input_filter nor the widgets have handled
    """

    def run():
        if handle_mouse:
            screen.set_mouse_tracking()
        size = screen.get_cols_rows()
        while True:
            canvas = topmost_widget.render(size, focus=True)
            screen.draw_screen(size, canvas)
            keys = None
            while not keys:
                keys = screen.get_input()
            for k in keys:
                if input_filter:
                    k = input_filter(k)
                if is_mouse_event(k):
                    event, button, col, row = k
                    if topmost_widget.mouse_event(size, 
                        event, button, col, row, 
                        focus=True ):
                        k = None
                else:
                    k = topmost_widget.keypress(size, k)
                if k and unhandled_input:
                    k = unhandled_input(k)
                if k and command_map[k] == 'redraw screen':
                    screen.clear()
            
            if 'window resize' in keys:
                size = screen.get_cols_rows()
    
    if not screen:
        import raw_display
        screen = raw_display.Screen()

    if palette:
        screen.register_palette(palette)
    try:
        if screen.started:
            run()
        else:
            screen.run_wrapper(run)
    except ExitMainLoop:
        pass



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


# GLib main loop
try:
    import gobject
except:
    # Do nothing, the user should have pygobject if they want to use this.
    pass
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
        global _handle_exceptions,_quit_loop
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

        _handle_exceptions = self.handle_exceptions
        _quit_loop = self.quit_loop
        
        self._loop = gobject.MainLoop()

    def _set_screen_alarm(self,sec):
        def ret_false():
            self._run()
            return False
        return gobject.timeout_add(sec*1000,ret_false)

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
        tag = gobject.timeout_add(sec*1000, ret_false)
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
        tag = gobject.timeout_add(sec*1000, callback,user_data)
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
            return gobject.source_remove(tag)
        else:
            return None

    @wrap_exceptions
    def run(self):
        """
        Start a glib main loop handling input events and updating 
        the screen.  The loop will continue until an ExitMainLoop 
        (or some other) exception is raised.  
        """
        #This function will call screen.run_wrapper() if screen.start() 
        #has not already been called.
        #"""
        if self.handle_mouse:
            self.screen.set_mouse_tracking()
        #gobject.idle_add(self._run)

        # Set up the UI, this starts setting up other timeouts/alarms for
        # the input
        try:
            if not self.screen.started:
                self.screen.run_wrapper(self._prerun)
            else:
                self._prerun()
        except ExitMainLoop:
            screen._loop.quit()
            pass
        
    #@wrap_exceptions
    def _prerun(self):
        self._run()

        # Account for file descriptors
        fds = self.screen.get_input_descriptors()
        for fd in fds:
            gobject.io_add_watch(fd, gobject.IO_IN,self._call_run)

        self._loop.run()

    def _call_run(self,source,cb_condition):
        self._run()
        return True

    @wrap_exceptions
    def _run(self):
        input_data = self.screen.get_input_nonblocking()
        max_wait = input_data[0]
        keys = input_data[1]

        # Resolve any "alarms" in the waiting
        if self.update_tag != None:
            self.remove_timeout(self.update_tag)
        if max_wait == None:
            max_wait = 0.050

        self.update_tag = self._set_screen_alarm(max_wait)
        
        if keys:
            self.process_input(keys)
            
            if 'window resize' in keys:
                self.screen_size = None
        # If the "Quit" key is pressed, burn, baby, burn.
        if not self.screen.started:
            return False
        self.draw_screen()
        return True

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

    def handle_exceptions(self, exc):
        """
        Handle exceptions that are caught by the wrap_exceptions decorator.
        
        This method is called to handle all exceptions except 
        urwid.ExitMainLoop, which is simply used to trigger an exit.

        Unless overridden, this just kills the loop and then raises
        the exception.

        exc -- Exception to be processed.
        """
        #if type(exc) == type(ExitMainLoop):
        #    quit_loop()
        self.quit_loop()
        raise
    def quit_loop(self):
        """
        Quit the mainloop.  This is called by wrap_exceptions on ExitMainLoop
        and is used in the default handle_exceptions to quit the loop before
        raising the exception.
        """
        self.screen.stop()
        self._loop.quit()


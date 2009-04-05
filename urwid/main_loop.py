#!/usr/bin/python
#
# Urwid main loop code
#    Copyright (C) 2004-2008  Ian Ward, Walter Mundt
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


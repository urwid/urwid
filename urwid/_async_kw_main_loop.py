#!/usr/bin/python
#
# Urwid main loop code using Python-3.5 features (Trio, Curio, etc)
#    Copyright (C) 2018 Toshio Kuratomi
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

from __future__ import division, print_function

from .main_loop import EventLoop, ExitMainLoop


try:
    import trio
except Exception:
    trio = None


class TrioEventLoop(EventLoop):
    """
    Event loop based on the ``trio`` module.

    ``trio`` is an async library for Python 3.5 and later.
    """
    #_we_started_event_loop = False

    _idle_emulation_delay = 1.0/256  # a short time (in seconds)

    def __init__(self, nursery=None):
        self.nursery = nursery
        self._alarm_queue = []
        self._watcher_queue = []
        self._idle_queue = []

    async def _trio_alarm(self, seconds, callback, cancel):
        await trio.sleep(seconds)
        if cancel.is_set():
            return
        callback()

    def alarm(self, seconds, callback):
        """
        Call callback() a given time from now.  No parameters are
        passed to callback.

        Returns a handle that may be passed to remove_alarm()

        seconds -- time in seconds to wait before calling callback
        callback -- function to call from event loop
        """
        cancel = trio.Event()
        if self.nursery:
            self.nursery.start_soon(self._trio_alarm, seconds, callback, cancel)
        else:
            self._alarm_queue.append((seconds, callback, cancel))
        return cancel

    def remove_alarm(self, handle):
        """
        Remove an alarm.

        Returns True if the alarm exists, False otherwise
        """
        # Alarm has already been scheduled to be removed or has exited
        if handle.is_set():
            return False

        handle.set()
        return True

    async def _trio_watch_file(self, fd, callback, cancel):
        while True:
            await trio.hazmat.wait_readable(fd)
            if cancel.is_set():
                return
            callback()

    def watch_file(self, fd, callback):
        """
        Call callback() when fd has some data to read.  No parameters
        are passed to callback.

        Returns a handle that may be passed to remove_watch_file()

        fd -- file descriptor to watch for input
        callback -- function to call when input is available
        """
        cancel = trio.Event()
        if self.nursery:
            self.nursery.start_soon(self._trio_watch_file, fd, callback, cancel)
        else:
            self._watcher_queue.append((fd, callback, cancel))
        return cancel

    remove_watch_file = remove_alarm

    def enter_idle(self, callback):
        """
        Add a callback for entering idle.

        Returns a handle that may be passed to remove_idle()
        """
        # XXX there's no such thing as "idle" in most event loops; (scheduling a task with a lower
        # priority than everything else)  this fakes it the same way as Twisted, by scheduling the
        # callback to be called repeatedly
        cancel = trio.Event()

        def faux_idle_callback():
            callback()
            if self.nursery:
                self.nursery.start_soon(self._trio_alarm, self._idle_emulation_delay, faux_idle_callback, cancel)
            else:
                self._alarm_queue.append((self._idle_emulation_delay, faux_idle_callback, cancel))

        if self.nursery:
            self.nursery.start_soon(self._trio_alarm, self._idle_emulation_delay, faux_idle_callback, cancel)
        else:
            self._alarm_queue.append((self._idle_emulation_delay, faux_idle_callback, cancel))
        return cancel

    remove_enter_idle = remove_alarm

    def _register_queued_tasks(self):
        for alarm in self._alarm_queue:
            self.nursery.start_soon(self._trio_alarm, *alarm)
        self._alarm_queue = []

        for watcher in self._watcher_queue:
            self.nursery.start_soon(self._trio_watch_file, *watcher)
        self._watcher_queue = []

        for idle in self._idle_queue:
            self.nursery.start_soon(self._trio_idle, *idle)
        self._idle_queue = []

    async def _parent(self):
        """
        Create a nursery and register all of the tasks that were scheduled before trio initialized
        """
        if not self.nursery:
            async with trio.open_nursery() as nursery:
                self.nursery = nursery
                self._register_queued_tasks()
        else:
            self._register_queued_tasks()

    def run(self):
        """
        Start the event loop.  Exit the loop when any callback raises
        an exception.  If ExitMainLoop is raised, exit cleanly.
        """
        if not self.nursery:
            try:
                trio.run(self._parent)
            except ExitMainLoop:
                pass
            finally:
                self.nursery = None

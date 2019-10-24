#!/usr/bin/python
#
# Urwid main loop code using Python-3.5 features (Trio, Curio, etc)
#    Copyright (C) 2018 Toshio Kuratomi
#    Copyright (C) 2019 Tamas Nepusz
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

from .main_loop import EventLoop, ExitMainLoop


class TrioEventLoop(EventLoop):
    """
    Event loop based on the ``trio`` module.

    ``trio`` is an async library for Python 3.5 and later.
    """

    _idle_emulation_delay = 1.0/256 # a short time (in seconds)

    def __init__(self, nursery=None):
        """Constructor.

        Parameters:
            nursery: the Trio nursery in which the asynchronous tasks will
                execute. `None` will make the event loop use `trio.run()` when
                the loop is started and force it to create a nursery on its
                own.
        """
        import trio

        self._idle_handle = 0
        self._idle_callbacks = {}
        self._pending_tasks = []

        self._trio = trio
        self._nursery = None

        self._sleep = trio.sleep
        self._wait_readable = trio.hazmat.wait_readable

    def alarm(self, seconds, callback):
        """Calls `callback()` a given time from now.  No parameters are passed
        to the callback.

        Parameters:
            seconds: time in seconds to wait before calling the callback
            callback: function to call from the event loop

        Returns:
            a handle that may be passed to `remove_alarm()`
        """
        return self._start_task(self._alarm_task, seconds, callback)

    def enter_idle(self, callback):
        """Calls `callback()` when the event loop enters the idle state.

        There is no such thing as being idle in a Trio event loop so we
        simulate it by repeatedly calling `callback()` with a short delay.
        """
        self._idle_handle += 1
        self._idle_callbacks[self._idle_handle] = callback
        return self._idle_handle

    def remove_alarm(self, handle):
        """Removes an alarm.

        Parameters:
            handle: the handle of the alarm to remove
        """
        return self._cancel_scope(handle)

    def remove_enter_idle(self, handle):
        """Removes an idle callback.

        Parameters:
            handle: the handle of the idle callback to remove
        """
        try:
            del self._idle_callbacks[handle]
        except KeyError:
            return False
        return True

    def remove_watch_file(self, handle):
        """Removes a file descriptor being watched for input.

        Parameters:
            handle: the handle of the file descriptor callback to remove

        Returns:
            True if the file descriptor was watched, False otherwise
        """
        return self._cancel_scope(handle)

    def _cancel_scope(self, scope):
        """Cancels the given Trio cancellation scope.

        Returns:
            True if the scope was cancelled, False if it was cancelled already
            before invoking this function
        """
        scope, cancelled = scope
        existed = not cancelled[0]
        cancelled[0] = True
        scope.cancel()
        return existed

    def _create_cancel_scope(self):
        """Creates a Trio cancellation scope and a corresponding mutable flag
        that indicates whether the scope was cancelled already _from_ urwid.

        This is needed because `CancelScope.cancelled_caught` stays `False` until
        someone actually _handles_ the cancellation, and
        `CancelScope.cancel_called` can only be called from an async context
        (which we cannot guarantee).
        """
        return self._trio.CancelScope(), [False]

    def run(self):
        """Starts the event loop. Exits the loop when any callback raises an
        exception. If ExitMainLoop is raised, exits cleanly.
        """
        def _exception_handler(exc):
            if isinstance(exc, ExitMainLoop):
                return None
            else:
                return exc

        with self._trio.MultiError.catch(_exception_handler):
            if not self._nursery:
                self._trio.run(self._main_task)
            else:
                self._nursery.start_soon(self._main_task)

    def watch_file(self, fd, callback):
        """Calls `callback()` when the given file descriptor has some data
        to read. No parameters are passed to the callback.

        Parameters:
            fd: file descriptor to watch for input
            callback: function to call when some input is available

        Returns:
            a handle that may be passed to `remove_watch_file()`
        """
        return self._start_task(self._watch_task, fd, callback)

    async def _alarm_task(self, scope, seconds, callback):
        """Asynchronous task that sleeps for a given number of seconds and then
        calls the given callback.

        Parameters:
            scope: the cancellation scope that can be used to cancel the task
            seconds: the number of seconds to wait
            callback: the callback to call
        """
        with scope:
            await self._sleep(seconds)
            callback()

    async def _idle_task(self):
        """Asynchronous task that sleeps for a short amount of time and then
        calls all the registered idle callbacks.

        Used to simulate idle callbacks in the Trio event loop that has no
        concept of being idle.
        """
        while True:
            await self._sleep(self._idle_emulation_delay)
            for idle_callback in self._idle_callbacks.values():
                idle_callback()

    async def _main_task(self):
        """Main Trio task that opens a nursery and then sleeps until the user
        exits the app by raising ExitMainLoop.
        """

        if self._nursery:
            self._schedule_pending_tasks()
            await self._idle_task()
        else:
            try:
                async with self._trio.open_nursery() as self._nursery:
                    self._schedule_pending_tasks()
                    await self._idle_task()
            finally:
                self._nursery = None

    def _schedule_pending_tasks(self):
        """Schedules all pending asynchronous tasks that were created before
        the nursery to be executed on the nursery soon.
        """
        for task, scope, args in self._pending_tasks:
            self._nursery.start_soon(task, scope, *args)
        del self._pending_tasks[:]

    def _start_task(self, task, *args):
        """Starts an asynchronous task in the Trio nursery managed by the
        main loop. If the nursery has not started yet, store a reference to
        the task and the arguments so we can start the task when the nursery
        is open.

        Parameters:
            task: a Trio task to run

        Returns:
            a cancellation scope for the Trio task
        """
        handle = self._create_cancel_scope()
        scope, _ = handle
        if self._nursery:
            self._nursery.start_soon(task, scope, *args)
        else:
            self._pending_tasks.append((task, scope, args))
        return handle

    async def _watch_task(self, scope, fd, callback):
        """Asynchronous task that watches the given file descriptor and calls
        the given callback whenever the file descriptor becomes readable.

        Parameters:
            scope: the cancellation scope that can be used to cancel the task
            fd: the file descriptor to watch
            callback: the callback to call
        """
        with scope:
            while True:
                await self._wait_readable(fd)
                callback()

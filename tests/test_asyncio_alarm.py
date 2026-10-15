from __future__ import annotations

import asyncio
import gc
import sys
import unittest
import weakref

import urwid


class AsyncioAlarmTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.loop = asyncio.get_running_loop()
        self.evl = urwid.AsyncioEventLoop(loop=self.loop)

    async def test_remove_fired_alarm(self):
        fired = self.loop.create_future()
        handle = self.evl.alarm(0, lambda: fired.set_result(None))

        await asyncio.wait_for(fired, 1)

        self.assertFalse(self.evl.remove_alarm(handle))
        self.assertFalse(self.evl.remove_alarm(handle))

    async def test_remove_alarm_from_its_callback(self):
        removed = self.loop.create_future()

        def callback():
            removed.set_result(self.evl.remove_alarm(handle))

        handle = self.evl.alarm(0, callback)

        self.assertFalse(await asyncio.wait_for(removed, 1))

    async def test_remove_alarm_from_its_async_callback(self):
        removed = self.loop.create_future()

        async def callback():
            await asyncio.sleep(0)
            removed.set_result(self.evl.remove_alarm(handle))

        handle = self.evl.alarm(0, callback)

        self.assertFalse(await asyncio.wait_for(removed, 1))

    async def test_pending_alarm_is_cancelled(self):
        called = []
        handle = self.evl.alarm(0, lambda: called.append(True))

        self.assertTrue(self.evl.remove_alarm(handle))
        self.assertFalse(self.evl.remove_alarm(handle))
        await asyncio.sleep(0)

        self.assertTrue(handle.cancelled())
        self.assertEqual(called, [])

    async def test_directly_cancelled_alarm(self):
        handle = self.evl.alarm(60, lambda: None)
        handle.cancel()

        self.assertFalse(self.evl.remove_alarm(handle))

    async def test_directly_cancelled_handle_is_not_retained(self):
        handle = self.evl.alarm(60, lambda: None)
        handle_ref = weakref.ref(handle)
        handle.cancel()
        del handle

        await asyncio.sleep(0)
        gc.collect()

        self.assertIsNone(handle_ref())

    async def test_removing_one_alarm_preserves_another(self):
        fired = self.loop.create_future()
        called = []
        cancelled = self.evl.alarm(0, lambda: called.append(True))
        remaining = self.evl.alarm(0, lambda: fired.set_result(None))

        self.assertTrue(self.evl.remove_alarm(cancelled))
        await asyncio.wait_for(fired, 1)

        self.assertFalse(self.evl.remove_alarm(remaining))
        self.assertEqual(called, [])

    async def test_fired_handle_stays_uncancelled(self):
        fired = self.loop.create_future()
        handle = self.evl.alarm(0, lambda: fired.set_result(None))

        await asyncio.wait_for(fired, 1)

        self.assertFalse(handle.cancelled())

    @unittest.skipUnless(sys.implementation.name == "cpython", "Requires reference counting")
    async def test_fired_handle_does_not_require_cyclic_gc(self):
        gc_was_enabled = gc.isenabled()
        gc.disable()
        try:
            fired = self.loop.create_future()
            handle = self.evl.alarm(0, lambda: fired.set_result(None))
            handle_ref = weakref.ref(handle)
            del handle

            await asyncio.wait_for(fired, 1)
            await asyncio.sleep(0)

            self.assertIsNone(handle_ref())
        finally:
            if gc_was_enabled:
                gc.enable()


from __future__ import annotations

import gc
import sys
import sysconfig
import typing
import unittest
import weakref
from unittest.mock import Mock

from tests.util import GC_KEEPS_UNREACHABLE
from urwid import (
    Edit,
    MetaSignals,
    Signals,
    SimpleListWalker,
    Widget,
    connect_signal,
    disconnect_signal,
    disconnect_signal_by_key,
    emit_signal,
    register_signal,
)

if typing.TYPE_CHECKING:
    from collections.abc import Callable


class SiglnalsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.EmClass = type("EmClass", (object,), {})
        register_signal(cls.EmClass, ["change", "test"])

    def test_connect(self):
        obj = Mock()
        handler = Mock()
        edit = Edit("")
        key = connect_signal(edit, "change", handler, user_args=[obj])
        self.assertIsNotNone(key)
        edit.set_edit_text("long test text")
        handler.assert_called_once_with(obj, edit, "long test text")

        handler.reset_mock()
        disconnect_signal(edit, "change", handler, user_args=[obj])
        edit.set_edit_text("another text")
        handler.assert_not_called()

    def test_handler_mutation_during_emit(self):
        emitter = self.EmClass()
        calls = []

        def third():
            calls.append("third")

        def first():
            calls.append("first")
            disconnect_signal(emitter, "test", first)
            connect_signal(emitter, "test", third)

        def second():
            calls.append("second")

        connect_signal(emitter, "test", first)
        connect_signal(emitter, "test", second)

        emit_signal(emitter, "test")
        self.assertEqual(calls, ["first", "second"])

        emit_signal(emitter, "test")
        self.assertEqual(calls, ["first", "second", "second", "third"])

    @unittest.skipIf(
        sys.implementation.name in {"pypy", "graalpy"},
        "WeakRef works differently on PyPy/GraalPy's tracing GC",
    )
    def test_weak_del(self):
        emitter = SiglnalsTest.EmClass()
        w1 = Mock(name="w1")
        w2 = Mock(name="w2")
        w3 = Mock(name="w3")

        handler1 = Mock(name="handler1")
        handler2 = Mock(name="handler2")

        k1 = connect_signal(emitter, "test", handler1, weak_args=[w1], user_args=[42, "abc"])
        k2 = connect_signal(emitter, "test", handler2, weak_args=[w2, w3], user_args=[8])
        self.assertIsNotNone(k2)

        emit_signal(emitter, "test", "Foo")
        handler1.assert_called_once_with(w1, 42, "abc", "Foo")
        handler2.assert_called_once_with(w2, w3, 8, "Foo")

        handler1.reset_mock()
        handler2.reset_mock()
        del w1
        self.assertEqual(
            len(getattr(emitter, Signals._signal_attr)["test"]),
            1,
            getattr(emitter, Signals._signal_attr)["test"],
        )
        emit_signal(emitter, "test", "Bar")
        handler1.assert_not_called()
        handler2.assert_called_once_with(w2, w3, 8, "Bar")

        handler2.reset_mock()
        del w3
        emit_signal(emitter, "test", "Baz")
        handler1.assert_not_called()
        handler2.assert_not_called()
        self.assertEqual(len(getattr(emitter, Signals._signal_attr)["test"]), 0)
        del w2


class RegistryLeakTest(unittest.TestCase):
    """The signal registry does not keep the classes it knows alive."""

    @unittest.skipIf(
        sys.version_info[:2] == (3, 13) and sysconfig.get_config_var("Py_GIL_DISABLED"),
        "the free-threaded CPython 3.13 build makes every class immortal once a thread has been started",
    )
    @unittest.skipIf(GC_KEEPS_UNREACHABLE, "GraalPy for Python 3.11 never frees a class created at run time")
    def test_runtime_classes_are_collected(self) -> None:
        """Classes created at run time are freed once nothing else refers to them."""
        # Not a Widget subclass: GraalPy itself can keep a runtime Widget subclass alive.
        refs = [weakref.ref(MetaSignals("Runtime", (), {"signals": ["ping"]})) for _ in range(20)]
        gc.collect()
        self.assertEqual([], [ref for ref in refs if ref() is not None])

    def test_live_classes_and_subclasses_keep_their_signals(self) -> None:
        """A live class created at run time, and its subclass, still connect and emit their signals."""
        base = type("Base", (Widget,), {"signals": ["ping"]})
        sub = type("Sub", (base,), {})
        gc.collect()
        for cls in (base, sub):
            with self.subTest(cls=cls):
                obj = cls()
                handler = Mock()
                connect_signal(obj, "ping", handler)
                emit_signal(obj, "ping", 1)
                handler.assert_called_once_with(1)
                with self.assertRaises(NameError):
                    connect_signal(obj, "change", handler)


class _GetHook(dict):
    """Handler storage that calls ``hook`` once, right after the next lookup of a signal's handlers."""

    def __init__(self) -> None:
        """Start with no hook set."""
        super().__init__()
        self.hook: Callable[[], object] | None = None

    def get(self, *args: typing.Any) -> typing.Any:
        result = super().get(*args)
        hook, self.hook = self.hook, None
        if hook is not None:
            hook()
        return result


@unittest.skipUnless(sys.implementation.name == "cpython", "relies on reference counting to free the weak argument")
class WeakCallbackRaceTest(unittest.TestCase):
    """A handler removed by its weak argument's callback stays removed when the callback interrupts an update."""

    def setUp(self) -> None:
        """Connect a handler whose weak argument is held only by ``self.holder``."""
        self.emitter = SiglnalsTest.EmClass()
        self.signals = _GetHook()
        setattr(self.emitter, Signals._signal_attr, self.signals)
        self.holder = [Mock(name="weak")]
        connect_signal(self.emitter, "test", Mock(name="doomed"), weak_args=self.holder)
        self.survivor = Mock(name="survivor")

    def test_connect(self) -> None:
        """Connecting a handler does not restore the one removed while the handlers were being read."""
        self.signals.hook = self.holder.clear
        connect_signal(self.emitter, "test", self.survivor)
        self.assertEqual([self.survivor], [h[1] for h in self.signals["test"]])

    def test_disconnect_by_key(self) -> None:
        """Disconnecting a handler does not restore the one removed while the handlers were being read."""
        connect_signal(self.emitter, "test", self.survivor)
        key = connect_signal(self.emitter, "test", Mock(name="removed"))
        self.signals.hook = self.holder.clear
        disconnect_signal_by_key(self.emitter, "test", key)
        self.assertEqual([self.survivor], [h[1] for h in self.signals["test"]])

    def test_falsy_emitter(self) -> None:
        """A handler on an emitter that is false in a boolean context is removed as soon as its weak argument dies."""
        emitter = SimpleListWalker([])
        holder = [Mock(name="weak")]
        connect_signal(emitter, "modified", Mock(name="doomed"), weak_args=holder)
        holder.clear()
        self.assertEqual((), getattr(emitter, Signals._signal_attr)["modified"])

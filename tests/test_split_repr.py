from __future__ import annotations

import sys
import unittest

from urwid.split_repr import remove_defaults, split_repr


class RemoveDefaultsTest(unittest.TestCase):
    def test_defaults_are_matched_to_their_own_parameters(self) -> None:
        """Pair each default with its own parameter, whatever *args, **kwargs or keyword-only parameters follow."""

        def plain(self, a=1, b=2): ...

        def with_varargs(self, a=1, b=2, *args): ...

        def with_varkw(self, a=1, b=2, **kwargs): ...

        def with_both(self, a=1, b=2, *args, **kwargs): ...

        def with_keyword_only(self, a=1, *, b=2): ...

        for fn in (plain, with_varargs, with_varkw, with_both, with_keyword_only):
            with self.subTest(fn=fn.__name__):
                self.assertEqual({"b": 5}, remove_defaults({"a": 1, "b": 5}, fn))
                self.assertEqual({"a": 5}, remove_defaults({"a": 5, "b": 2}, fn))
                self.assertEqual({}, remove_defaults({"a": 1, "b": 2}, fn))

    def test_keys_without_a_default_are_kept(self) -> None:
        """Keep a key that names no parameter, or a parameter without a default."""

        def fn(self, a, b=2, **kwargs): ...

        def no_defaults(self, a, b): ...

        self.assertEqual({"a": 2, "c": 2}, remove_defaults({"a": 2, "b": 2, "c": 2}, fn))
        self.assertEqual({"a": 1, "b": 2}, remove_defaults({"a": 1, "b": 2}, no_defaults))

    @unittest.skipUnless(sys.version_info >= (3, 14), "annotations are evaluated lazily from Python 3.14")
    def test_annotations_are_not_evaluated(self) -> None:
        """Read the defaults of a callable whose annotation names a type that is not defined at run time."""
        namespace: dict[str, object] = {}
        # Compiled without the module's `from __future__ import annotations`, as in a module that lacks it.
        exec(compile("def fn(self, a: Undefined = 1): ...", "<test>", "exec", dont_inherit=True), namespace)

        self.assertEqual({}, remove_defaults({"a": 1}, namespace["fn"]))


class SplitReprTest(unittest.TestCase):
    def test_empty_repr_falls_back_to_the_replaced_repr(self) -> None:
        """Without words and attributes, use the __repr__ that split_repr replaced, also from a subclass."""

        class Base:
            def __repr__(self) -> str:
                return "<base repr>"

        class Foo(Base):
            __repr__ = split_repr

            def _repr_words(self) -> list[str]:
                return []

            def _repr_attrs(self) -> dict[str, object]:
                return {}

        class Bar(Foo):
            pass

        class Baz(Foo):
            __repr__ = split_repr

        for cls in (Foo, Bar, Baz):
            with self.subTest(cls=cls.__name__):
                self.assertEqual("<base repr>", repr(cls()))

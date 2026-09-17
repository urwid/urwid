from __future__ import annotations

import locale
import unittest

import urwid
from urwid import str_util, util


class CalcWidthTest(unittest.TestCase):
    def setUp(self) -> None:
        self.old_encoding = util.get_encoding()

    def tearDown(self) -> None:
        urwid.set_encoding(self.old_encoding)

    def wtest(self, desc, s, exp):
        s = s.encode("iso8859-1")
        result = str_util.calc_width(s, 0, len(s))
        assert result == exp, f"{desc} got:{result!r} expected:{exp!r}"

    def test1(self):
        util.set_encoding("utf-8")
        self.wtest("narrow", "hello", 5)
        self.wtest("wide char", "\xe6\x9b\xbf", 2)
        self.wtest("invalid", "\xe6", 1)
        self.wtest("zero width", "\xcc\x80", 0)
        self.wtest("mixed", "hello\xe6\x9b\xbf\xe6\x9b\xbf", 9)

    def test2(self):
        util.set_encoding("euc-jp")
        self.wtest("narrow", "hello", 5)
        self.wtest("wide", "\xa1\xa1\xa1\xa1", 4)
        self.wtest("invalid", "\xa1", 1)


class ConvertDecSpecialTest(unittest.TestCase):
    def setUp(self) -> None:
        self.old_encoding = util.get_encoding()

    def tearDown(self) -> None:
        urwid.set_encoding(self.old_encoding)

    def ctest(self, desc, s, exp, expcs):
        exp = exp.encode("iso8859-1")
        util.set_encoding("ascii")
        c = urwid.Text(s).render((5,))
        result = c._text[0]
        assert result == exp, f"{desc} got:{result!r} expected:{exp!r}"
        resultcs = c._cs[0]
        assert resultcs == expcs, f"{desc} got:{resultcs!r} expected:{expcs!r}"

    def test1(self):
        self.ctest("no conversion", "hello", "hello", [(None, 5)])
        self.ctest("only special", "£££££", "}}}}}", [("0", 5)])
        self.ctest("mix left", "££abc", "}}abc", [("0", 2), (None, 3)])
        self.ctest("mix right", "abc££", "abc}}", [(None, 3), ("0", 2)])
        self.ctest("mix inner", "a££bc", "a}}bc", [(None, 1), ("0", 2), (None, 2)])
        self.ctest("mix well", "£a£b£", "}a}b}", [("0", 1), (None, 1), ("0", 1), (None, 1), ("0", 1)])


class WithinDoubleByteTest(unittest.TestCase):
    def setUp(self):
        self.old_encoding = util.get_encoding()
        urwid.set_encoding("euc-jp")

    def tearDown(self) -> None:
        urwid.set_encoding(self.old_encoding)

    def wtest(self, s, ls, pos, expected, desc):
        result = str_util.within_double_byte(s.encode("iso8859-1"), ls, pos)
        assert result == expected, f"{desc} got:{result!r} expected: {expected!r}"

    def test1(self):
        self.wtest("mnopqr", 0, 2, 0, "simple no high bytes")
        self.wtest("mn\xa1\xa1qr", 0, 2, 1, "simple 1st half")
        self.wtest("mn\xa1\xa1qr", 0, 3, 2, "simple 2nd half")
        self.wtest("m\xa1\xa1\xa1\xa1r", 0, 3, 1, "subsequent 1st half")
        self.wtest("m\xa1\xa1\xa1\xa1r", 0, 4, 2, "subsequent 2nd half")
        self.wtest("mn\xa1@qr", 0, 3, 2, "simple 2nd half lo")
        self.wtest("mn\xa1\xa1@r", 0, 4, 0, "subsequent not 2nd half lo")
        self.wtest("m\xa1\xa1\xa1@r", 0, 4, 2, "subsequent 2nd half lo")

    def test2(self):
        self.wtest("\xa1\xa1qr", 0, 0, 1, "begin 1st half")
        self.wtest("\xa1\xa1qr", 0, 1, 2, "begin 2nd half")
        self.wtest("\xa1@qr", 0, 1, 2, "begin 2nd half lo")
        self.wtest("\xa1\xa1\xa1\xa1r", 0, 2, 1, "begin subs. 1st half")
        self.wtest("\xa1\xa1\xa1\xa1r", 0, 3, 2, "begin subs. 2nd half")
        self.wtest("\xa1\xa1\xa1@r", 0, 3, 2, "begin subs. 2nd half lo")
        self.wtest("\xa1@\xa1@r", 0, 3, 2, "begin subs. 2nd half lo lo")
        self.wtest("@\xa1\xa1@r", 0, 3, 0, "begin subs. not 2nd half lo")

    def test3(self):
        self.wtest("abc \xa1\xa1qr", 4, 4, 1, "newline 1st half")
        self.wtest("abc \xa1\xa1qr", 4, 5, 2, "newline 2nd half")
        self.wtest("abc \xa1@qr", 4, 5, 2, "newline 2nd half lo")
        self.wtest("abc \xa1\xa1\xa1\xa1r", 4, 6, 1, "newl subs. 1st half")
        self.wtest("abc \xa1\xa1\xa1\xa1r", 4, 7, 2, "newl subs. 2nd half")
        self.wtest("abc \xa1\xa1\xa1@r", 4, 7, 2, "newl subs. 2nd half lo")
        self.wtest("abc \xa1@\xa1@r", 4, 7, 2, "newl subs. 2nd half lo lo")
        self.wtest("abc @\xa1\xa1@r", 4, 7, 0, "newl subs. not 2nd half lo")


class CalcTextPosTest(unittest.TestCase):
    def setUp(self) -> None:
        self.old_encoding = util.get_encoding()

    def tearDown(self) -> None:
        urwid.set_encoding(self.old_encoding)

    def ctptest(self, text, tests):
        text = text.encode("iso8859-1")
        for s, e, p, expected in tests:
            got = str_util.calc_text_pos(text, s, e, p)
            assert got == expected, f"{s, e, p!r} got:{got!r} expected:{expected!r}"

    def test1(self):
        text = "hello world out there"
        tests = [
            (0, 21, 0, (0, 0)),
            (0, 21, 5, (5, 5)),
            (0, 21, 21, (21, 21)),
            (0, 21, 50, (21, 21)),
            (2, 15, 50, (15, 13)),
            (6, 21, 0, (6, 0)),
            (6, 21, 3, (9, 3)),
        ]
        self.ctptest(text, tests)

    def test2_wide(self):
        util.set_encoding("euc-jp")
        text = "hel\xa1\xa1 world out there"
        tests = [
            (0, 21, 0, (0, 0)),
            (0, 21, 4, (3, 3)),
            (2, 21, 2, (3, 1)),
            (2, 21, 3, (5, 3)),
            (6, 21, 0, (6, 0)),
        ]
        self.ctptest(text, tests)

    def test3_utf8(self):
        util.set_encoding("utf-8")
        text = "hel\xc4\x83 world \xe2\x81\x81 there"
        tests = [
            (0, 21, 0, (0, 0)),
            (0, 21, 4, (5, 4)),
            (2, 21, 1, (3, 1)),
            (2, 21, 2, (5, 2)),
            (2, 21, 3, (6, 3)),
            (6, 21, 7, (15, 7)),
            (6, 21, 8, (16, 8)),
        ]
        self.ctptest(text, tests)

    def test4_utf8(self):
        util.set_encoding("utf-8")
        text = "he\xcc\x80llo \xe6\x9b\xbf world"
        tests = [
            (0, 15, 0, (0, 0)),
            (0, 15, 1, (1, 1)),
            (0, 15, 2, (4, 2)),
            (0, 15, 4, (6, 4)),
            (8, 15, 0, (8, 0)),
            (8, 15, 1, (8, 0)),
            (8, 15, 2, (11, 2)),
            (8, 15, 5, (14, 5)),
        ]
        self.ctptest(text, tests)


class TagMarkupTest(unittest.TestCase):
    mytests = [
        ("simple one", "simple one", []),
        (("blue", "john"), "john", [("blue", 4)]),
        (["a ", "litt", "le list"], "a little list", []),
        (
            ["mix", [" it", ("high", [" up", ("ital", " a")])], " little"],
            "mix it up a little",
            [(None, 6), ("high", 3), ("ital", 2)],
        ),
        (["££", "x££"], "££x££", []),
        ([b"\xc2\x80", b"\xc2\x80"], b"\xc2\x80\xc2\x80", []),
    ]

    def test(self):
        for input, text, attr in self.mytests:
            restext, resattr = urwid.decompose_tagmarkup(input)
            assert restext == text, f"got: {restext!r} expected: {text!r}"
            assert resattr == attr, f"got: {resattr!r} expected: {attr!r}"

    def test_bad_tuple(self):
        self.assertRaises(urwid.TagMarkupException, lambda: urwid.decompose_tagmarkup((1, 2, 3)))

    def test_bad_type(self):
        self.assertRaises(urwid.TagMarkupException, lambda: urwid.decompose_tagmarkup(5))


class RleTest(unittest.TestCase):
    def test_rle_prepend(self):
        rle0 = [("A", 10), ("B", 15)]
        # the rle functions are mutating, so make a few copies of rle0
        rle1, rle2 = rle0[:], rle0[:]
        util.rle_prepend_modify(rle1, ("A", 3))
        util.rle_prepend_modify(rle2, ("X", 2))
        self.assertListEqual(rle1, [("A", 13), ("B", 15)])
        self.assertListEqual(rle2, [("X", 2), ("A", 10), ("B", 15)])

    def test_rle_append(self):
        rle0 = [("A", 10), ("B", 15)]
        rle3, rle4 = rle0[:], rle0[:]
        util.rle_append_modify(rle3, ("B", 5))
        util.rle_append_modify(rle4, ("K", 1))
        self.assertListEqual(rle3, [("A", 10), ("B", 20)])
        self.assertListEqual(rle4, [("A", 10), ("B", 15), ("K", 1)])

    def test_rle_prepend_empty(self):
        rle = []
        util.rle_prepend_modify(rle, ("A", 3))
        self.assertListEqual(rle, [("A", 3)])

    def test_rle_append_empty(self):
        rle = []
        util.rle_append_modify(rle, ("A", 3))
        self.assertListEqual(rle, [("A", 3)])

    def test_rle_get_at(self):
        rle = [("A", 10), ("B", 15)]
        self.assertEqual("A", util.rle_get_at(rle, 0))
        self.assertEqual("A", util.rle_get_at(rle, 9))
        self.assertEqual("B", util.rle_get_at(rle, 10))
        self.assertEqual("B", util.rle_get_at(rle, 24))
        self.assertIsNone(util.rle_get_at(rle, 25))
        self.assertIsNone(util.rle_get_at(rle, -1))

    def test_rle_subseg(self):
        rle = [("A", 10), ("B", 15)]
        self.assertListEqual([("A", 10), ("B", 15)], util.rle_subseg(rle, 0, 25))
        self.assertListEqual([("A", 5)], util.rle_subseg(rle, 0, 5))
        self.assertListEqual([("A", 5), ("B", 5)], util.rle_subseg(rle, 5, 15))
        self.assertListEqual([("B", 5)], util.rle_subseg(rle, 20, 30))
        self.assertListEqual([], util.rle_subseg(rle, 25, 30))
        self.assertListEqual([], util.rle_subseg(rle, 5, 5))

    def test_rle_len(self):
        self.assertEqual(0, util.rle_len([]))
        self.assertEqual(25, util.rle_len([("A", 10), ("B", 15)]))
        self.assertRaises(TypeError, util.rle_len, [("A", 10), "not a tuple"])

    def test_rle_join_modify(self):
        rle = [("A", 10), ("B", 15)]
        util.rle_join_modify(rle, [])
        self.assertListEqual(rle, [("A", 10), ("B", 15)])

        util.rle_join_modify(rle, [("B", 5), ("C", 1)])
        self.assertListEqual(rle, [("A", 10), ("B", 20), ("C", 1)])

        util.rle_join_modify(rle, [("D", 2)])
        self.assertListEqual(rle, [("A", 10), ("B", 20), ("C", 1), ("D", 2)])

    def test_rle_product(self):
        rle1 = [("a", 10), ("b", 5)]
        rle2 = [("Q", 5), ("P", 10)]
        self.assertListEqual(
            [(("a", "Q"), 5), (("a", "P"), 5), (("b", "P"), 5)],
            util.rle_product(rle1, rle2),
        )
        self.assertListEqual([], util.rle_product([], rle2))
        self.assertListEqual([], util.rle_product(rle1, []))

    def test_rle_product_skips_zero_length_runs(self):
        rle1 = [("a", 0), ("b", 5)]
        rle2 = [("Q", 0), ("P", 5)]
        self.assertListEqual([(("b", "P"), 5)], util.rle_product(rle1, rle2))

    def test_trim_text_attr_cs(self):
        old_encoding = util.get_encoding()
        try:
            util.set_encoding("euc-jp")
            text = "hel\xa1\xa1lo".encode("iso8859-1")
            attr = [("A", 7)]
            cs = [(None, 7)]

            self.assertEqual(
                (b"hel\xa1\xa1lo", [("A", 7)], [(None, 7)]),
                util.trim_text_attr_cs(text, attr, cs, 0, 7),
            )
            self.assertEqual((b"hel ", [("A", 4)], [(None, 4)]), util.trim_text_attr_cs(text, attr, cs, 0, 4))
            self.assertEqual((b" lo", [("A", 3)], [(None, 3)]), util.trim_text_attr_cs(text, attr, cs, 4, 7))
        finally:
            urwid.set_encoding(old_encoding)


class PortabilityTest(unittest.TestCase):
    def test_locale(self):
        initial = locale.getlocale()

        locale.setlocale(locale.LC_ALL, (None, None))
        util.detect_encoding()
        self.assertEqual(locale.getlocale(), (None, None))

        try:
            locale.setlocale(locale.LC_ALL, ("en_US", "UTF-8"))
        except locale.Error as exc:
            if "unsupported locale setting" not in str(exc):
                raise

            print(
                f"Locale change impossible, probably locale not supported by system (libc ignores this error).\n"
                f"{exc}"
            )
            return

        util.detect_encoding()
        self.assertEqual(locale.getlocale(), ("en_US", "UTF-8"))

        try:
            locale.setlocale(locale.LC_ALL, initial)
        except locale.Error as exc:
            if "unsupported locale setting" not in str(exc):
                raise

            print(
                f"Locale restore impossible, probably locale not supported by system (libc ignores this error).\n"
                f"{exc}"
            )


class TestEmptyMarkup(unittest.TestCase):
    def test_001_empty(self):
        text = urwid.Text("")
        text.set_text(text.get_text())
        self.assertEqual("", text.text)

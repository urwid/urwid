#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Urwid unit testing .. ok, ok, ok
#    Copyright (C) 2004-2012  Ian Ward
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

import unittest
from doctest import DocTestSuite, ELLIPSIS, IGNORE_EXCEPTION_DETAIL

import urwid
from urwid.compat import bytes, B
from urwid.vterm_test import TermTest
from urwid.text_layout import calc_pos, calc_coords, CanNotDisplayText
from urwid.canvas import (shard_body, shard_body_tail, shards_trim_top,
    shards_trim_sides, shards_join, shards_trim_rows, shard_body_row)
from urwid.graphics import calculate_bargraph_display



class DecodeOneTest(unittest.TestCase):
    def gwt(self, ch, exp_ord, exp_pos):
        ch = B(ch)
        o, pos = urwid.str_util.decode_one(ch,0)
        assert o==exp_ord, " got:%r expected:%r" % (o, exp_ord)
        assert pos==exp_pos, " got:%r expected:%r" % (pos, exp_pos)

    def test1byte(self):
        self.gwt("ab", ord("a"), 1)
        self.gwt("\xc0a", ord("?"), 1) # error

    def test2byte(self):
        self.gwt("\xc2", ord("?"), 1) # error
        self.gwt("\xc0\x80", ord("?"), 1) # error
        self.gwt("\xc2\x80", 0x80, 2)
        self.gwt("\xdf\xbf", 0x7ff, 2)

    def test3byte(self):
        self.gwt("\xe0", ord("?"), 1) # error
        self.gwt("\xe0\xa0", ord("?"), 1) # error
        self.gwt("\xe0\x90\x80", ord("?"), 1) # error
        self.gwt("\xe0\xa0\x80", 0x800, 3)
        self.gwt("\xef\xbf\xbf", 0xffff, 3)

    def test4byte(self):
        self.gwt("\xf0", ord("?"), 1) # error
        self.gwt("\xf0\x90", ord("?"), 1) # error
        self.gwt("\xf0\x90\x80", ord("?"), 1) # error
        self.gwt("\xf0\x80\x80\x80", ord("?"), 1) # error
        self.gwt("\xf0\x90\x80\x80", 0x10000, 4)
        self.gwt("\xf3\xbf\xbf\xbf", 0xfffff, 4)



class CalcWidthTest(unittest.TestCase):
    def wtest(self, desc, s, exp):
        s = B(s)
        result = urwid.calc_width( s, 0, len(s))
        assert result==exp, "%s got:%r expected:%r" % (desc, result, exp)
    def test1(self):
        urwid.set_encoding("utf-8")
        self.wtest("narrow", "hello", 5)
        self.wtest("wide char", '\xe6\x9b\xbf', 2)
        self.wtest("invalid", '\xe6', 1)
        self.wtest("zero width", '\xcc\x80', 0)
        self.wtest("mixed", 'hello\xe6\x9b\xbf\xe6\x9b\xbf', 9)

    def test2(self):
        urwid.set_encoding("euc-jp")
        self.wtest("narrow", "hello", 5)
        self.wtest("wide", "\xA1\xA1\xA1\xA1", 4)
        self.wtest("invalid", "\xA1", 1)


class ConvertDecSpecialTest(unittest.TestCase):
    def ctest(self, desc, s, exp, expcs):
        exp = B(exp)
        urwid.set_encoding('ascii')
        c = urwid.Text(s).render((5,))
        result = c._text[0]
        assert result==exp, "%s got:%r expected:%r" % (desc, result, exp)
        resultcs = c._cs[0]
        assert resultcs==expcs, "%s got:%r expected:%r" % (desc,
                                                           resultcs, expcs)


    def test1(self):
        self.ctest("no conversion", u"hello", "hello", [(None,5)])
        self.ctest("only special", u"£££££", "}}}}}", [("0",5)])
        self.ctest("mix left", u"££abc", "}}abc", [("0",2),(None,3)])
        self.ctest("mix right", u"abc££", "abc}}", [(None,3),("0",2)])
        self.ctest("mix inner", u"a££bc", "a}}bc",
            [(None,1),("0",2),(None,2)] )
        self.ctest("mix well", u"£a£b£", "}a}b}",
            [("0",1),(None,1),("0",1),(None,1),("0",1)] )


class WithinDoubleByteTest(unittest.TestCase):
    def setUp(self):
        urwid.set_encoding("euc-jp")
    def wtest(self, s, ls, pos, expected, desc):
        result = urwid.within_double_byte(B(s), ls, pos)
        assert result==expected, "%s got:%r expected: %r" % (desc,
                                                             result, expected)
    def test1(self):
        self.wtest("mnopqr",0,2,0,'simple no high bytes')
        self.wtest("mn\xA1\xA1qr",0,2,1,'simple 1st half')
        self.wtest("mn\xA1\xA1qr",0,3,2,'simple 2nd half')
        self.wtest("m\xA1\xA1\xA1\xA1r",0,3,1,'subsequent 1st half')
        self.wtest("m\xA1\xA1\xA1\xA1r",0,4,2,'subsequent 2nd half')
        self.wtest("mn\xA1@qr",0,3,2,'simple 2nd half lo')
        self.wtest("mn\xA1\xA1@r",0,4,0,'subsequent not 2nd half lo')
        self.wtest("m\xA1\xA1\xA1@r",0,4,2,'subsequent 2nd half lo')

    def test2(self):
        self.wtest("\xA1\xA1qr",0,0,1,'begin 1st half')
        self.wtest("\xA1\xA1qr",0,1,2,'begin 2nd half')
        self.wtest("\xA1@qr",0,1,2,'begin 2nd half lo')
        self.wtest("\xA1\xA1\xA1\xA1r",0,2,1,'begin subs. 1st half')
        self.wtest("\xA1\xA1\xA1\xA1r",0,3,2,'begin subs. 2nd half')
        self.wtest("\xA1\xA1\xA1@r",0,3,2,'begin subs. 2nd half lo')
        self.wtest("\xA1@\xA1@r",0,3,2,'begin subs. 2nd half lo lo')
        self.wtest("@\xA1\xA1@r",0,3,0,'begin subs. not 2nd half lo')

    def test3(self):
        self.wtest("abc \xA1\xA1qr",4,4,1,'newline 1st half')
        self.wtest("abc \xA1\xA1qr",4,5,2,'newline 2nd half')
        self.wtest("abc \xA1@qr",4,5,2,'newline 2nd half lo')
        self.wtest("abc \xA1\xA1\xA1\xA1r",4,6,1,'newl subs. 1st half')
        self.wtest("abc \xA1\xA1\xA1\xA1r",4,7,2,'newl subs. 2nd half')
        self.wtest("abc \xA1\xA1\xA1@r",4,7,2,'newl subs. 2nd half lo')
        self.wtest("abc \xA1@\xA1@r",4,7,2,'newl subs. 2nd half lo lo')
        self.wtest("abc @\xA1\xA1@r",4,7,0,'newl subs. not 2nd half lo')



class CalcTextPosTest(unittest.TestCase):
    def ctptest(self, text, tests):
        text = B(text)
        for s,e,p, expected in tests:
            got = urwid.calc_text_pos( text, s, e, p )
            assert got == expected, "%r got:%r expected:%r" % ((s,e,p),
                                                               got, expected)
    def test1(self):
        text = "hello world out there"
        tests = [
            (0,21,0, (0,0)),
            (0,21,5, (5,5)),
            (0,21,21, (21,21)),
            (0,21,50, (21,21)),
            (2,15,50, (15,13)),
            (6,21,0, (6,0)),
            (6,21,3, (9,3)),
            ]
        self.ctptest(text, tests)

    def test2_wide(self):
        urwid.set_encoding("euc-jp")
        text = "hel\xA1\xA1 world out there"
        tests = [
            (0,21,0, (0,0)),
            (0,21,4, (3,3)),
            (2,21,2, (3,1)),
            (2,21,3, (5,3)),
            (6,21,0, (6,0)),
            ]
        self.ctptest(text, tests)

    def test3_utf8(self):
        urwid.set_encoding("utf-8")
        text = "hel\xc4\x83 world \xe2\x81\x81 there"
        tests = [
            (0,21,0, (0,0)),
            (0,21,4, (5,4)),
            (2,21,1, (3,1)),
            (2,21,2, (5,2)),
            (2,21,3, (6,3)),
            (6,21,7, (15,7)),
            (6,21,8, (16,8)),
            ]
        self.ctptest(text, tests)

    def test4_utf8(self):
        urwid.set_encoding("utf-8")
        text = "he\xcc\x80llo \xe6\x9b\xbf world"
        tests = [
            (0,15,0, (0,0)),
            (0,15,1, (1,1)),
            (0,15,2, (4,2)),
            (0,15,4, (6,4)),
            (8,15,0, (8,0)),
            (8,15,1, (8,0)),
            (8,15,2, (11,2)),
            (8,15,5, (14,5)),
            ]
        self.ctptest(text, tests)

class CalcBreaksTest(unittest.TestCase):
    def cbtest(self, width, exp):
        result = urwid.default_layout.calculate_text_segments(
            B(self.text), width, self.mode )
        assert len(result) == len(exp), repr((result, exp))
        for l,e in zip(result, exp):
            end = l[-1][-1]
            assert end == e, repr((result,exp))

    def test(self):
        for width, exp in self.do:
            self.cbtest( width, exp )

class CalcBreaksCharTest(CalcBreaksTest):
    mode = 'any'
    text = "abfghsdjf askhtrvs\naltjhgsdf ljahtshgf"
    # tests
    do = [
        ( 100, [18,38] ),
        ( 6, [6, 12, 18, 25, 31, 37, 38] ),
        ( 10, [10, 18, 29, 38] ),
    ]

class CalcBreaksDBCharTest(CalcBreaksTest):
    def setUp(self):
        urwid.set_encoding("euc-jp")
    mode = 'any'
    text = "abfgh\xA1\xA1j\xA1\xA1xskhtrvs\naltjhgsdf\xA1\xA1jahtshgf"
    # tests
    do = [
        ( 10, [10, 18, 28, 38] ),
        ( 6, [5, 11, 17, 18, 25, 31, 37, 38] ),
        ( 100, [18, 38]),
    ]

class CalcBreaksWordTest(CalcBreaksTest):
    mode = 'space'
    text = "hello world\nout there. blah"
    # tests
    do = [
        ( 10, [5, 11, 22, 27] ),
        ( 5, [5, 11, 17, 22, 27] ),
        ( 100, [11, 27] ),
    ]

class CalcBreaksWordTest2(CalcBreaksTest):
    mode = 'space'
    text = "A simple set of words, really...."
    do = [
        ( 10, [8, 15, 22, 33]),
        ( 17, [15, 33]),
        ( 13, [12, 22, 33]),
    ]

class CalcBreaksDBWordTest(CalcBreaksTest):
    def setUp(self):
        urwid.set_encoding("euc-jp")
    mode = 'space'
    text = "hel\xA1\xA1 world\nout-\xA1\xA1tre blah"
    # tests
    do = [
        ( 10, [5, 11, 21, 26] ),
        ( 5, [5, 11, 16, 21, 26] ),
        ( 100, [11, 26] ),
    ]

class CalcBreaksUTF8Test(CalcBreaksTest):
    def setUp(self):
        urwid.set_encoding("utf-8")
    mode = 'space'
    text = '\xe6\x9b\xbf\xe6\xb4\xbc\xe6\xb8\x8e\xe6\xba\x8f\xe6\xbd\xba'
    do = [
        (4, [6, 12, 15] ),
        (10, [15] ),
        (5, [6, 12, 15] ),
    ]

class CalcBreaksCantDisplayTest(unittest.TestCase):
    def test(self):
        urwid.set_encoding("euc-jp")
        self.assertRaises(CanNotDisplayText,
            urwid.default_layout.calculate_text_segments,
            B('\xA1\xA1'), 1, 'space' )
        urwid.set_encoding("utf-8")
        self.assertRaises(CanNotDisplayText,
            urwid.default_layout.calculate_text_segments,
            B('\xe9\xa2\x96'), 1, 'space' )

class SubsegTest(unittest.TestCase):
    def setUp(self):
        urwid.set_encoding("euc-jp")

    def st(self, seg, text, start, end, exp):
        text = B(text)
        s = urwid.LayoutSegment(seg)
        result = s.subseg( text, start, end )
        assert result == exp, "Expected %r, got %r"%(exp,result)

    def test1_padding(self):
        self.st( (10, None), "", 0, 8,    [(8, None)] )
        self.st( (10, None), "", 2, 10, [(8, None)] )
        self.st( (10, 0), "", 3, 7,     [(4, 0)] )
        self.st( (10, 0), "", 0, 20,     [(10, 0)] )

    def test2_text(self):
        self.st( (10, 0, B("1234567890")), "", 0, 8,  [(8,0,B("12345678"))] )
        self.st( (10, 0, B("1234567890")), "", 2, 10, [(8,0,B("34567890"))] )
        self.st( (10, 0, B("12\xA1\xA156\xA1\xA190")), "", 2, 8,
            [(6, 0, B("\xA1\xA156\xA1\xA1"))] )
        self.st( (10, 0, B("12\xA1\xA156\xA1\xA190")), "", 3, 8,
            [(5, 0, B(" 56\xA1\xA1"))] )
        self.st( (10, 0, B("12\xA1\xA156\xA1\xA190")), "", 2, 7,
            [(5, 0, B("\xA1\xA156 "))] )
        self.st( (10, 0, B("12\xA1\xA156\xA1\xA190")), "", 3, 7,
            [(4, 0, B(" 56 "))] )
        self.st( (10, 0, B("12\xA1\xA156\xA1\xA190")), "", 0, 20,
            [(10, 0, B("12\xA1\xA156\xA1\xA190"))] )

    def test3_range(self):
        t = "1234567890"
        self.st( (10, 0, 10), t, 0, 8,    [(8, 0, 8)] )
        self.st( (10, 0, 10), t, 2, 10, [(8, 2, 10)] )
        self.st( (6, 2, 8), t, 1, 6,     [(5, 3, 8)] )
        self.st( (6, 2, 8), t, 0, 5,     [(5, 2, 7)] )
        self.st( (6, 2, 8), t, 1, 5,     [(4, 3, 7)] )
        t = "12\xA1\xA156\xA1\xA190"
        self.st( (10, 0, 10), t, 0, 8,    [(8, 0, 8)] )
        self.st( (10, 0, 10), t, 2, 10, [(8, 2, 10)] )
        self.st( (6, 2, 8), t, 1, 6,     [(1, 3), (4, 4, 8)] )
        self.st( (6, 2, 8), t, 0, 5,     [(4, 2, 6), (1, 6)] )
        self.st( (6, 2, 8), t, 1, 5,     [(1, 3), (2, 4, 6), (1, 6)] )



class CalcTranslateTest(unittest.TestCase):
    def setUp(self):
        urwid.set_encoding("utf-8")
    def test1_left(self):
        result = urwid.default_layout.layout( self.text,
            self.width, 'left', self.mode)
        assert result == self.result_left, result
    def test2_right(self):
        result = urwid.default_layout.layout( self.text,
            self.width, 'right', self.mode)
        assert result == self.result_right, result
    def test3_center(self):
        result = urwid.default_layout.layout( self.text,
            self.width, 'center', self.mode)
        assert result == self.result_center, result

class CalcTranslateCharTest(CalcTranslateTest):
    text = "It's out of control!\nYou've got to"
    mode = 'any'
    width = 15
    result_left = [
        [(15, 0, 15)],
        [(5, 15, 20), (0, 20)],
        [(13, 21, 34), (0, 34)]]
    result_right = [
        [(15, 0, 15)],
        [(10, None), (5, 15, 20), (0,20)],
        [(2, None), (13, 21, 34), (0,34)]]
    result_center = [
        [(15, 0, 15)],
        [(5, None), (5, 15, 20), (0,20)],
        [(1, None), (13, 21, 34), (0,34)]]

class CalcTranslateWordTest(CalcTranslateTest):
    text = "It's out of control!\nYou've got to"
    mode = 'space'
    width = 14
    result_left = [
        [(11, 0, 11), (0, 11)],
        [(8, 12, 20), (0, 20)],
        [(13, 21, 34), (0, 34)]]
    result_right = [
        [(3, None), (11, 0, 11), (0, 11)],
        [(6, None), (8, 12, 20), (0, 20)],
        [(1, None), (13, 21, 34), (0, 34)]]
    result_center = [
        [(2, None), (11, 0, 11), (0, 11)],
        [(3, None), (8, 12, 20), (0, 20)],
        [(1, None), (13, 21, 34), (0, 34)]]

class CalcTranslateWordTest2(CalcTranslateTest):
    text = "It's out of control!\nYou've got to "
    mode = 'space'
    width = 14
    result_left = [
        [(11, 0, 11), (0, 11)],
        [(8, 12, 20), (0, 20)],
        [(14, 21, 35), (0, 35)]]
    result_right = [
        [(3, None), (11, 0, 11), (0, 11)],
        [(6, None), (8, 12, 20), (0, 20)],
        [(14, 21, 35), (0, 35)]]
    result_center = [
        [(2, None), (11, 0, 11), (0, 11)],
        [(3, None), (8, 12, 20), (0, 20)],
        [(14, 21, 35), (0, 35)]]

class CalcTranslateWordTest3(CalcTranslateTest):
    def setUp(self):
        urwid.set_encoding('utf-8')
    text = B('\xe6\x9b\xbf\xe6\xb4\xbc\n\xe6\xb8\x8e\xe6\xba\x8f\xe6\xbd\xba')
    width = 10
    mode = 'space'
    result_left = [
        [(4, 0, 6), (0, 6)],
        [(6, 7, 16), (0, 16)]]
    result_right = [
        [(6, None), (4, 0, 6), (0, 6)],
        [(4, None), (6, 7, 16), (0, 16)]]
    result_center = [
        [(3, None), (4, 0, 6), (0, 6)],
        [(2, None), (6, 7, 16), (0, 16)]]

class CalcTranslateWordTest4(CalcTranslateTest):
    text = ' Die Gedank'
    width = 3
    mode = 'space'
    result_left = [
        [(0, 0)],
        [(3, 1, 4), (0, 4)],
        [(3, 5, 8)],
        [(3, 8, 11), (0, 11)]]
    result_right = [
        [(3, None), (0, 0)],
        [(3, 1, 4), (0, 4)],
        [(3, 5, 8)],
        [(3, 8, 11), (0, 11)]]
    result_center = [
        [(2, None), (0, 0)],
        [(3, 1, 4), (0, 4)],
        [(3, 5, 8)],
        [(3, 8, 11), (0, 11)]]

class CalcTranslateWordTest5(CalcTranslateTest):
    text = ' Word.'
    width = 3
    mode = 'space'
    result_left = [[(3, 0, 3)], [(3, 3, 6), (0, 6)]]
    result_right = [[(3, 0, 3)], [(3, 3, 6), (0, 6)]]
    result_center = [[(3, 0, 3)], [(3, 3, 6), (0, 6)]]
class CalcTranslateClipTest(CalcTranslateTest):
    text = "It's out of control!\nYou've got to\n\nturn it off!!!"
    mode = 'clip'
    width = 14
    result_left = [
        [(20, 0, 20), (0, 20)],
        [(13, 21, 34), (0, 34)],
        [(0, 35)],
        [(14, 36, 50), (0, 50)]]
    result_right = [
        [(-6, None), (20, 0, 20), (0, 20)],
        [(1, None), (13, 21, 34), (0, 34)],
        [(14, None), (0, 35)],
        [(14, 36, 50), (0, 50)]]
    result_center = [
        [(-3, None), (20, 0, 20), (0, 20)],
        [(1, None), (13, 21, 34), (0, 34)],
        [(7, None), (0, 35)],
        [(14, 36, 50), (0, 50)]]

class CalcTranslateCantDisplayTest(CalcTranslateTest):
    text = B('Hello\xe9\xa2\x96')
    mode = 'space'
    width = 1
    result_left = [[]]
    result_right = [[]]
    result_center = [[]]


class CalcPosTest(unittest.TestCase):
    def setUp(self):
        self.text = "A" * 27
        self.trans = [
            [(2,None),(7,0,7),(0,7)],
            [(13,8,21),(0,21)],
            [(3,None),(5,22,27),(0,27)]]
        self.mytests = [(1,0, 0), (2,0, 0), (11,0, 7),
            (-3,1, 8), (-2,1, 8), (1,1, 9), (31,1, 21),
            (1,2, 22), (11,2, 27) ]

    def tests(self):
        for x,y, expected in self.mytests:
            got = calc_pos( self.text, self.trans, x, y )
            assert got == expected, "%r got:%r expected:%r" % ((x, y), got,
                                                               expected)


class Pos2CoordsTest(unittest.TestCase):
    pos_list = [5, 9, 20, 26]
    text = "1234567890" * 3
    mytests = [
        ( [[(15,0,15)], [(15,15,30),(0,30)]],
            [(5,0),(9,0),(5,1),(11,1)] ),
        ( [[(9,0,9)], [(12,9,21)], [(9,21,30),(0,30)]],
            [(5,0),(0,1),(11,1),(5,2)] ),
        ( [[(2,None), (15,0,15)], [(2,None), (15,15,30),(0,30)]],
            [(7,0),(11,0),(7,1),(13,1)] ),
        ( [[(3, 6, 9),(0,9)], [(5, 20, 25),(0,25)]],
            [(0,0),(3,0),(0,1),(5,1)] ),
        ( [[(10, 0, 10),(0,10)]],
            [(5,0),(9,0),(10,0),(10,0)] ),

        ]

    def test(self):
        for t, answer in self.mytests:
            for pos,a in zip(self.pos_list,answer) :
                r = calc_coords( self.text, t, pos)
                assert r==a, "%r got: %r expected: %r"%(t,r,a)


class CanvasCacheTest(unittest.TestCase):
    def setUp(self):
        # purge the cache
        urwid.CanvasCache._widgets.clear()

    def cct(self, widget, size, focus, expected):
        got = urwid.CanvasCache.fetch(widget, urwid.Widget, size, focus)
        assert expected==got, "got: %s expected: %s"%(got, expected)

    def test1(self):
        a = urwid.Text("")
        b = urwid.Text("")
        blah = urwid.TextCanvas()
        blah.finalize(a, (10,1), False)
        blah2 = urwid.TextCanvas()
        blah2.finalize(a, (15,1), False)
        bloo = urwid.TextCanvas()
        bloo.finalize(b, (20,2), True)

        urwid.CanvasCache.store(urwid.Widget, blah)
        urwid.CanvasCache.store(urwid.Widget, blah2)
        urwid.CanvasCache.store(urwid.Widget, bloo)

        self.cct(a, (10,1), False, blah)
        self.cct(a, (15,1), False, blah2)
        self.cct(a, (15,1), True, None)
        self.cct(a, (10,2), False, None)
        self.cct(b, (20,2), True, bloo)
        self.cct(b, (21,2), True, None)
        urwid.CanvasCache.invalidate(a)
        self.cct(a, (10,1), False, None)
        self.cct(a, (15,1), False, None)
        self.cct(b, (20,2), True, bloo)


class CanvasTest(unittest.TestCase):
    def ct(self, text, attr, exp_content):
        c = urwid.TextCanvas([B(t) for t in text], attr)
        content = list(c.content())
        assert content == exp_content, "got: %r expected: %r" % (content,
                                                                 exp_content)

    def ct2(self, text, attr, left, top, cols, rows, def_attr, exp_content):
        c = urwid.TextCanvas([B(t) for t in text], attr)
        content = list(c.content(left, top, cols, rows, def_attr))
        assert content == exp_content, "got: %r expected: %r" % (content,
                                                                 exp_content)

    def test1(self):
        self.ct(["Hello world"], None, [[(None, None, B("Hello world"))]])
        self.ct(["Hello world"], [[("a",5)]],
            [[("a", None, B("Hello")), (None, None, B(" world"))]])
        self.ct(["Hi","There"], None,
            [[(None, None, B("Hi   "))], [(None, None, B("There"))]])

    def test2(self):
        self.ct2(["Hello"], None, 0, 0, 5, 1, None,
            [[(None, None, B("Hello"))]])
        self.ct2(["Hello"], None, 1, 0, 4, 1, None,
            [[(None, None, B("ello"))]])
        self.ct2(["Hello"], None, 0, 0, 4, 1, None,
            [[(None, None, B("Hell"))]])
        self.ct2(["Hi","There"], None, 1, 0, 3, 2, None,
            [[(None, None, B("i  "))], [(None, None, B("her"))]])
        self.ct2(["Hi","There"], None, 0, 0, 5, 1, None,
            [[(None, None, B("Hi   "))]])
        self.ct2(["Hi","There"], None, 0, 1, 5, 1, None,
            [[(None, None, B("There"))]])

class ShardBodyTest(unittest.TestCase):
    def sbt(self, shards, shard_tail, expected):
        result = shard_body(shards, shard_tail, False)
        assert result == expected, "got: %r expected: %r" % (result, expected)

    def sbttail(self, num_rows, sbody, expected):
        result = shard_body_tail(num_rows, sbody)
        assert result == expected, "got: %r expected: %r" % (result, expected)

    def sbtrow(self, sbody, expected):
        result = list(shard_body_row(sbody))
        assert result == expected, "got: %r expected: %r" % (result, expected)


    def test1(self):
        cviews = [(0,0,10,5,None,"foo"),(0,0,5,5,None,"bar")]
        self.sbt(cviews, [],
            [(0, None, (0,0,10,5,None,"foo")),
            (0, None, (0,0,5,5,None,"bar"))])
        self.sbt(cviews, [(0, 3, None, (0,0,5,8,None,"baz"))],
            [(3, None, (0,0,5,8,None,"baz")),
            (0, None, (0,0,10,5,None,"foo")),
            (0, None, (0,0,5,5,None,"bar"))])
        self.sbt(cviews, [(10, 3, None, (0,0,5,8,None,"baz"))],
            [(0, None, (0,0,10,5,None,"foo")),
            (3, None, (0,0,5,8,None,"baz")),
            (0, None, (0,0,5,5,None,"bar"))])
        self.sbt(cviews, [(15, 3, None, (0,0,5,8,None,"baz"))],
            [(0, None, (0,0,10,5,None,"foo")),
            (0, None, (0,0,5,5,None,"bar")),
            (3, None, (0,0,5,8,None,"baz"))])

    def test2(self):
        sbody = [(0, None, (0,0,10,5,None,"foo")),
            (0, None, (0,0,5,5,None,"bar")),
            (3, None, (0,0,5,8,None,"baz"))]
        self.sbttail(5, sbody, [])
        self.sbttail(3, sbody,
            [(0, 3, None, (0,0,10,5,None,"foo")),
                    (0, 3, None, (0,0,5,5,None,"bar")),
            (0, 6, None, (0,0,5,8,None,"baz"))])

        sbody = [(0, None, (0,0,10,3,None,"foo")),
                        (0, None, (0,0,5,5,None,"bar")),
                        (3, None, (0,0,5,9,None,"baz"))]
        self.sbttail(3, sbody,
            [(10, 3, None, (0,0,5,5,None,"bar")),
            (0, 6, None, (0,0,5,9,None,"baz"))])

    def test3(self):
        self.sbtrow([(0, None, (0,0,10,5,None,"foo")),
            (0, None, (0,0,5,5,None,"bar")),
            (3, None, (0,0,5,8,None,"baz"))],
            [20])
        self.sbtrow([(0, iter("foo"), (0,0,10,5,None,"foo")),
            (0, iter("bar"), (0,0,5,5,None,"bar")),
            (3, iter("zzz"), (0,0,5,8,None,"baz"))],
            ["f","b","z"])



class ShardsTrimTest(unittest.TestCase):
    def sttop(self, shards, top, expected):
        result = shards_trim_top(shards, top)
        assert result == expected, "got: %r expected: %r" (result, expected)

    def strows(self, shards, rows, expected):
        result = shards_trim_rows(shards, rows)
        assert result == expected, "got: %r expected: %r" (result, expected)

    def stsides(self, shards, left, cols, expected):
        result = shards_trim_sides(shards, left, cols)
        assert result == expected, "got: %r expected: %r" (result, expected)


    def test1(self):
        shards = [(5, [(0,0,10,5,None,"foo"),(0,0,5,5,None,"bar")])]
        self.sttop(shards, 2,
            [(3, [(0,2,10,3,None,"foo"),(0,2,5,3,None,"bar")])])
        self.strows(shards, 2,
            [(2, [(0,0,10,2,None,"foo"),(0,0,5,2,None,"bar")])])

        shards = [(5, [(0,0,10,5,None,"foo")]),(3,[(0,0,10,3,None,"bar")])]
        self.sttop(shards, 2,
            [(3, [(0,2,10,3,None,"foo")]),(3,[(0,0,10,3,None,"bar")])])
        self.sttop(shards, 5,
            [(3, [(0,0,10,3,None,"bar")])])
        self.sttop(shards, 7,
            [(1, [(0,2,10,1,None,"bar")])])
        self.strows(shards, 7,
            [(5, [(0,0,10,5,None,"foo")]),(2, [(0,0,10,2,None,"bar")])])
        self.strows(shards, 5,
            [(5, [(0,0,10,5,None,"foo")])])
        self.strows(shards, 4,
            [(4, [(0,0,10,4,None,"foo")])])

        shards = [(5, [(0,0,10,5,None,"foo"), (0,0,5,8,None,"baz")]),
            (3,[(0,0,10,3,None,"bar")])]
        self.sttop(shards, 2,
            [(3, [(0,2,10,3,None,"foo"), (0,2,5,6,None,"baz")]),
            (3,[(0,0,10,3,None,"bar")])])
        self.sttop(shards, 5,
            [(3, [(0,0,10,3,None,"bar"), (0,5,5,3,None,"baz")])])
        self.sttop(shards, 7,
            [(1, [(0,2,10,1,None,"bar"), (0,7,5,1,None,"baz")])])
        self.strows(shards, 7,
            [(5, [(0,0,10,5,None,"foo"), (0,0,5,7,None,"baz")]),
            (2, [(0,0,10,2,None,"bar")])])
        self.strows(shards, 5,
            [(5, [(0,0,10,5,None,"foo"), (0,0,5,5,None,"baz")])])
        self.strows(shards, 4,
            [(4, [(0,0,10,4,None,"foo"), (0,0,5,4,None,"baz")])])


    def test2(self):
        shards = [(5, [(0,0,10,5,None,"foo"),(0,0,5,5,None,"bar")])]
        self.stsides(shards, 0, 15,
            [(5, [(0,0,10,5,None,"foo"),(0,0,5,5,None,"bar")])])
        self.stsides(shards, 6, 9,
            [(5, [(6,0,4,5,None,"foo"),(0,0,5,5,None,"bar")])])
        self.stsides(shards, 6, 6,
            [(5, [(6,0,4,5,None,"foo"),(0,0,2,5,None,"bar")])])
        self.stsides(shards, 0, 10,
            [(5, [(0,0,10,5,None,"foo")])])
        self.stsides(shards, 10, 5,
            [(5, [(0,0,5,5,None,"bar")])])
        self.stsides(shards, 1, 7,
            [(5, [(1,0,7,5,None,"foo")])])

        shards = [(5, [(0,0,10,5,None,"foo"), (0,0,5,8,None,"baz")]),
            (3,[(0,0,10,3,None,"bar")])]
        self.stsides(shards, 0, 15,
            [(5, [(0,0,10,5,None,"foo"), (0,0,5,8,None,"baz")]),
            (3,[(0,0,10,3,None,"bar")])])
        self.stsides(shards, 2, 13,
            [(5, [(2,0,8,5,None,"foo"), (0,0,5,8,None,"baz")]),
            (3,[(2,0,8,3,None,"bar")])])
        self.stsides(shards, 2, 10,
            [(5, [(2,0,8,5,None,"foo"), (0,0,2,8,None,"baz")]),
            (3,[(2,0,8,3,None,"bar")])])
        self.stsides(shards, 2, 8,
            [(5, [(2,0,8,5,None,"foo")]),
            (3,[(2,0,8,3,None,"bar")])])
        self.stsides(shards, 2, 6,
            [(5, [(2,0,6,5,None,"foo")]),
            (3,[(2,0,6,3,None,"bar")])])
        self.stsides(shards, 10, 5,
            [(8, [(0,0,5,8,None,"baz")])])
        self.stsides(shards, 11, 3,
            [(8, [(1,0,3,8,None,"baz")])])

class ShardsJoinTest(unittest.TestCase):
    def sjt(self, shard_lists, expected):
        result = shards_join(shard_lists)
        assert result == expected, "got: %r expected: %r" (result, expected)

    def test(self):
        shards1 = [(5, [(0,0,10,5,None,"foo"), (0,0,5,8,None,"baz")]),
            (3,[(0,0,10,3,None,"bar")])]
        shards2 = [(3, [(0,0,10,3,None,"aaa")]),
            (5,[(0,0,10,5,None,"bbb")])]
        shards3 = [(3, [(0,0,10,3,None,"111")]),
            (2,[(0,0,10,3,None,"222")]),
            (3,[(0,0,10,3,None,"333")])]

        self.sjt([shards1], shards1)
        self.sjt([shards1, shards2],
            [(3, [(0,0,10,5,None,"foo"), (0,0,5,8,None,"baz"),
                (0,0,10,3,None,"aaa")]),
            (2, [(0,0,10,5,None,"bbb")]),
            (3, [(0,0,10,3,None,"bar")])])
        self.sjt([shards1, shards3],
            [(3, [(0,0,10,5,None,"foo"), (0,0,5,8,None,"baz"),
                (0,0,10,3,None,"111")]),
            (2, [(0,0,10,3,None,"222")]),
            (3, [(0,0,10,3,None,"bar"), (0,0,10,3,None,"333")])])
        self.sjt([shards1, shards2, shards3],
            [(3, [(0,0,10,5,None,"foo"), (0,0,5,8,None,"baz"),
                (0,0,10,3,None,"aaa"), (0,0,10,3,None,"111")]),
            (2, [(0,0,10,5,None,"bbb"), (0,0,10,3,None,"222")]),
            (3, [(0,0,10,3,None,"bar"), (0,0,10,3,None,"333")])])


class TagMarkupTest(unittest.TestCase):
    mytests = [
        ("simple one", "simple one", []),
        (('blue',"john"), "john", [('blue',4)]),
        (["a ","litt","le list"], "a little list", []),
        (["mix",('high',[" it ",('ital',"up a")])," little"],
            "mix it up a little",
            [(None,3),('high',4),('ital',4)]),
        ([u"££", u"x££"], u"££x££", []),
        ([B("\xc2\x80"), B("\xc2\x80")], B("\xc2\x80\xc2\x80"), []),
        ]
    def test(self):
        for input, text, attr in self.mytests:
            restext,resattr = urwid.decompose_tagmarkup( input )
            assert restext == text, "got: %r expected: %r" % (restext, text)
            assert resattr == attr, "got: %r expected: %r" % (resattr, attr)

    def test_bad_tuple(self):
        self.assertRaises(urwid.TagMarkupException, lambda:
            urwid.decompose_tagmarkup((1,2,3)))

    def test_bad_type(self):
        self.assertRaises(urwid.TagMarkupException, lambda:
            urwid.decompose_tagmarkup(5))


class TextTest(unittest.TestCase):
    def setUp(self):
        self.t = urwid.Text("I walk the\ncity in the night")

    def test1_wrap(self):
        expected = [B(t) for t in "I walk the","city in   ","the night "]
        got = self.t.render((10,))._text
        assert got == expected, "got: %r expected: %r" % (got, expected)

    def test2_left(self):
        self.t.set_align_mode('left')
        expected = [B(t) for t in "I walk the        ","city in the night "]
        got = self.t.render((18,))._text
        assert got == expected, "got: %r expected: %r" % (got, expected)

    def test3_right(self):
        self.t.set_align_mode('right')
        expected = [B(t) for t in "        I walk the"," city in the night"]
        got = self.t.render((18,))._text
        assert got == expected, "got: %r expected: %r" % (got, expected)

    def test4_center(self):
        self.t.set_align_mode('center')
        expected = [B(t) for t in "    I walk the    "," city in the night"]
        got = self.t.render((18,))._text
        assert got == expected, "got: %r expected: %r" % (got, expected)



class EditTest(unittest.TestCase):
    def setUp(self):
        self.t1 = urwid.Edit(B(""),"blah blah")
        self.t2 = urwid.Edit(B("stuff:"), "blah blah")
        self.t3 = urwid.Edit(B("junk:\n"),"blah blah\n\nbloo",1)
        self.t4 = urwid.Edit(u"better:")

    def ktest(self, e, key, expected, pos, desc):
        got= e.keypress((12,),key)
        assert got == expected, "%s.  got: %r expected:%r" % (desc, got,
                                                              expected)
        assert e.edit_pos == pos, "%s. pos: %r expected pos: " % (
            desc, e.edit_pos, pos)

    def test1_left(self):
        self.t1.set_edit_pos(0)
        self.ktest(self.t1,'left','left',0,"left at left edge")

        self.ktest(self.t2,'left',None,8,"left within text")

        self.t3.set_edit_pos(10)
        self.ktest(self.t3,'left',None,9,"left after newline")

    def test2_right(self):
        self.ktest(self.t1,'right','right',9,"right at right edge")

        self.t2.set_edit_pos(8)
        self.ktest(self.t2,'right',None,9,"right at right edge-1")
        self.t3.set_edit_pos(0)
        self.t3.keypress((12,),'right')
        assert self.t3.get_pref_col((12,)) == 1


    def test3_up(self):
        self.ktest(self.t1,'up','up',9,"up at top")
        self.t2.set_edit_pos(2)
        self.t2.keypress((12,),"left")
        assert self.t2.get_pref_col((12,)) == 7
        self.ktest(self.t2,'up','up',1,"up at top again")
        assert self.t2.get_pref_col((12,)) == 7
        self.t3.set_edit_pos(10)
        self.ktest(self.t3,'up',None,0,"up at top+1")

    def test4_down(self):
        self.ktest(self.t1,'down','down',9,"down single line")
        self.t3.set_edit_pos(5)
        self.ktest(self.t3,'down',None,10,"down line 1 to 2")
        self.ktest(self.t3,'down',None,15,"down line 2 to 3")
        self.ktest(self.t3,'down','down',15,"down at bottom")

    def test_utf8_input(self):
        urwid.set_encoding("utf-8")
        self.t1.set_edit_text('')
        self.t1.keypress((12,), u'û')
        self.assertEquals(self.t1.edit_text, u'û'.encode('utf-8'))
        self.t4.keypress((12,), u'û')
        self.assertEquals(self.t4.edit_text, u'û')


class EditRenderTest(unittest.TestCase):
    def rtest(self, w, expected_text, expected_cursor):
        expected_text = [B(t) for t in expected_text]
        get_cursor = w.get_cursor_coords((4,))
        assert get_cursor == expected_cursor, "got: %r expected: %r" % (
            get_cursor, expected_cursor)
        r = w.render((4,), focus = 1)
        text = [t for a, cs, t in [ln[0] for ln in r.content()]]
        assert text == expected_text, "got: %r expected: %r" % (text,
                                                                expected_text)
        assert r.cursor == expected_cursor, "got: %r expected: %r" % (
            r.cursor, expected_cursor)


    def test1_SpaceWrap(self):
        w = urwid.Edit("","blah blah")
        w.set_edit_pos(0)
        self.rtest(w,["blah","blah"],(0,0))

        w.set_edit_pos(4)
        self.rtest(w,["lah ","blah"],(3,0))

        w.set_edit_pos(5)
        self.rtest(w,["blah","blah"],(0,1))

        w.set_edit_pos(9)
        self.rtest(w,["blah","lah "],(3,1))

    def test2_ClipWrap(self):
        w = urwid.Edit("","blah\nblargh",1)
        w.set_wrap_mode('clip')
        w.set_edit_pos(0)
        self.rtest(w,["blah","blar"],(0,0))

        w.set_edit_pos(10)
        self.rtest(w,["blah","argh"],(3,1))

        w.set_align_mode('right')
        w.set_edit_pos(6)
        self.rtest(w,["blah","larg"],(0,1))

    def test3_AnyWrap(self):
        w = urwid.Edit("","blah blah")
        w.set_wrap_mode('any')

        self.rtest(w,["blah"," bla","h   "],(1,2))

    def test4_CursorNudge(self):
        w = urwid.Edit("","hi",align='right')
        w.keypress((4,),'end')

        self.rtest(w,[" hi "],(3,0))

        w.keypress((4,),'left')
        self.rtest(w,["  hi"],(3,0))



class SelectableText(urwid.Text):
    def selectable(self):
        return 1

    def keypress(self, size, key):
        return key

class ListBoxCalculateVisibleTest(unittest.TestCase):

    def cvtest(self, desc, body, focus, offset_rows, inset_fraction,
        exp_offset_inset, exp_cur ):

        lbox = urwid.ListBox(body)
        lbox.body.set_focus( focus )
        lbox.offset_rows = offset_rows
        lbox.inset_fraction = inset_fraction

        middle, top, bottom = lbox.calculate_visible((4,5),focus=1)
        offset_inset, focus_widget, focus_pos, _ign, cursor = middle

        if cursor is not None:
            x, y = cursor
            y += offset_inset
            cursor = x, y

        assert offset_inset == exp_offset_inset, "%s got: %r expected: %r" %(desc,offset_inset,exp_offset_inset)
        assert cursor == exp_cur, "%s (cursor) got: %r expected: %r" %(desc,cursor,exp_cur)

    def test1_simple(self):
        T = urwid.Text

        l = [T(""),T(""),T("\n"),T("\n\n"),T("\n"),T(""),T("")]

        self.cvtest( "simple top position",
            l, 3, 0, (0,1), 0, None )

        self.cvtest( "simple middle position",
            l, 3, 1, (0,1), 1, None )

        self.cvtest( "simple bottom postion",
            l, 3, 2, (0,1), 2, None )

        self.cvtest( "straddle top edge",
            l, 3, 0, (1,2), -1, None )

        self.cvtest( "straddle bottom edge",
            l, 3, 4, (0,1), 4, None )

        self.cvtest( "off bottom edge",
            l, 3, 5, (0,1), 4, None )

        self.cvtest( "way off bottom edge",
            l, 3, 100, (0,1), 4, None )

        self.cvtest( "gap at top",
            l, 0, 2, (0,1), 0, None )

        self.cvtest( "gap at top and off bottom edge",
            l, 2, 5, (0,1), 2, None )

        self.cvtest( "gap at bottom",
            l, 6, 1, (0,1), 4, None )

        self.cvtest( "gap at bottom and straddling top edge",
            l, 4, 0, (1,2), 1, None )

        self.cvtest( "gap at bottom cannot completely fill",
            [T(""),T(""),T("")], 1, 0, (0,1), 1, None )

        self.cvtest( "gap at top and bottom",
            [T(""),T(""),T("")], 1, 2, (0,1), 1, None )


    def test2_cursor(self):
        T, E = urwid.Text, urwid.Edit

        l1 = [T(""),T(""),T("\n"),E("","\n\nX"),T("\n"),T(""),T("")]
        l2 = [T(""),T(""),T("\n"),E("","YY\n\n"),T("\n"),T(""),T("")]

        l2[3].set_edit_pos(2)

        self.cvtest( "plain cursor in view",
            l1, 3, 1, (0,1), 1, (1,3) )

        self.cvtest( "cursor off top",
            l2, 3, 0, (1,3), 0, (2, 0) )

        self.cvtest( "cursor further off top",
            l2, 3, 0, (2,3), 0, (2, 0) )

        self.cvtest( "cursor off bottom",
            l1, 3, 3, (0,1), 2, (1, 4) )

        self.cvtest( "cursor way off bottom",
            l1, 3, 100, (0,1), 2, (1, 4) )



class ListBoxChangeFocusTest(unittest.TestCase):

    def cftest(self, desc, body, pos, offset_inset,
            coming_from, cursor, snap_rows,
            exp_offset_rows, exp_inset_fraction, exp_cur ):

        lbox = urwid.ListBox(body)

        lbox.change_focus( (4,5), pos, offset_inset, coming_from,
            cursor, snap_rows )

        exp = exp_offset_rows, exp_inset_fraction
        act = lbox.offset_rows, lbox.inset_fraction

        cursor = None
        focus_widget, focus_pos = lbox.body.get_focus()
        if focus_widget.selectable():
            if hasattr(focus_widget,'get_cursor_coords'):
                cursor=focus_widget.get_cursor_coords((4,))

        assert act == exp, "%s got: %s expected: %s" %(desc, act, exp)
        assert cursor == exp_cur, "%s (cursor) got: %r expected: %r" %(desc,cursor,exp_cur)


    def test1unselectable(self):
        T = urwid.Text
        l = [T("\n"),T("\n\n"),T("\n\n"),T("\n\n"),T("\n")]

        self.cftest( "simple unselectable",
            l, 2, 0, None, None, None, 0, (0,1), None )

        self.cftest( "unselectable",
            l, 2, 1, None, None, None, 1, (0,1), None )

        self.cftest( "unselectable off top",
            l, 2, -2, None, None, None, 0, (2,3), None )

        self.cftest( "unselectable off bottom",
            l, 3, 2, None, None, None, 2, (0,1), None )

    def test2selectable(self):
        T, S = urwid.Text, SelectableText
        l = [T("\n"),T("\n\n"),S("\n\n"),T("\n\n"),T("\n")]

        self.cftest( "simple selectable",
            l, 2, 0, None, None, None, 0, (0,1), None )

        self.cftest( "selectable",
            l, 2, 1, None, None, None, 1, (0,1), None )

        self.cftest( "selectable at top",
            l, 2, 0, 'below', None, None, 0, (0,1), None )

        self.cftest( "selectable at bottom",
            l, 2, 2, 'above', None, None, 2, (0,1), None )

        self.cftest( "selectable off top snap",
            l, 2, -1, 'below', None, None, 0, (0,1), None )

        self.cftest( "selectable off bottom snap",
            l, 2, 3, 'above', None, None, 2, (0,1), None )

        self.cftest( "selectable off top no snap",
            l, 2, -1, 'above', None, None, 0, (1,3), None )

        self.cftest( "selectable off bottom no snap",
            l, 2, 3, 'below', None, None, 3, (0,1), None )

    def test3large_selectable(self):
        T, S = urwid.Text, SelectableText
        l = [T("\n"),S("\n\n\n\n\n\n"),T("\n")]
        self.cftest( "large selectable no snap",
            l, 1, -1, None, None, None, 0, (1,7), None )

        self.cftest( "large selectable snap up",
            l, 1, -2, 'below', None, None, 0, (0,1), None )

        self.cftest( "large selectable snap up2",
            l, 1, -2, 'below', None, 2, 0, (0,1), None )

        self.cftest( "large selectable almost snap up",
            l, 1, -2, 'below', None, 1, 0, (2,7), None )

        self.cftest( "large selectable snap down",
            l, 1, 0, 'above', None, None, 0, (2,7), None )

        self.cftest( "large selectable snap down2",
            l, 1, 0, 'above', None, 2, 0, (2,7), None )

        self.cftest( "large selectable almost snap down",
            l, 1, 0, 'above', None, 1, 0, (0,1), None )

        m = [T("\n\n\n\n"), S("\n\n\n\n\n"), T("\n\n\n\n")]
        self.cftest( "large selectable outside view down",
            m, 1, 4, 'above', None, None, 0, (0,1), None )

        self.cftest( "large selectable outside view up",
            m, 1, -5, 'below', None, None, 0, (1,6), None )

    def test4cursor(self):
        T,E = urwid.Text, urwid.Edit
        #...

    def test5set_focus_valign(self):
        T,E = urwid.Text, urwid.Edit
        lbox = urwid.ListBox(urwid.SimpleFocusListWalker([
            T(''), T('')]))
        lbox.set_focus_valign('middle')
        # TODO: actually test the result


class ListBoxRenderTest(unittest.TestCase):

    def ltest(self,desc,body,focus,offset_inset_rows,exp_text,exp_cur):
        exp_text = [B(t) for t in exp_text]
        lbox = urwid.ListBox(body)
        lbox.body.set_focus( focus )
        lbox.shift_focus((4,10), offset_inset_rows )
        canvas = lbox.render( (4,5), focus=1 )

        text = [bytes().join([t for at, cs, t in ln]) for ln in canvas.content()]

        cursor = canvas.cursor

        assert text == exp_text, "%s (text) got: %r expected: %r" %(desc,text,exp_text)
        assert cursor == exp_cur, "%s (cursor) got: %r expected: %r" %(desc,cursor,exp_cur)


    def test1_simple(self):
        T = urwid.Text

        self.ltest( "simple one text item render",
            [T("1\n2")], 0, 0,
            ["1   ","2   ","    ","    ","    "],None)

        self.ltest( "simple multi text item render off bottom",
            [T("1"),T("2"),T("3\n4"),T("5"),T("6")], 2, 2,
            ["1   ","2   ","3   ","4   ","5   "],None)

        self.ltest( "simple multi text item render off top",
            [T("1"),T("2"),T("3\n4"),T("5"),T("6")], 2, 1,
            ["2   ","3   ","4   ","5   ","6   "],None)

    def test2_trim(self):
        T = urwid.Text

        self.ltest( "trim unfocused bottom",
            [T("1\n2"),T("3\n4"),T("5\n6")], 1, 2,
            ["1   ","2   ","3   ","4   ","5   "],None)

        self.ltest( "trim unfocused top",
            [T("1\n2"),T("3\n4"),T("5\n6")], 1, 1,
            ["2   ","3   ","4   ","5   ","6   "],None)

        self.ltest( "trim none full focus",
            [T("1\n2\n3\n4\n5")], 0, 0,
            ["1   ","2   ","3   ","4   ","5   "],None)

        self.ltest( "trim focus bottom",
            [T("1\n2\n3\n4\n5\n6")], 0, 0,
            ["1   ","2   ","3   ","4   ","5   "],None)

        self.ltest( "trim focus top",
            [T("1\n2\n3\n4\n5\n6")], 0, -1,
            ["2   ","3   ","4   ","5   ","6   "],None)

        self.ltest( "trim focus top and bottom",
            [T("1\n2\n3\n4\n5\n6\n7")], 0, -1,
            ["2   ","3   ","4   ","5   ","6   "],None)

    def test3_shift(self):
        T,E = urwid.Text, urwid.Edit

        self.ltest( "shift up one fit",
            [T("1\n2"),T("3"),T("4"),T("5"),T("6")], 4, 5,
            ["2   ","3   ","4   ","5   ","6   "],None)

        e = E("","ab\nc",1)
        e.set_edit_pos( 2 )
        self.ltest( "shift down one cursor over edge",
            [e,T("3"),T("4"),T("5\n6")], 0, -1,
            ["ab  ","c   ","3   ","4   ","5   "], (2,0))

        self.ltest( "shift up one cursor over edge",
            [T("1\n2"),T("3"),T("4"),E("","d\ne")], 3, 4,
            ["2   ","3   ","4   ","d   ","e   "], (1,4))

        self.ltest( "shift none cursor top focus over edge",
            [E("","ab\n"),T("3"),T("4"),T("5\n6")], 0, -1,
            ["    ","3   ","4   ","5   ","6   "], (0,0))

        e = E("","abc\nd")
        e.set_edit_pos( 3 )
        self.ltest( "shift none cursor bottom focus over edge",
            [T("1\n2"),T("3"),T("4"),e], 3, 4,
            ["1   ","2   ","3   ","4   ","abc "], (3,4))

    def test4_really_large_contents(self):
        T,E = urwid.Text, urwid.Edit
        self.ltest("really large edit",
            [T(u"hello"*100)], 0, 0,
            ["hell","ohel","lohe","lloh","ello"], None)

        self.ltest("really large edit",
            [E(u"", u"hello"*100)], 0, 0,
            ["hell","ohel","lohe","lloh","llo "], (3,4))

class ListBoxKeypressTest(unittest.TestCase):

    def ktest(self, desc, key, body, focus, offset_inset,
        exp_focus, exp_offset_inset, exp_cur, lbox = None):

        if lbox is None:
            lbox = urwid.ListBox(body)
            lbox.body.set_focus( focus )
            lbox.shift_focus((4,10), offset_inset )

        ret_key = lbox.keypress((4,5),key)
        middle, top, bottom = lbox.calculate_visible((4,5),focus=1)
        offset_inset, focus_widget, focus_pos, _ign, cursor = middle

        if cursor is not None:
            x, y = cursor
            y += offset_inset
            cursor = x, y

        exp = exp_focus, exp_offset_inset
        act = focus_pos, offset_inset
        assert act == exp, "%s got: %r expected: %r" %(desc,act,exp)
        assert cursor == exp_cur, "%s (cursor) got: %r expected: %r" %(desc,cursor,exp_cur)
        return ret_key,lbox


    def test1_up(self):
        T,S,E = urwid.Text, SelectableText, urwid.Edit

        self.ktest( "direct selectable both visible", 'up',
            [S(""),S("")], 1, 1,
            0, 0, None )

        self.ktest( "selectable skip one all visible", 'up',
            [S(""),T(""),S("")], 2, 2,
            0, 0, None )

        key,lbox = self.ktest( "nothing above no scroll", 'up',
            [S("")], 0, 0,
            0, 0, None )
        assert key == 'up'

        key, lbox = self.ktest( "unselectable above no scroll", 'up',
            [T(""),T(""),S("")], 2, 2,
            2, 2, None )
        assert key == 'up'

        self.ktest( "unselectable above scroll 1", 'up',
            [T(""),S(""),T("\n\n\n")], 1, 0,
            1, 1, None )

        self.ktest( "selectable above scroll 1", 'up',
            [S(""),S(""),T("\n\n\n")], 1, 0,
            0, 0, None )

        self.ktest( "selectable above too far", 'up',
            [S(""),T(""),S(""),T("\n\n\n")], 2, 0,
            2, 1, None )

        self.ktest( "selectable above skip 1 scroll 1", 'up',
            [S(""),T(""),S(""),T("\n\n\n")], 2, 1,
            0, 0, None )

        self.ktest( "tall selectable above scroll 2", 'up',
            [S(""),S("\n"),S(""),T("\n\n\n")], 2, 0,
            1, 0, None )

        self.ktest( "very tall selectable above scroll 5", 'up',
            [S(""),S("\n\n\n\n"),S(""),T("\n\n\n\n")], 2, 0,
            1, 0, None )

        self.ktest( "very tall selected scroll within 1", 'up',
            [S(""),S("\n\n\n\n\n")], 1, -1,
            1, 0, None )

        self.ktest( "edit above pass cursor", 'up',
            [E("","abc"),E("","de")], 1, 1,
            0, 0, (2, 0) )

        key,lbox = self.ktest( "edit too far above pass cursor A", 'up',
            [E("","abc"),T("\n\n\n\n"),E("","de")], 2, 4,
            1, 0, None )

        self.ktest( "edit too far above pass cursor B", 'up',
            None, None, None,
            0, 0, (2,0), lbox )

        self.ktest( "within focus cursor made not visible", 'up',
            [T("\n\n\n"),E("hi\n","ab")], 1, 3,
            0, 0, None )

        self.ktest( "within focus cursor made not visible (2)", 'up',
            [T("\n\n\n\n"),E("hi\n","ab")], 1, 3,
            0, -1, None )

        self.ktest( "force focus unselectable" , 'up',
            [T("\n\n\n\n"),S("")], 1, 4,
            0, 0, None )

        self.ktest( "pathological cursor widget", 'up',
            [T("\n"),E("\n\n\n\n\n","a")], 1, 4,
            0, -1, None )

        self.ktest( "unselectable to unselectable", 'up',
            [T(""),T(""),T(""),T(""),T(""),T(""),T("")], 2, 0,
            1, 0, None )

        self.ktest( "unselectable over edge to same", 'up',
            [T(""),T("12\n34"),T(""),T(""),T(""),T("")],1,-1,
            1, 0, None )

        key,lbox = self.ktest( "edit short between pass cursor A", 'up',
            [E("","abcd"),E("","a"),E("","def")], 2, 2,
            1, 1, (1,1) )

        self.ktest( "edit short between pass cursor B", 'up',
            None, None, None,
            0, 0, (3,0), lbox )

        e = E("","\n\n\n\n\n")
        e.set_edit_pos(1)
        key,lbox = self.ktest( "edit cursor force scroll", 'up',
            [e], 0, -1,
            0, 0, (0,0) )
        assert lbox.inset_fraction[0] == 0

    def test2_down(self):
        T,S,E = urwid.Text, SelectableText, urwid.Edit

        self.ktest( "direct selectable both visible", 'down',
            [S(""),S("")], 0, 0,
            1, 1, None )

        self.ktest( "selectable skip one all visible", 'down',
            [S(""),T(""),S("")], 0, 0,
            2, 2, None )

        key,lbox = self.ktest( "nothing below no scroll", 'down',
            [S("")], 0, 0,
            0, 0, None )
        assert key == 'down'

        key, lbox = self.ktest( "unselectable below no scroll", 'down',
            [S(""),T(""),T("")], 0, 0,
            0, 0, None )
        assert key == 'down'

        self.ktest( "unselectable below scroll 1", 'down',
            [T("\n\n\n"),S(""),T("")], 1, 4,
            1, 3, None )

        self.ktest( "selectable below scroll 1", 'down',
            [T("\n\n\n"),S(""),S("")], 1, 4,
            2, 4, None )

        self.ktest( "selectable below too far", 'down',
            [T("\n\n\n"),S(""),T(""),S("")], 1, 4,
            1, 3, None )

        self.ktest( "selectable below skip 1 scroll 1", 'down',
            [T("\n\n\n"),S(""),T(""),S("")], 1, 3,
            3, 4, None )

        self.ktest( "tall selectable below scroll 2", 'down',
            [T("\n\n\n"),S(""),S("\n"),S("")], 1, 4,
            2, 3, None )

        self.ktest( "very tall selectable below scroll 5", 'down',
            [T("\n\n\n\n"),S(""),S("\n\n\n\n"),S("")], 1, 4,
            2, 0, None )

        self.ktest( "very tall selected scroll within 1", 'down',
            [S("\n\n\n\n\n"),S("")], 0, 0,
            0, -1, None )

        self.ktest( "edit below pass cursor", 'down',
            [E("","de"),E("","abc")], 0, 0,
            1, 1, (2, 1) )

        key,lbox=self.ktest( "edit too far below pass cursor A", 'down',
            [E("","de"),T("\n\n\n\n"),E("","abc")], 0, 0,
            1, 0, None )

        self.ktest( "edit too far below pass cursor B", 'down',
            None, None, None,
            2, 4, (2,4), lbox )

        odd_e = E("","hi\nab")
        odd_e.set_edit_pos( 2 )
        # disble cursor movement in odd_e object
        odd_e.move_cursor_to_coords = lambda s,c,xy: 0
        self.ktest( "within focus cursor made not visible", 'down',
            [odd_e,T("\n\n\n\n")], 0, 0,
            1, 1, None )

        self.ktest( "within focus cursor made not visible (2)", 'down',
            [odd_e,T("\n\n\n\n"),], 0, 0,
            1, 1, None )

        self.ktest( "force focus unselectable" , 'down',
            [S(""),T("\n\n\n\n")], 0, 0,
            1, 0, None )

        odd_e.set_edit_text( "hi\n\n\n\n\n" )
        self.ktest( "pathological cursor widget", 'down',
            [odd_e,T("\n")], 0, 0,
            1, 4, None )

        self.ktest( "unselectable to unselectable", 'down',
            [T(""),T(""),T(""),T(""),T(""),T(""),T("")], 4, 4,
            5, 4, None )

        self.ktest( "unselectable over edge to same", 'down',
            [T(""),T(""),T(""),T(""),T("12\n34"),T("")],4,4,
            4, 3, None )

        key,lbox=self.ktest( "edit short between pass cursor A", 'down',
            [E("","abc"),E("","a"),E("","defg")], 0, 0,
            1, 1, (1,1) )

        self.ktest( "edit short between pass cursor B", 'down',
            None, None, None,
            2, 2, (3,2), lbox )

        e = E("","\n\n\n\n\n")
        e.set_edit_pos(4)
        key,lbox = self.ktest( "edit cursor force scroll", 'down',
            [e], 0, 0,
            0, -1, (0,4) )
        assert lbox.inset_fraction[0] == 1

    def test3_page_up(self):
        T,S,E = urwid.Text, SelectableText, urwid.Edit

        self.ktest( "unselectable aligned to aligned", 'page up',
            [T(""),T("\n"),T("\n\n"),T(""),T("\n"),T("\n\n")], 3, 0,
            1, 0, None )

        self.ktest( "unselectable unaligned to aligned", 'page up',
            [T(""),T("\n"),T("\n"),T("\n"),T("\n"),T("\n\n")], 3,-1,
            1, 0, None )

        self.ktest( "selectable to unselectable", 'page up',
            [T(""),T("\n"),T("\n"),T("\n"),S("\n"),T("\n\n")], 4, 1,
            1, -1, None )

        self.ktest( "selectable to cut off selectable", 'page up',
            [S("\n\n"),T("\n"),T("\n"),S("\n"),T("\n\n")], 3, 1,
            0, -1, None )

        self.ktest( "seletable to selectable", 'page up',
            [T("\n\n"),S("\n"),T("\n"),S("\n"),T("\n\n")], 3, 1,
            1, 1, None )

        self.ktest( "within very long selectable", 'page up',
            [S(""),S("\n\n\n\n\n\n\n\n"),T("\n")], 1, -6,
            1, -1, None )

        e = E("","\n\nab\n\n\n\n\ncd\n")
        e.set_edit_pos(11)
        self.ktest( "within very long cursor widget", 'page up',
            [S(""),e,T("\n")], 1, -6,
            1, -2, (2, 0) )

        self.ktest( "pathological cursor widget", 'page up',
            [T(""),E("\n\n\n\n\n\n\n\n","ab"),T("")], 1, -5,
            0, 0, None )

        e = E("","\nab\n\n\n\n\ncd\n")
        e.set_edit_pos(10)
        self.ktest( "very long cursor widget snap", 'page up',
            [T(""),e,T("\n")], 1, -5,
            1, 0, (2, 1) )

        self.ktest( "slight scroll selectable", 'page up',
            [T("\n"),S("\n"),T(""),S(""),T("\n\n\n"),S("")], 5, 4,
            3, 0, None )

        self.ktest( "scroll into snap region", 'page up',
            [T("\n"),S("\n"),T(""),T(""),T("\n\n\n"),S("")], 5, 4,
            1, 0, None )

        self.ktest( "mid scroll short", 'page up',
            [T("\n"),T(""),T(""),S(""),T(""),T("\n"),S(""),T("\n")],
            6, 2,    3, 1, None )

        self.ktest( "mid scroll long", 'page up',
            [T("\n"),S(""),T(""),S(""),T(""),T("\n"),S(""),T("\n")],
            6, 2,    1, 0, None )

        self.ktest( "mid scroll perfect", 'page up',
            [T("\n"),S(""),S(""),S(""),T(""),T("\n"),S(""),T("\n")],
            6, 2,    2, 0, None )

        self.ktest( "cursor move up fail short", 'page up',
            [T("\n"),T("\n"),E("","\nab"),T(""),T("")], 2, 1,
            2, 4, (0, 4) )

        self.ktest( "cursor force fail short", 'page up',
            [T("\n"),T("\n"),E("\n","ab"),T(""),T("")], 2, 1,
            0, 0, None )

        odd_e = E("","hi\nab")
        odd_e.set_edit_pos( 2 )
        # disble cursor movement in odd_e object
        odd_e.move_cursor_to_coords = lambda s,c,xy: 0
        self.ktest( "cursor force fail long", 'page up',
            [odd_e,T("\n"),T("\n"),T("\n"),S(""),T("\n")], 4, 2,
            1, -1, None )

        self.ktest( "prefer not cut off", 'page up',
            [S("\n"),T("\n"),S(""),T("\n\n"),S(""),T("\n")], 4, 2,
            2, 1, None )

        self.ktest( "allow cut off", 'page up',
            [S("\n"),T("\n"),T(""),T("\n\n"),S(""),T("\n")], 4, 2,
            0, -1, None )

        self.ktest( "at top fail", 'page up',
            [T("\n\n"),T("\n"),T("\n\n\n")], 0, 0,
            0, 0, None )

        self.ktest( "all visible fail", 'page up',
            [T("a"),T("\n")], 0, 0,
            0, 0, None )

        self.ktest( "current ok fail", 'page up',
            [T("\n\n"),S("hi")], 1, 3,
            1, 3, None )

        self.ktest( "all visible choose top selectable", 'page up',
            [T(""),S("a"),S("b"),S("c")], 3, 3,
            1, 1, None )

        self.ktest( "bring in edge choose top", 'page up',
            [S("b"),T("-"),S("-"),T("c"),S("d"),T("-")],4,3,
            0, 0, None )

        self.ktest( "bring in edge choose top selectable", 'page up',
            [T("b"),S("-"),S("-"),T("c"),S("d"),T("-")],4,3,
            1, 1, None )

    def test4_page_down(self):
        T,S,E = urwid.Text, SelectableText, urwid.Edit

        self.ktest( "unselectable aligned to aligned", 'page down',
            [T("\n\n"),T("\n"),T(""),T("\n\n"),T("\n"),T("")], 2, 4,
            4, 3, None )

        self.ktest( "unselectable unaligned to aligned", 'page down',
            [T("\n\n"),T("\n"),T("\n"),T("\n"),T("\n"),T("")], 2, 4,
            4, 3, None )

        self.ktest( "selectable to unselectable", 'page down',
            [T("\n\n"),S("\n"),T("\n"),T("\n"),T("\n"),T("")], 1, 2,
            4, 4, None )

        self.ktest( "selectable to cut off selectable", 'page down',
            [T("\n\n"),S("\n"),T("\n"),T("\n"),S("\n\n")], 1, 2,
            4, 3, None )

        self.ktest( "seletable to selectable", 'page down',
            [T("\n\n"),S("\n"),T("\n"),S("\n"),T("\n\n")], 1, 1,
            3, 2, None )

        self.ktest( "within very long selectable", 'page down',
            [T("\n"),S("\n\n\n\n\n\n\n\n"),S("")], 1, 2,
            1, -3, None )

        e = E("","\nab\n\n\n\n\ncd\n\n")
        e.set_edit_pos(2)
        self.ktest( "within very long cursor widget", 'page down',
            [T("\n"),e,S("")], 1, 2,
            1, -2, (1, 4) )

        odd_e = E("","ab\n\n\n\n\n\n\n\n\n")
        odd_e.set_edit_pos( 1 )
        # disble cursor movement in odd_e object
        odd_e.move_cursor_to_coords = lambda s,c,xy: 0
        self.ktest( "pathological cursor widget", 'page down',
            [T(""),odd_e,T("")], 1, 1,
            2, 4, None )

        e = E("","\nab\n\n\n\n\ncd\n")
        e.set_edit_pos(2)
        self.ktest( "very long cursor widget snap", 'page down',
            [T("\n"),e,T("")], 1, 2,
            1, -3, (1, 3) )

        self.ktest( "slight scroll selectable", 'page down',
            [S(""),T("\n\n\n"),S(""),T(""),S("\n"),T("\n")], 0, 0,
            2, 4, None )

        self.ktest( "scroll into snap region", 'page down',
            [S(""),T("\n\n\n"),T(""),T(""),S("\n"),T("\n")], 0, 0,
            4, 3, None )

        self.ktest( "mid scroll short", 'page down',
            [T("\n"),S(""),T("\n"),T(""),S(""),T(""),T(""),T("\n")],
            1, 2,    4, 3, None )

        self.ktest( "mid scroll long", 'page down',
            [T("\n"),S(""),T("\n"),T(""),S(""),T(""),S(""),T("\n")],
            1, 2,    6, 4, None )

        self.ktest( "mid scroll perfect", 'page down',
            [T("\n"),S(""),T("\n"),T(""),S(""),S(""),S(""),T("\n")],
            1, 2,    5, 4, None )

        e = E("","hi\nab")
        e.set_edit_pos( 1 )
        self.ktest( "cursor move up fail short", 'page down',
            [T(""),T(""),e,T("\n"),T("\n")], 2, 1,
            2, -1, (1, 0) )


        odd_e = E("","hi\nab")
        odd_e.set_edit_pos( 1 )
        # disble cursor movement in odd_e object
        odd_e.move_cursor_to_coords = lambda s,c,xy: 0
        self.ktest( "cursor force fail short", 'page down',
            [T(""),T(""),odd_e,T("\n"),T("\n")], 2, 2,
            4, 3, None )

        self.ktest( "cursor force fail long", 'page down',
            [T("\n"),S(""),T("\n"),T("\n"),T("\n"),E("hi\n","ab")],
            1, 2,    4, 4, None )

        self.ktest( "prefer not cut off", 'page down',
            [T("\n"),S(""),T("\n\n"),S(""),T("\n"),S("\n")], 1, 2,
            3, 3, None )

        self.ktest( "allow cut off", 'page down',
            [T("\n"),S(""),T("\n\n"),T(""),T("\n"),S("\n")], 1, 2,
            5, 4, None )

        self.ktest( "at bottom fail", 'page down',
            [T("\n\n"),T("\n"),T("\n\n\n")], 2, 1,
            2, 1, None )

        self.ktest( "all visible fail", 'page down',
            [T("a"),T("\n")], 1, 1,
            1, 1, None )

        self.ktest( "current ok fail", 'page down',
            [S("hi"),T("\n\n")], 0, 0,
            0, 0, None )

        self.ktest( "all visible choose last selectable", 'page down',
            [S("a"),S("b"),S("c"),T("")], 0, 0,
            2, 2, None )

        self.ktest( "bring in edge choose last", 'page down',
            [T("-"),S("d"),T("c"),S("-"),T("-"),S("b")],1,1,
            5,4, None )

        self.ktest( "bring in edge choose last selectable", 'page down',
            [T("-"),S("d"),T("c"),S("-"),S("-"),T("b")],1,1,
            4,3, None )


class ZeroHeightContentsTest(unittest.TestCase):
    def test_listbox_pile(self):
        lb = urwid.ListBox(urwid.SimpleListWalker(
            [urwid.Pile([])]))
        lb.render((40,10), focus=True)

    def test_listbox_text_pile_page_down(self):
        lb = urwid.ListBox(urwid.SimpleListWalker(
            [urwid.Text(u'above'), urwid.Pile([])]))
        lb.keypress((40,10), 'page down')
        self.assertEquals(lb.get_focus()[1], 0)
        lb.keypress((40,10), 'page down') # second one caused ListBox failure
        self.assertEquals(lb.get_focus()[1], 0)

    def test_listbox_text_pile_page_up(self):
        lb = urwid.ListBox(urwid.SimpleListWalker(
            [urwid.Pile([]), urwid.Text(u'below')]))
        lb.set_focus(1)
        lb.keypress((40,10), 'page up')
        self.assertEquals(lb.get_focus()[1], 1)
        lb.keypress((40,10), 'page up') # second one caused pile failure
        self.assertEquals(lb.get_focus()[1], 1)

    def test_listbox_text_pile_down(self):
        sp = urwid.Pile([])
        sp.selectable = lambda: True # abuse our Pile
        lb = urwid.ListBox(urwid.SimpleListWalker([urwid.Text(u'above'), sp]))
        lb.keypress((40,10), 'down')
        self.assertEquals(lb.get_focus()[1], 0)
        lb.keypress((40,10), 'down')
        self.assertEquals(lb.get_focus()[1], 0)

    def test_listbox_text_pile_up(self):
        sp = urwid.Pile([])
        sp.selectable = lambda: True # abuse our Pile
        lb = urwid.ListBox(urwid.SimpleListWalker([sp, urwid.Text(u'below')]))
        lb.set_focus(1)
        lb.keypress((40,10), 'up')
        self.assertEquals(lb.get_focus()[1], 1)
        lb.keypress((40,10), 'up')
        self.assertEquals(lb.get_focus()[1], 1)

class PaddingTest(unittest.TestCase):
    def ptest(self, desc, align, width, maxcol, left, right,min_width=None):
        p = urwid.Padding(None, align, width, min_width)
        l, r = p.padding_values((maxcol,),False)
        assert (l,r)==(left,right), "%s expected %s but got %s"%(
            desc, (left,right), (l,r))

    def petest(self, desc, align, width):
        self.assertRaises(urwid.PaddingError, lambda:
            urwid.Padding(None, align, width))

    def test_create(self):
        self.petest("invalid pad",6,5)
        self.petest("invalid pad type",('bad',2),5)
        self.petest("invalid width",'center','42')
        self.petest("invalid width type",'center',('gouranga',4))

    def test_values(self):
        self.ptest("left align 5 7",'left',5,7,0,2)
        self.ptest("left align 7 7",'left',7,7,0,0)
        self.ptest("left align 9 7",'left',9,7,0,0)
        self.ptest("right align 5 7",'right',5,7,2,0)
        self.ptest("center align 5 7",'center',5,7,1,1)
        self.ptest("fixed left",('fixed left',3),5,10,3,2)
        self.ptest("fixed left reduce",('fixed left',3),8,10,2,0)
        self.ptest("fixed left shrink",('fixed left',3),18,10,0,0)
        self.ptest("fixed left, right",
            ('fixed left',3),('fixed right',4),17,3,4)
        self.ptest("fixed left, right, min_width",
            ('fixed left',3),('fixed right',4),10,3,2,5)
        self.ptest("fixed left, right, min_width 2",
            ('fixed left',3),('fixed right',4),10,2,0,8)
        self.ptest("fixed right",('fixed right',3),5,10,2,3)
        self.ptest("fixed right reduce",('fixed right',3),8,10,0,2)
        self.ptest("fixed right shrink",('fixed right',3),18,10,0,0)
        self.ptest("fixed right, left",
            ('fixed right',3),('fixed left',4),17,4,3)
        self.ptest("fixed right, left, min_width",
            ('fixed right',3),('fixed left',4),10,2,3,5)
        self.ptest("fixed right, left, min_width 2",
            ('fixed right',3),('fixed left',4),10,0,2,8)
        self.ptest("relative 30",('relative',30),5,10,1,4)
        self.ptest("relative 50",('relative',50),5,10,2,3)
        self.ptest("relative 130 edge",('relative',130),5,10,5,0)
        self.ptest("relative -10 edge",('relative',-10),4,10,0,6)
        self.ptest("center relative 70",'center',('relative',70),
            10,1,2)
        self.ptest("center relative 70 grow 8",'center',('relative',70),
            10,1,1,8)

    def mctest(self, desc, left, right, size, cx, innercx):
        class Inner:
            def __init__(self, desc, innercx):
                self.desc = desc
                self.innercx = innercx
            def move_cursor_to_coords(self,size,cx,cy):
                assert cx==self.innercx, desc
        i = Inner(desc,innercx)
        p = urwid.Padding(i, ('fixed left',left),
            ('fixed right',right))
        p.move_cursor_to_coords(size, cx, 0)

    def test_cursor(self):
        self.mctest("cursor left edge",2,2,(10,2),2,0)
        self.mctest("cursor left edge-1",2,2,(10,2),1,0)
        self.mctest("cursor right edge",2,2,(10,2),7,5)
        self.mctest("cursor right edge+1",2,2,(10,2),8,5)

    def test_reduced_padding_cursor(self):
        # FIXME: This is at least consistent now, but I don't like it.
        # pack() on an Edit should leave room for the cursor
        # fixing this gets deep into things like Edit._shift_view_to_cursor
        # though, so this might not get fixed for a while

        p = urwid.Padding(urwid.Edit(u'',u''), width='pack', left=4)
        self.assertEquals(p.render((10,), True).cursor, None)
        self.assertEquals(p.get_cursor_coords((10,)), None)
        self.assertEquals(p.render((4,), True).cursor, None)
        self.assertEquals(p.get_cursor_coords((4,)), None)

        p = urwid.Padding(urwid.Edit(u'',u''), width=('relative', 100), left=4)
        self.assertEquals(p.render((10,), True).cursor, (4, 0))
        self.assertEquals(p.get_cursor_coords((10,)), (4, 0))
        self.assertEquals(p.render((4,), True).cursor, None)
        self.assertEquals(p.get_cursor_coords((4,)), None)




class FillerTest(unittest.TestCase):
    def ftest(self, desc, valign, height, maxrow, top, bottom,
            min_height=None):
        f = urwid.Filler(None, valign, height, min_height)
        t, b = f.filler_values((20,maxrow), False)
        assert (t,b)==(top,bottom), "%s expected %s but got %s"%(
            desc, (top,bottom), (t,b))

    def fetest(self, desc, valign, height):
        self.assertRaises(urwid.FillerError, lambda:
            urwid.Filler(None, valign, height))

    def test_create(self):
        self.fetest("invalid pad",6,5)
        self.fetest("invalid pad type",('bad',2),5)
        self.fetest("invalid width",'middle','42')
        self.fetest("invalid width type",'middle',('gouranga',4))
        self.fetest("invalid combination",('relative',20),
            ('fixed bottom',4))
        self.fetest("invalid combination 2",('relative',20),
            ('fixed top',4))

    def test_values(self):
        self.ftest("top align 5 7",'top',5,7,0,2)
        self.ftest("top align 7 7",'top',7,7,0,0)
        self.ftest("top align 9 7",'top',9,7,0,0)
        self.ftest("bottom align 5 7",'bottom',5,7,2,0)
        self.ftest("middle align 5 7",'middle',5,7,1,1)
        self.ftest("fixed top",('fixed top',3),5,10,3,2)
        self.ftest("fixed top reduce",('fixed top',3),8,10,2,0)
        self.ftest("fixed top shrink",('fixed top',3),18,10,0,0)
        self.ftest("fixed top, bottom",
            ('fixed top',3),('fixed bottom',4),17,3,4)
        self.ftest("fixed top, bottom, min_width",
            ('fixed top',3),('fixed bottom',4),10,3,2,5)
        self.ftest("fixed top, bottom, min_width 2",
            ('fixed top',3),('fixed bottom',4),10,2,0,8)
        self.ftest("fixed bottom",('fixed bottom',3),5,10,2,3)
        self.ftest("fixed bottom reduce",('fixed bottom',3),8,10,0,2)
        self.ftest("fixed bottom shrink",('fixed bottom',3),18,10,0,0)
        self.ftest("fixed bottom, top",
            ('fixed bottom',3),('fixed top',4),17,4,3)
        self.ftest("fixed bottom, top, min_height",
            ('fixed bottom',3),('fixed top',4),10,2,3,5)
        self.ftest("fixed bottom, top, min_height 2",
            ('fixed bottom',3),('fixed top',4),10,0,2,8)
        self.ftest("relative 30",('relative',30),5,10,1,4)
        self.ftest("relative 50",('relative',50),5,10,2,3)
        self.ftest("relative 130 edge",('relative',130),5,10,5,0)
        self.ftest("relative -10 edge",('relative',-10),4,10,0,6)
        self.ftest("middle relative 70",'middle',('relative',70),
            10,1,2)
        self.ftest("middle relative 70 grow 8",'middle',('relative',70),
            10,1,1,8)

    def test_repr(self):
        repr(urwid.Filler(urwid.Text(u'hai')))

class FrameTest(unittest.TestCase):

    def ftbtest(self, desc, focus_part, header_rows, footer_rows, size,
            focus, top, bottom):
        class FakeWidget:
            def __init__(self, rows, want_focus):
                self.ret_rows = rows
                self.want_focus = want_focus
            def rows(self, size, focus=False):
                assert self.want_focus == focus
                return self.ret_rows
        header = footer = None
        if header_rows:
            header = FakeWidget(header_rows,
                focus and focus_part == 'header')
        if footer_rows:
            footer = FakeWidget(footer_rows,
                focus and focus_part == 'footer')

        f = urwid.Frame(None, header, footer, focus_part)

        rval = f.frame_top_bottom(size, focus)
        exp = (top, bottom), (header_rows, footer_rows)
        assert exp == rval, "%s expected %r but got %r"%(
            desc,exp,rval)

    def test(self):
        self.ftbtest("simple", 'body', 0, 0, (9, 10), True, 0, 0)
        self.ftbtest("simple h", 'body', 3, 0, (9, 10), True, 3, 0)
        self.ftbtest("simple f", 'body', 0, 3, (9, 10), True, 0, 3)
        self.ftbtest("simple hf", 'body', 3, 3, (9, 10), True, 3, 3)
        self.ftbtest("almost full hf", 'body', 4, 5, (9, 10),
            True, 4, 5)
        self.ftbtest("full hf", 'body', 5, 5, (9, 10),
            True, 4, 5)
        self.ftbtest("x full h+1f", 'body', 6, 5, (9, 10),
            False, 4, 5)
        self.ftbtest("full h+1f", 'body', 6, 5, (9, 10),
            True, 4, 5)
        self.ftbtest("full hf+1", 'body', 5, 6, (9, 10),
            True, 3, 6)
        self.ftbtest("F full h+1f", 'footer', 6, 5, (9, 10),
            True, 5, 5)
        self.ftbtest("F full hf+1", 'footer', 5, 6, (9, 10),
            True, 4, 6)
        self.ftbtest("F full hf+5", 'footer', 5, 11, (9, 10),
            True, 0, 10)
        self.ftbtest("full hf+5", 'body', 5, 11, (9, 10),
            True, 0, 9)
        self.ftbtest("H full hf+1", 'header', 5, 6, (9, 10),
            True, 5, 5)
        self.ftbtest("H full h+1f", 'header', 6, 5, (9, 10),
            True, 6, 4)
        self.ftbtest("H full h+5f", 'header', 11, 5, (9, 10),
            True, 10, 0)


class PileTest(unittest.TestCase):
    def ktest(self, desc, l, focus_item, key,
            rkey, rfocus, rpref_col):
        p = urwid.Pile( l, focus_item )
        rval = p.keypress( (20,), key )
        assert rkey == rval, "%s key expected %r but got %r" %(
            desc, rkey, rval)
        new_focus = l.index(p.get_focus())
        assert new_focus == rfocus, "%s focus expected %r but got %r" %(
            desc, rfocus, new_focus)
        new_pref = p.get_pref_col((20,))
        assert new_pref == rpref_col, (
            "%s pref_col expected %r but got %r" % (
            desc, rpref_col, new_pref))

    def test_select_change(self):
        T,S,E = urwid.Text, SelectableText, urwid.Edit

        self.ktest("simple up", [S("")], 0, "up", "up", 0, 0)
        self.ktest("simple down", [S("")], 0, "down", "down", 0, 0)
        self.ktest("ignore up", [T(""),S("")], 1, "up", "up", 1, 0)
        self.ktest("ignore down", [S(""),T("")], 0, "down",
            "down", 0, 0)
        self.ktest("step up", [S(""),S("")], 1, "up", None, 0, 0)
        self.ktest("step down", [S(""),S("")], 0, "down",
            None, 1, 0)
        self.ktest("skip step up", [S(""),T(""),S("")], 2, "up",
            None, 0, 0)
        self.ktest("skip step down", [S(""),T(""),S("")], 0, "down",
            None, 2, 0)
        self.ktest("pad skip step up", [T(""),S(""),T(""),S("")], 3,
            "up", None, 1, 0)
        self.ktest("pad skip step down", [S(""),T(""),S(""),T("")], 0,
            "down", None, 2, 0)
        self.ktest("padi skip step up", [S(""),T(""),S(""),T(""),S("")],
            4, "up", None, 2, 0)
        self.ktest("padi skip step down", [S(""),T(""),S(""),T(""),
            S("")], 0, "down", None, 2, 0)
        e = E("","abcd", edit_pos=1)
        e.keypress((20,),"right") # set a pref_col
        self.ktest("pref step up", [S(""),T(""),e], 2, "up",
            None, 0, 2)
        self.ktest("pref step down", [e,T(""),S("")], 0, "down",
            None, 2, 2)
        z = E("","1234")
        self.ktest("prefx step up", [z,T(""),e], 2, "up",
            None, 0, 2)
        assert z.get_pref_col((20,)) == 2
        z = E("","1234")
        self.ktest("prefx step down", [e,T(""),z], 0, "down",
            None, 2, 2)
        assert z.get_pref_col((20,)) == 2

    def test_init_with_a_generator(self):
        urwid.Pile(urwid.Text(c) for c in "ABC")

    def test_change_focus_with_mouse(self):
        p = urwid.Pile([urwid.Edit(), urwid.Edit()])
        self.assertEquals(p.focus_position, 0)
        p.mouse_event((10,), 'button press', 1, 1, 1, True)
        self.assertEquals(p.focus_position, 1)


class ColumnsTest(unittest.TestCase):
    def cwtest(self, desc, l, divide, size, exp, focus_column=0):
        c = urwid.Columns(l, divide, focus_column)
        rval = c.column_widths( size )
        assert rval == exp, "%s expected %s, got %s"%(desc,exp,rval)

    def test_widths(self):
        x = urwid.Text("") # sample "column"
        self.cwtest( "simple 1", [x], 0, (20,), [20] )
        self.cwtest( "simple 2", [x,x], 0, (20,), [10,10] )
        self.cwtest( "simple 2+1", [x,x], 1, (20,), [10,9] )
        self.cwtest( "simple 3+1", [x,x,x], 1, (20,), [6,6,6] )
        self.cwtest( "simple 3+2", [x,x,x], 2, (20,), [5,6,5] )
        self.cwtest( "simple 3+2", [x,x,x], 2, (21,), [6,6,5] )
        self.cwtest( "simple 4+1", [x,x,x,x], 1, (25,), [6,5,6,5] )
        self.cwtest( "squish 4+1", [x,x,x,x], 1, (7,), [1,1,1,1] )
        self.cwtest( "squish 4+1", [x,x,x,x], 1, (6,), [1,2,1] )
        self.cwtest( "squish 4+1", [x,x,x,x], 1, (4,), [2,1] )

        self.cwtest( "fixed 3", [('fixed',4,x),('fixed',6,x),
            ('fixed',2,x)], 1, (25,), [4,6,2] )
        self.cwtest( "fixed 3 cut", [('fixed',4,x),('fixed',6,x),
            ('fixed',2,x)], 1, (13,), [4,6] )
        self.cwtest( "fixed 3 cut2", [('fixed',4,x),('fixed',6,x),
            ('fixed',2,x)], 1, (10,), [4] )

        self.cwtest( "mixed 4", [('weight',2,x),('fixed',5,x),
            x, ('weight',3,x)], 1, (14,), [2,5,1,3] )
        self.cwtest( "mixed 4 a", [('weight',2,x),('fixed',5,x),
            x, ('weight',3,x)], 1, (12,), [1,5,1,2] )
        self.cwtest( "mixed 4 b", [('weight',2,x),('fixed',5,x),
            x, ('weight',3,x)], 1, (10,), [2,5,1] )
        self.cwtest( "mixed 4 c", [('weight',2,x),('fixed',5,x),
            x, ('weight',3,x)], 1, (20,), [4,5,2,6] )

    def test_widths_focus_end(self):
        x = urwid.Text("") # sample "column"
        self.cwtest("end simple 2", [x,x], 0, (20,), [10,10], 1)
        self.cwtest("end simple 2+1", [x,x], 1, (20,), [10,9], 1)
        self.cwtest("end simple 3+1", [x,x,x], 1, (20,), [6,6,6], 2)
        self.cwtest("end simple 3+2", [x,x,x], 2, (20,), [5,6,5], 2)
        self.cwtest("end simple 3+2", [x,x,x], 2, (21,), [6,6,5], 2)
        self.cwtest("end simple 4+1", [x,x,x,x], 1, (25,), [6,5,6,5], 3)
        self.cwtest("end squish 4+1", [x,x,x,x], 1, (7,), [1,1,1,1], 3)
        self.cwtest("end squish 4+1", [x,x,x,x], 1, (6,), [0,1,2,1], 3)
        self.cwtest("end squish 4+1", [x,x,x,x], 1, (4,), [0,0,2,1], 3)

        self.cwtest("end fixed 3", [('fixed',4,x),('fixed',6,x),
            ('fixed',2,x)], 1, (25,), [4,6,2], 2)
        self.cwtest("end fixed 3 cut", [('fixed',4,x),('fixed',6,x),
            ('fixed',2,x)], 1, (13,), [0,6,2], 2)
        self.cwtest("end fixed 3 cut2", [('fixed',4,x),('fixed',6,x),
            ('fixed',2,x)], 1, (8,), [0,0,2], 2)

        self.cwtest("end mixed 4", [('weight',2,x),('fixed',5,x),
            x, ('weight',3,x)], 1, (14,), [2,5,1,3], 3)
        self.cwtest("end mixed 4 a", [('weight',2,x),('fixed',5,x),
            x, ('weight',3,x)], 1, (12,), [1,5,1,2], 3)
        self.cwtest("end mixed 4 b", [('weight',2,x),('fixed',5,x),
            x, ('weight',3,x)], 1, (10,), [0,5,1,2], 3)
        self.cwtest("end mixed 4 c", [('weight',2,x),('fixed',5,x),
            x, ('weight',3,x)], 1, (20,), [4,5,2,6], 3)

    def mctest(self, desc, l, divide, size, col, row, exp, f_col, pref_col):
        c = urwid.Columns( l, divide )
        rval = c.move_cursor_to_coords( size, col, row )
        assert rval == exp, "%s expected %r, got %r"%(desc,exp,rval)
        assert c.focus_col == f_col, "%s expected focus_col %s got %s"%(
            desc, f_col, c.focus_col)
        pc = c.get_pref_col( size )
        assert pc == pref_col, "%s expected pref_col %s, got %s"%(
            desc, pref_col, pc)

    def test_move_cursor(self):
        e, s, x = urwid.Edit("",""),SelectableText(""), urwid.Text("")
        self.mctest("nothing selectbl",[x,x,x],1,(20,),9,0,False,0,None)
        self.mctest("dead on",[x,s,x],1,(20,),9,0,True,1,9)
        self.mctest("l edge",[x,s,x],1,(20,),6,0,True,1,6)
        self.mctest("r edge",[x,s,x],1,(20,),13,0,True,1,13)
        self.mctest("l off",[x,s,x],1,(20,),2,0,True,1,2)
        self.mctest("r off",[x,s,x],1,(20,),17,0,True,1,17)
        self.mctest("l off 2",[x,x,s],1,(20,),2,0,True,2,2)
        self.mctest("r off 2",[s,x,x],1,(20,),17,0,True,0,17)

        self.mctest("l between",[s,s,x],1,(20,),6,0,True,0,6)
        self.mctest("r between",[x,s,s],1,(20,),13,0,True,1,13)
        self.mctest("l between 2l",[s,s,x],2,(22,),6,0,True,0,6)
        self.mctest("r between 2l",[x,s,s],2,(22,),14,0,True,1,14)
        self.mctest("l between 2r",[s,s,x],2,(22,),7,0,True,1,7)
        self.mctest("r between 2r",[x,s,s],2,(22,),15,0,True,2,15)

        # unfortunate pref_col shifting
        self.mctest("l e edge",[x,e,x],1,(20,),6,0,True,1,7)
        self.mctest("r e edge",[x,e,x],1,(20,),13,0,True,1,12)

    def test_init_with_a_generator(self):
        urwid.Columns(urwid.Text(c) for c in "ABC")

    def test_old_attributes(self):
        c = urwid.Columns([urwid.Text(u'a'), urwid.SolidFill(u'x')],
            box_columns=[1])
        self.assertEquals(c.box_columns, [1])
        c.box_columns=[]
        self.assertEquals(c.box_columns, [])

    def test_box_column(self):
        c = urwid.Columns([urwid.Filler(urwid.Edit()),urwid.Text('')],
            box_columns=[0])
        c.keypress((10,), 'x')
        c.get_cursor_coords((10,))
        c.move_cursor_to_coords((10,), 0, 0)
        c.mouse_event((10,), 'foo', 1, 0, 0, True)
        c.get_pref_col((10,))


class LineBoxTest(unittest.TestCase):
    def border(self, tl, t, tr, l, r, bl, b, br):
        return [bytes().join([tl, t, tr]),
                bytes().join([l, B(" "), r]),
                bytes().join([bl, b, br]),]

    def test_linebox_border(self):
        urwid.set_encoding("utf-8")
        t = urwid.Text("")

        l = urwid.LineBox(t).render((3,)).text

        # default
        self.assertEqual(l,
            self.border(B("\xe2\x94\x8c"), B("\xe2\x94\x80"),
                B("\xe2\x94\x90"), B("\xe2\x94\x82"), B("\xe2\x94\x82"),
                B("\xe2\x94\x94"), B("\xe2\x94\x80"), B("\xe2\x94\x98")))

        nums = [B(str(n)) for n in range(8)]
        b = dict(zip(["tlcorner", "tline", "trcorner", "lline", "rline",
            "blcorner", "bline", "brcorner"], nums))
        l = urwid.LineBox(t, **b).render((3,)).text

        self.assertEqual(l, self.border(*nums))


class BarGraphTest(unittest.TestCase):
    def bgtest(self, desc, data, top, widths, maxrow, exp ):
        rval = calculate_bargraph_display(data,top,widths,maxrow)
        assert rval == exp, "%s expected %r, got %r"%(desc,exp,rval)

    def test1(self):
        self.bgtest('simplest',[[0]],5,[1],1,
            [(1,[(0,1)])] )
        self.bgtest('simpler',[[0],[0]],5,[1,2],5,
            [(5,[(0,3)])] )
        self.bgtest('simple',[[5]],5,[1],1,
            [(1,[(1,1)])] )
        self.bgtest('2col-1',[[2],[0]],5,[1,2],5,
            [(3,[(0,3)]), (2,[(1,1),(0,2)]) ] )
        self.bgtest('2col-2',[[0],[2]],5,[1,2],5,
            [(3,[(0,3)]), (2,[(0,1),(1,2)]) ] )
        self.bgtest('2col-3',[[2],[3]],5,[1,2],5,
            [(2,[(0,3)]), (1,[(0,1),(1,2)]), (2,[(1,3)]) ] )
        self.bgtest('3col-1',[[5],[3],[0]],5,[2,1,1],5,
            [(2,[(1,2),(0,2)]), (3,[(1,3),(0,1)]) ] )
        self.bgtest('3col-2',[[4],[4],[4]],5,[2,1,1],5,
            [(1,[(0,4)]), (4,[(1,4)]) ] )
        self.bgtest('3col-3',[[1],[2],[3]],5,[2,1,1],5,
            [(2,[(0,4)]), (1,[(0,3),(1,1)]), (1,[(0,2),(1,2)]),
             (1,[(1,4)]) ] )
        self.bgtest('3col-4',[[4],[2],[4]],5,[1,2,1],5,
            [(1,[(0,4)]), (2,[(1,1),(0,2),(1,1)]), (2,[(1,4)]) ] )

    def test2(self):
        self.bgtest('simple1a',[[2,0],[2,1]],2,[1,1],2,
            [(1,[(1,2)]),(1,[(1,1),(2,1)]) ] )
        self.bgtest('simple1b',[[2,1],[2,0]],2,[1,1],2,
            [(1,[(1,2)]),(1,[(2,1),(1,1)]) ] )
        self.bgtest('cross1a',[[2,2],[1,2]],2,[1,1],2,
            [(2,[(2,2)]) ] )
        self.bgtest('cross1b',[[1,2],[2,2]],2,[1,1],2,
            [(2,[(2,2)]) ] )
        self.bgtest('mix1a',[[3,2,1],[2,2,2],[1,2,3]],3,[1,1,1],3,
            [(1,[(1,1),(0,1),(3,1)]),(1,[(2,1),(3,2)]),
             (1,[(3,3)]) ] )
        self.bgtest('mix1b',[[1,2,3],[2,2,2],[3,2,1]],3,[1,1,1],3,
            [(1,[(3,1),(0,1),(1,1)]),(1,[(3,2),(2,1)]),
             (1,[(3,3)]) ] )

class SmoothBarGraphTest(unittest.TestCase):
    def sbgtest(self, desc, data, top, exp ):
        urwid.set_encoding('utf-8')
        g = urwid.BarGraph( ['black','red','blue'],
                None, {(1,0):'red/black', (2,1):'blue/red'})
        g.set_data( data, top )
        rval = g.calculate_display((5,3))
        assert rval == exp, "%s expected %r, got %r"%(desc,exp,rval)

    def test1(self):
        self.sbgtest('simple', [[3]], 5,
            [(1, [(0, 5)]), (1, [((1, 0, 6), 5)]), (1, [(1, 5)])] )
        self.sbgtest('boring', [[4,2]], 6,
            [(1, [(0, 5)]), (1, [(1, 5)]), (1, [(2,5)]) ] )
        self.sbgtest('two', [[4],[2]], 6,
            [(1, [(0, 5)]), (1, [(1, 3), (0, 2)]), (1, [(1, 5)]) ] )
        self.sbgtest('twos', [[3],[4]], 6,
            [(1, [(0, 5)]), (1, [((1,0,4), 3), (1, 2)]), (1, [(1,5)]) ] )
        self.sbgtest('twof', [[4],[3]], 6,
            [(1, [(0, 5)]), (1, [(1,3), ((1,0,4), 2)]), (1, [(1,5)]) ] )


class OverlayTest(unittest.TestCase):
    def test_old_params(self):
        o1 = urwid.Overlay(urwid.SolidFill(u'X'), urwid.SolidFill(u'O'),
            ('fixed left', 5), ('fixed right', 4),
            ('fixed top', 3), ('fixed bottom', 2),)
        self.assertEquals(o1.contents[1][1], (
            'left', None, 'relative', 100, None, 5, 4,
            'top', None, 'relative', 100, None, 3, 2))
        o2 = urwid.Overlay(urwid.SolidFill(u'X'), urwid.SolidFill(u'O'),
            ('fixed right', 5), ('fixed left', 4),
            ('fixed bottom', 3), ('fixed top', 2),)
        self.assertEquals(o2.contents[1][1], (
            'right', None, 'relative', 100, None, 4, 5,
            'bottom', None, 'relative', 100, None, 2, 3))

    def test_get_cursor_coords(self):
        self.assertEquals(urwid.Overlay(urwid.Filler(urwid.Edit()),
            urwid.SolidFill(u'B'),
            'right', 1, 'bottom', 1).get_cursor_coords((2,2)), (1,1))


class GridFlowTest(unittest.TestCase):
    def test_cell_width(self):
        gf = urwid.GridFlow([], 5, 0, 0, 'left')
        self.assertEquals(gf.cell_width, 5)

    def test_basics(self):
        repr(urwid.GridFlow([], 5, 0, 0, 'left')) # should not fail


class CanvasJoinTest(unittest.TestCase):
    def cjtest(self, desc, l, expected):
        l = [(c, None, False, n) for c, n in l]
        result = list(urwid.CanvasJoin(l).content())

        assert result == expected, "%s expected %r, got %r"%(
            desc, expected, result)

    def test(self):
        C = urwid.TextCanvas
        hello = C([B("hello")])
        there = C([B("there")], [[("a",5)]])
        a = C([B("a")])
        hi = C([B("hi")])
        how = C([B("how")], [[("a",1)]])
        dy = C([B("dy")])
        how_you = C([B("how"), B("you")])

        self.cjtest("one", [(hello, 5)],
            [[(None, None, B("hello"))]])
        self.cjtest("two", [(hello, 5), (there, 5)],
            [[(None, None, B("hello")), ("a", None, B("there"))]])
        self.cjtest("two space", [(hello, 7), (there, 5)],
            [[(None, None, B("hello")),(None,None,B("  ")),
            ("a", None, B("there"))]])
        self.cjtest("three space", [(hi, 4), (how, 3), (dy, 2)],
            [[(None, None, B("hi")),(None,None,B("  ")),("a",None, B("h")),
            (None,None,B("ow")),(None,None,B("dy"))]])
        self.cjtest("four space", [(a, 2), (hi, 3), (dy, 3), (a, 1)],
            [[(None, None, B("a")),(None,None,B(" ")),
            (None, None, B("hi")),(None,None,B(" ")),
            (None, None, B("dy")),(None,None,B(" ")),
            (None, None, B("a"))]])
        self.cjtest("pile 2", [(how_you, 4), (hi, 2)],
            [[(None, None, B('how')), (None, None, B(' ')),
            (None, None, B('hi'))],
            [(None, None, B('you')), (None, None, B(' ')),
            (None, None, B('  '))]])
        self.cjtest("pile 2r", [(hi, 4), (how_you, 3)],
            [[(None, None, B('hi')), (None, None, B('  ')),
            (None, None, B('how'))],
            [(None, None, B('    ')),
            (None, None, B('you'))]])

class CanvasOverlayTest(unittest.TestCase):
    def cotest(self, desc, bgt, bga, fgt, fga, l, r, et):
        bgt = B(bgt)
        fgt = B(fgt)
        bg = urwid.CompositeCanvas(
            urwid.TextCanvas([bgt],[bga]))
        fg = urwid.CompositeCanvas(
            urwid.TextCanvas([fgt],[fga]))
        bg.overlay(fg, l, 0)
        result = list(bg.content())
        assert result == et, "%s expected %r, got %r"%(
            desc, et, result)

    def test1(self):
        self.cotest("left", "qxqxqxqx", [], "HI", [], 0, 6,
            [[(None, None, B("HI")),(None,None,B("qxqxqx"))]])
        self.cotest("right", "qxqxqxqx", [], "HI", [], 6, 0,
            [[(None, None, B("qxqxqx")),(None,None,B("HI"))]])
        self.cotest("center", "qxqxqxqx", [], "HI", [], 3, 3,
            [[(None, None, B("qxq")),(None,None,B("HI")),
            (None,None,B("xqx"))]])
        self.cotest("center2", "qxqxqxqx", [], "HI  ", [], 2, 2,
            [[(None, None, B("qx")),(None,None,B("HI  ")),
            (None,None,B("qx"))]])
        self.cotest("full", "rz", [], "HI", [], 0, 0,
            [[(None, None, B("HI"))]])

    def test2(self):
        self.cotest("same","asdfghjkl",[('a',9)],"HI",[('a',2)],4,3,
            [[('a',None,B("asdf")),('a',None,B("HI")),('a',None,B("jkl"))]])
        self.cotest("diff","asdfghjkl",[('a',9)],"HI",[('b',2)],4,3,
            [[('a',None,B("asdf")),('b',None,B("HI")),('a',None,B("jkl"))]])
        self.cotest("None end","asdfghjkl",[('a',9)],"HI  ",[('a',2)],
            2,3,
            [[('a',None,B("as")),('a',None,B("HI")),
            (None,None,B("  ")),('a',None,B("jkl"))]])
        self.cotest("float end","asdfghjkl",[('a',3)],"HI",[('a',2)],
            4,3,
            [[('a',None,B("asd")),(None,None,B("f")),
            ('a',None,B("HI")),(None,None,B("jkl"))]])
        self.cotest("cover 2","asdfghjkl",[('a',5),('c',4)],"HI",
            [('b',2)],4,3,
            [[('a',None,B("asdf")),('b',None,B("HI")),('c',None,B("jkl"))]])
        self.cotest("cover 2-2","asdfghjkl",
            [('a',4),('d',1),('e',1),('c',3)],
            "HI",[('b',2)], 4, 3,
            [[('a',None,B("asdf")),('b',None,B("HI")),('c',None,B("jkl"))]])

    def test3(self):
        urwid.set_encoding("euc-jp")
        self.cotest("db0","\xA1\xA1\xA1\xA1\xA1\xA1",[],"HI",[],2,2,
            [[(None,None,B("\xA1\xA1")),(None,None,B("HI")),
            (None,None,B("\xA1\xA1"))]])
        self.cotest("db1","\xA1\xA1\xA1\xA1\xA1\xA1",[],"OHI",[],1,2,
            [[(None,None,B(" ")),(None,None,B("OHI")),
            (None,None,B("\xA1\xA1"))]])
        self.cotest("db2","\xA1\xA1\xA1\xA1\xA1\xA1",[],"OHI",[],2,1,
            [[(None,None,B("\xA1\xA1")),(None,None,B("OHI")),
            (None,None,B(" "))]])
        self.cotest("db3","\xA1\xA1\xA1\xA1\xA1\xA1",[],"OHIO",[],1,1,
            [[(None,None,B(" ")),(None,None,B("OHIO")),(None,None,B(" "))]])

class CanvasPadTrimTest(unittest.TestCase):
    def cptest(self, desc, ct, ca, l, r, et):
        ct = B(ct)
        c = urwid.CompositeCanvas(
            urwid.TextCanvas([ct], [ca]))
        c.pad_trim_left_right(l, r)
        result = list(c.content())
        assert result == et, "%s expected %r, got %r"%(
            desc, et, result)

    def test1(self):
        self.cptest("none", "asdf", [], 0, 0,
            [[(None,None,B("asdf"))]])
        self.cptest("left pad", "asdf", [], 2, 0,
            [[(None,None,B("  ")),(None,None,B("asdf"))]])
        self.cptest("right pad", "asdf", [], 0, 2,
            [[(None,None,B("asdf")),(None,None,B("  "))]])

    def test2(self):
        self.cptest("left trim", "asdf", [], -2, 0,
            [[(None,None,B("df"))]])
        self.cptest("right trim", "asdf", [], 0, -2,
            [[(None,None,B("as"))]])


class WidgetSquishTest(unittest.TestCase):
    def wstest(self, w):
        c = w.render((80,0), focus=False)
        assert c.rows() == 0
        c = w.render((80,0), focus=True)
        assert c.rows() == 0
        c = w.render((80,1), focus=False)
        assert c.rows() == 1
        c = w.render((0, 25), focus=False)
        c = w.render((1, 25), focus=False)

    def fwstest(self, w):
        def t(cols, focus):
            wrows = w.rows((cols,), focus)
            c = w.render((cols,), focus)
            assert c.rows() == wrows, (c.rows(), wrows)
            if focus and hasattr(w, 'get_cursor_coords'):
                gcc = w.get_cursor_coords((cols,))
                assert c.cursor == gcc, (c.cursor, gcc)
        t(0, False)
        t(1, False)
        t(0, True)
        t(1, True)

    def test_listbox(self):
        self.wstest(urwid.ListBox([]))
        self.wstest(urwid.ListBox([urwid.Text("hello")]))

    def test_bargraph(self):
        self.wstest(urwid.BarGraph(['foo','bar']))

    def test_graphvscale(self):
        self.wstest(urwid.GraphVScale([(0,"hello")], 1))
        self.wstest(urwid.GraphVScale([(5,"hello")], 1))

    def test_solidfill(self):
        self.wstest(urwid.SolidFill())

    def test_filler(self):
        self.wstest(urwid.Filler(urwid.Text("hello")))

    def test_overlay(self):
        self.wstest(urwid.Overlay(
            urwid.BigText("hello",urwid.Thin6x6Font()),
            urwid.SolidFill(),
            'center', None, 'middle', None))
        self.wstest(urwid.Overlay(
            urwid.Text("hello"), urwid.SolidFill(),
            'center',  ('relative', 100), 'middle', None))

    def test_frame(self):
        self.wstest(urwid.Frame(urwid.SolidFill()))
        self.wstest(urwid.Frame(urwid.SolidFill(),
            header=urwid.Text("hello")))
        self.wstest(urwid.Frame(urwid.SolidFill(),
            header=urwid.Text("hello"),
            footer=urwid.Text("hello")))

    def test_pile(self):
        self.wstest(urwid.Pile([urwid.SolidFill()]))
        self.wstest(urwid.Pile([('flow', urwid.Text("hello"))]))
        self.wstest(urwid.Pile([]))

    def test_columns(self):
        self.wstest(urwid.Columns([urwid.SolidFill()]))
        self.wstest(urwid.Columns([(4, urwid.SolidFill())]))

    def test_buttons(self):
        self.fwstest(urwid.Button(u"hello"))
        self.fwstest(urwid.RadioButton([], u"hello"))


class CommonContainerTest(unittest.TestCase):
    def test_pile(self):
        t1 = urwid.Text(u'one')
        t2 = urwid.Text(u'two')
        t3 = urwid.Text(u'three')
        sf = urwid.SolidFill('x')
        p = urwid.Pile([])
        self.assertEquals(p.focus, None)
        self.assertRaises(IndexError, lambda: getattr(p, 'focus_position'))
        self.assertRaises(IndexError, lambda: setattr(p, 'focus_position',
            None))
        self.assertRaises(IndexError, lambda: setattr(p, 'focus_position', 0))
        p.contents = [(t1, ('pack', None)), (t2, ('pack', None)),
            (sf, ('given', 3)), (t3, ('pack', None))]
        p.focus_position = 1
        del p.contents[0]
        self.assertEquals(p.focus_position, 0)
        p.contents[0:0] = [(t3, ('pack', None)), (t2, ('pack', None))]
        p.contents.insert(3, (t1, ('pack', None)))
        self.assertEquals(p.focus_position, 2)
        self.assertRaises(urwid.PileError, lambda: p.contents.append(t1))
        self.assertRaises(urwid.PileError, lambda: p.contents.append((t1, None)))
        self.assertRaises(urwid.PileError, lambda: p.contents.append((t1, 'given')))

        p = urwid.Pile([t1, t2])
        self.assertEquals(p.focus, t1)
        self.assertEquals(p.focus_position, 0)
        p.focus_position = 1
        self.assertEquals(p.focus, t2)
        self.assertEquals(p.focus_position, 1)
        p.focus_position = 0
        self.assertRaises(IndexError, lambda: setattr(p, 'focus_position', -1))
        self.assertRaises(IndexError, lambda: setattr(p, 'focus_position', 2))
        # old methods:
        p.set_focus(0)
        self.assertRaises(IndexError, lambda: p.set_focus(-1))
        self.assertRaises(IndexError, lambda: p.set_focus(2))
        p.set_focus(t2)
        self.assertEquals(p.focus_position, 1)
        self.assertRaises(ValueError, lambda: p.set_focus('nonexistant'))
        self.assertEquals(p.widget_list, [t1, t2])
        self.assertEquals(p.item_types, [('weight', 1), ('weight', 1)])
        p.widget_list = [t2, t1]
        self.assertEquals(p.widget_list, [t2, t1])
        self.assertEquals(p.contents, [(t2, ('weight', 1)), (t1, ('weight', 1))])
        self.assertEquals(p.focus_position, 1) # focus unchanged
        p.item_types = [('flow', None), ('weight', 2)]
        self.assertEquals(p.item_types, [('flow', None), ('weight', 2)])
        self.assertEquals(p.contents, [(t2, ('pack', None)), (t1, ('weight', 2))])
        self.assertEquals(p.focus_position, 1) # focus unchanged
        p.widget_list = [t1]
        self.assertEquals(len(p.contents), 1)
        self.assertEquals(p.focus_position, 0)
        p.widget_list.extend([t2, t1])
        self.assertEquals(len(p.contents), 3)
        self.assertEquals(p.item_types, [
            ('flow', None), ('weight', 1), ('weight', 1)])
        p.item_types[:] = [('weight', 2)]
        self.assertEquals(len(p.contents), 1)


    def test_columns(self):
        t1 = urwid.Text(u'one')
        t2 = urwid.Text(u'two')
        t3 = urwid.Text(u'three')
        sf = urwid.SolidFill('x')
        c = urwid.Columns([])
        self.assertEquals(c.focus, None)
        self.assertRaises(IndexError, lambda: getattr(c, 'focus_position'))
        self.assertRaises(IndexError, lambda: setattr(c, 'focus_position',
            None))
        self.assertRaises(IndexError, lambda: setattr(c, 'focus_position', 0))
        c.contents = [
            (t1, ('pack', None, False)),
            (t2, ('weight', 1, False)),
            (sf, ('weight', 2, True)),
            (t3, ('given', 10, False))]
        c.focus_position = 1
        del c.contents[0]
        self.assertEquals(c.focus_position, 0)
        c.contents[0:0] = [
            (t3, ('given', 10, False)),
            (t2, ('weight', 1, False))]
        c.contents.insert(3, (t1, ('pack', None, False)))
        self.assertEquals(c.focus_position, 2)
        self.assertRaises(urwid.ColumnsError, lambda: c.contents.append(t1))
        self.assertRaises(urwid.ColumnsError, lambda: c.contents.append((t1, None)))
        self.assertRaises(urwid.ColumnsError, lambda: c.contents.append((t1, 'given')))

        c = urwid.Columns([t1, t2])
        self.assertEquals(c.focus, t1)
        self.assertEquals(c.focus_position, 0)
        c.focus_position = 1
        self.assertEquals(c.focus, t2)
        self.assertEquals(c.focus_position, 1)
        c.focus_position = 0
        self.assertRaises(IndexError, lambda: setattr(c, 'focus_position', -1))
        self.assertRaises(IndexError, lambda: setattr(c, 'focus_position', 2))
        # old methods:
        c = urwid.Columns([t1, ('weight', 3, t2), sf], box_columns=[2])
        c.set_focus(0)
        self.assertRaises(IndexError, lambda: c.set_focus(-1))
        self.assertRaises(IndexError, lambda: c.set_focus(3))
        c.set_focus(t2)
        self.assertEquals(c.focus_position, 1)
        self.assertRaises(ValueError, lambda: c.set_focus('nonexistant'))
        self.assertEquals(c.widget_list, [t1, t2, sf])
        self.assertEquals(c.column_types, [
            ('weight', 1), ('weight', 3), ('weight', 1)])
        self.assertEquals(c.box_columns, [2])
        c.widget_list = [t2, t1, sf]
        self.assertEquals(c.widget_list, [t2, t1, sf])
        self.assertEquals(c.box_columns, [2])

        self.assertEquals(c.contents, [
            (t2, ('weight', 1, False)),
            (t1, ('weight', 3, False)),
            (sf, ('weight', 1, True))])
        self.assertEquals(c.focus_position, 1) # focus unchanged
        c.column_types = [
            ('flow', None), # use the old name
            ('weight', 2),
            ('fixed', 5)]
        self.assertEquals(c.column_types, [
            ('flow', None),
            ('weight', 2),
            ('fixed', 5)])
        self.assertEquals(c.contents, [
            (t2, ('pack', None, False)),
            (t1, ('weight', 2, False)),
            (sf, ('given', 5, True))])
        self.assertEquals(c.focus_position, 1) # focus unchanged
        c.widget_list = [t1]
        self.assertEquals(len(c.contents), 1)
        self.assertEquals(c.focus_position, 0)
        c.widget_list.extend([t2, t1])
        self.assertEquals(len(c.contents), 3)
        self.assertEquals(c.column_types, [
            ('flow', None), ('weight', 1), ('weight', 1)])
        c.column_types[:] = [('weight', 2)]
        self.assertEquals(len(c.contents), 1)

    def test_list_box(self):
        lb = urwid.ListBox(urwid.SimpleFocusListWalker([]))
        self.assertEquals(lb.focus, None)
        self.assertRaises(IndexError, lambda: getattr(lb, 'focus_position'))
        self.assertRaises(IndexError, lambda: setattr(lb, 'focus_position',
            None))
        self.assertRaises(IndexError, lambda: setattr(lb, 'focus_position', 0))

        t1 = urwid.Text(u'one')
        t2 = urwid.Text(u'two')
        lb = urwid.ListBox(urwid.SimpleListWalker([t1, t2]))
        self.assertEquals(lb.focus, t1)
        self.assertEquals(lb.focus_position, 0)
        lb.focus_position = 1
        self.assertEquals(lb.focus, t2)
        self.assertEquals(lb.focus_position, 1)
        lb.focus_position = 0
        self.assertRaises(IndexError, lambda: setattr(lb, 'focus_position', -1))
        self.assertRaises(IndexError, lambda: setattr(lb, 'focus_position', 2))

    def test_grid_flow(self):
        gf = urwid.GridFlow([], 5, 1, 0, 'left')
        self.assertEquals(gf.focus, None)
        self.assertEquals(gf.contents, [])
        self.assertRaises(IndexError, lambda: getattr(gf, 'focus_position'))
        self.assertRaises(IndexError, lambda: setattr(gf, 'focus_position',
            None))
        self.assertRaises(IndexError, lambda: setattr(gf, 'focus_position', 0))
        self.assertEquals(gf.options(), ('given', 5))
        self.assertEquals(gf.options(width_amount=9), ('given', 9))
        self.assertRaises(urwid.GridFlowError, lambda: gf.options(
            'pack', None))

        t1 = urwid.Text(u'one')
        t2 = urwid.Text(u'two')
        gf = urwid.GridFlow([t1, t2], 5, 1, 0, 'left')
        self.assertEquals(gf.focus, t1)
        self.assertEquals(gf.focus_position, 0)
        self.assertEquals(gf.contents, [(t1, ('given', 5)), (t2, ('given', 5))])
        gf.focus_position = 1
        self.assertEquals(gf.focus, t2)
        self.assertEquals(gf.focus_position, 1)
        gf.contents.insert(0, (t2, ('given', 5)))
        self.assertEquals(gf.focus_position, 2)
        self.assertRaises(urwid.GridFlowError, lambda: gf.contents.append(()))
        self.assertRaises(urwid.GridFlowError, lambda: gf.contents.insert(1,
            (t1, ('pack', None))))
        gf.focus_position = 0
        self.assertRaises(IndexError, lambda: setattr(gf, 'focus_position', -1))
        self.assertRaises(IndexError, lambda: setattr(gf, 'focus_position', 3))
        # old methods:
        gf.set_focus(0)
        self.assertRaises(IndexError, lambda: gf.set_focus(-1))
        self.assertRaises(IndexError, lambda: gf.set_focus(3))
        gf.set_focus(t1)
        self.assertEquals(gf.focus_position, 1)
        self.assertRaises(ValueError, lambda: gf.set_focus('nonexistant'))

    def test_overlay(self):
        s1 = urwid.SolidFill(u'1')
        s2 = urwid.SolidFill(u'2')
        o = urwid.Overlay(s1, s2,
            'center', ('relative', 50), 'middle', ('relative', 50))
        self.assertEquals(o.focus, s1)
        self.assertEquals(o.focus_position, 1)
        self.assertRaises(IndexError, lambda: setattr(o, 'focus_position',
            None))
        self.assertRaises(IndexError, lambda: setattr(o, 'focus_position', 2))

        self.assertEquals(o.contents[0], (s2,
            urwid.Overlay._DEFAULT_BOTTOM_OPTIONS))
        self.assertEquals(o.contents[1], (s1, (
            'center', None, 'relative', 50, None, 0, 0,
            'middle', None, 'relative', 50, None, 0, 0)))

    def test_frame(self):
        s1 = urwid.SolidFill(u'1')

        f = urwid.Frame(s1)
        self.assertEquals(f.focus, s1)
        self.assertEquals(f.focus_position, 'body')
        self.assertRaises(IndexError, lambda: setattr(f, 'focus_position',
            None))
        self.assertRaises(IndexError, lambda: setattr(f, 'focus_position',
            'header'))

        t1 = urwid.Text(u'one')
        t2 = urwid.Text(u'two')
        t3 = urwid.Text(u'three')
        f = urwid.Frame(s1, t1, t2, 'header')
        self.assertEquals(f.focus, t1)
        self.assertEquals(f.focus_position, 'header')
        f.focus_position = 'footer'
        self.assertEquals(f.focus, t2)
        self.assertEquals(f.focus_position, 'footer')
        self.assertRaises(IndexError, lambda: setattr(f, 'focus_position', -1))
        self.assertRaises(IndexError, lambda: setattr(f, 'focus_position', 2))
        del f.contents['footer']
        self.assertEquals(f.footer, None)
        self.assertEquals(f.focus_position, 'body')
        f.contents.update(footer=(t3, None), header=(t2, None))
        self.assertEquals(f.header, t2)
        self.assertEquals(f.footer, t3)
        def set1():
            f.contents['body'] = t1
        self.assertRaises(urwid.FrameError, set1)
        def set2():
            f.contents['body'] = (t1, 'given')
        self.assertRaises(urwid.FrameError, set2)

    def test_focus_path(self):
        # big tree of containers
        t = urwid.Text(u'x')
        e = urwid.Edit(u'?')
        c = urwid.Columns([t, e, t, t])
        p = urwid.Pile([t, t, c, t])
        a = urwid.AttrMap(p, 'gets ignored')
        s = urwid.SolidFill(u'/')
        o = urwid.Overlay(e, s, 'center', 'pack', 'middle', 'pack')
        lb = urwid.ListBox(urwid.SimpleFocusListWalker([t, a, o, t]))
        lb.focus_position = 1
        g = urwid.GridFlow([t, t, t, t, e, t], 10, 0, 0, 'left')
        g.focus_position = 4
        f = urwid.Frame(lb, header=t, footer=g)

        self.assertEquals(f.get_focus_path(), ['body', 1, 2, 1])
        f.set_focus_path(['footer']) # same as f.focus_position = 'footer'
        self.assertEquals(f.get_focus_path(), ['footer', 4])
        f.set_focus_path(['body', 1, 2, 2])
        self.assertEquals(f.get_focus_path(), ['body', 1, 2, 2])
        self.assertRaises(IndexError, lambda: f.set_focus_path([0, 1, 2]))
        self.assertRaises(IndexError, lambda: f.set_focus_path(['body', 2, 2]))
        f.set_focus_path(['body', 2]) # focus the overlay
        self.assertEquals(f.get_focus_path(), ['body', 2, 1])



def test_all():
    """
    Return a TestSuite with all tests available
    """
    unittests = [
        DecodeOneTest,
        CalcWidthTest,
        ConvertDecSpecialTest,
        WithinDoubleByteTest,
        CalcTextPosTest,
        CalcBreaksCharTest,
        CalcBreaksDBCharTest,
        CalcBreaksWordTest,
        CalcBreaksWordTest2,
        CalcBreaksDBWordTest,
        CalcBreaksUTF8Test,
        CalcBreaksCantDisplayTest,
        SubsegTest,
        CalcTranslateCharTest,
        CalcTranslateWordTest,
        CalcTranslateWordTest2,
        CalcTranslateWordTest3,
        CalcTranslateWordTest4,
        CalcTranslateWordTest5,
        CalcTranslateClipTest,
        CalcTranslateCantDisplayTest,
        CalcPosTest,
        Pos2CoordsTest,
        CanvasCacheTest,
        CanvasTest,
        ShardBodyTest,
        ShardsTrimTest,
        ShardsJoinTest,
        TagMarkupTest,
        TextTest,
        EditTest,
        EditRenderTest,
        ListBoxCalculateVisibleTest,
        ListBoxChangeFocusTest,
        ListBoxRenderTest,
        ListBoxKeypressTest,
        ZeroHeightContentsTest,
        PaddingTest,
        FillerTest,
        FrameTest,
        PileTest,
        ColumnsTest,
        LineBoxTest,
        BarGraphTest,
        OverlayTest,
        GridFlowTest,
        SmoothBarGraphTest,
        CanvasJoinTest,
        CanvasOverlayTest,
        CanvasPadTrimTest,
        WidgetSquishTest,
        TermTest,
        CommonContainerTest,
        ]
    module_doctests = [
        urwid.widget,
        urwid.wimp,
        urwid.decoration,
        urwid.display_common,
        urwid.main_loop,
        urwid.monitored_list,
        urwid.raw_display,
        'urwid.split_repr', # override function with same name
        urwid.util,
        ]
    tests = unittest.TestSuite()
    for t in unittests:
        tests.addTest(unittest.TestLoader().loadTestsFromTestCase(t))
    for m in module_doctests:
        tests.addTest(DocTestSuite(
            m, optionflags=ELLIPSIS | IGNORE_EXCEPTION_DETAIL))
    return tests

if __name__ == '__main__':
    unittest.TextTestRunner(verbosity=2).run(test_all())

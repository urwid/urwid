import os
import sys
import unittest

from urwid.vterm import TerminalWidget
from urwid.main_loop import SelectEventLoop
from urwid import signals

class DummyCommand(object):
    QUITSTRING = '|||quit|||'

    def __init__(self):
        self.reader, self.writer = os.pipe()

    def __call__(self):
        while True:
            data = os.read(self.reader, 1024)
            if self.QUITSTRING == data:
                break
            sys.stdout.write(data)
            sys.stdout.flush()

    def write(self, data):
        os.write(self.writer, data)

    def quit(self):
        self.write(self.QUITSTRING)


class TermTest(unittest.TestCase):
    def setUp(self):
        self.command = DummyCommand()

        self.term = TerminalWidget(self.command)
        self.resize(80, 24)

    def tearDown(self):
        self.command.quit()

    def caught_beep(self, obj):
        self.beeped = True

    def resize(self, width, height, soft=False):
        self.termsize = (width, height)
        if not soft:
            self.term.render(self.termsize, focus=False)

    def write(self, data):
        self.command.write(data)

    def read(self):
        self.term.wait_and_feed()
        content = self.term.render(self.termsize, focus=False).text
        lines = [line.rstrip() for line in content]
        return '\n'.join(lines).rstrip()

    def test_simplestring(self):
        self.write('hello world')
        self.assertEqual(self.read(), 'hello world')

    def test_linefeed(self):
        self.write('hello\x0aworld')
        self.assertEqual(self.read(), 'hello\nworld')

    def test_carriage_return(self):
        self.write('hello\x0dworld')
        self.assertEqual(self.read(), 'world')

    def test_insertlines(self):
        self.write('\x1b[0;0flast\x1b[0;0f\x1b[10L\x1b[0;0ffirst\nsecond\n\x1b[11D')
        self.assertEqual(self.read(), 'first\nsecond\n\n\n\n\n\n\n\n\nlast')

    def test_deletelines(self):
        self.write('1\n2\n3\n4\x1b[2;1f\x1b[2M')
        self.assertEqual(self.read(), '1\n4')

    def edgewall(self):
        edgewall = '1-\x1b[1;%(x)df-2\x1b[%(y)d;1f3-\x1b[%(y)d;%(x)df-4\x0d'
        self.write(edgewall % {'x': self.termsize[0] - 1,
                               'y': self.termsize[1] - 1})

    def test_horizontal_resize(self):
        self.resize(80, 24)
        self.edgewall()
        self.assertEqual(self.read(), '1-' + ' ' * 76 + '-2' + '\n' * 22
                         + '3-' + ' ' * 76 + '-4')
        self.resize(78, 24, soft=True)
        self.assertEqual(self.read(), '1-' + '\n' * 22 + '3-')
        self.resize(80, 24, soft=True)
        self.assertEqual(self.read(), '1-' + '\n' * 22 + '3-')

    def test_vertical_resize(self):
        self.resize(80, 24)
        self.edgewall()
        self.assertEqual(self.read(), '1-' + ' ' * 76 + '-2' + '\n' * 22
                         + '3-' + ' ' * 76 + '-4')
        self.resize(80, 23, soft=True)
        self.assertEqual(self.read(), '\n' * 21 + '3-' + ' ' * 76 + '-4')
        self.resize(80, 24, soft=True)
        self.assertEqual(self.read(), '1-' + ' ' * 76 + '-2' + '\n' * 22
                         + '3-' + ' ' * 76 + '-4')

    def test_defargs(self):
        self.write('XXX\n\x1b[faaa\x1b[Bccc\x1b[Addd\x1b[Bfff\x1b[Cbbb\x1b[A\x1b[Deee')
        self.assertEqual(self.read(), 'aaa   ddd      eee\n   ccc   fff bbb')

if __name__ == '__main__':
    unittest.main()

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
    TERMSIZE = (80, 24)

    def setUp(self):
        self.command = DummyCommand()

        self.term = TerminalWidget(self.command)

        self.term.render(self.TERMSIZE, focus=False)

    def tearDown(self):
        self.command.quit()

    def caught_beep(self, obj):
        self.beeped = True

    def write(self, data):
        self.command.write(data)

    def read(self):
        self.term.wait_and_feed()
        content = self.term.render(self.TERMSIZE, focus=False).text
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

if __name__ == '__main__':
    unittest.main()

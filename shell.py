#!/usr/bin/python

import urwid
import urwid.raw_display

import sys
import StringIO
import traceback

Screen = urwid.raw_display.Screen

ps1 = ">>> "
ps2 = "... "


class AssertAlways(object):
    def __getattr__(self, name):
        assert 0, name  # FIXME 


class ShellEnvironment(object):
    def __init__(self):
        self.globals = {}


    def run(self, statement):
        """
        Run the python commands in statement and return:
        (output text, error information)

        """
        err = None
        try:
            code = compile(statement, '<interactive>', 'single')
        except:
            err = sys.exc_info()

        if err:
            return None, err

        save_stdin = sys.stdin
        sys.stdin = AssertAlways()
        save_stdout = sys.stdout
        sys.stdout = StringIO.StringIO()
        output = None
        try:
            try:
                eval(code, self.globals)
            except:
                err = sys.exc_info()
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = save_stdout
            sys.stdin = save_stdin

        return output, err

               

    

class ShellWindow(urwid.WidgetWrap):
    def __init__(self):
        self.lines = []
        self.lines.append(urwid.Text("Python "+sys.version))
        self.lb = urwid.ListBox(self.lines)
        self.new_edit()
        self.shenv = ShellEnvironment()
        self.__super.__init__(self.lb)

    def new_edit(self):
        self.edit = ShellEdit(self)
        self.lines.append(self.edit)
        self.lb.set_focus(len(self.lines)-1)

    def execute_edit(self):
        et = self.edit.get_edit_text()
        self.lines[-1] = urwid.Text([('prompt', ps1),et])
        result, err = self.shenv.run(et)
        if result:
            if result[-1:] == '\n': result = result[:-1]
            self.lines.append(urwid.Text(result))
        if err:
            trace = traceback.format_exception_only(*err[:2])
            trace = "".join(trace)
            if trace[-1] == '\n': trace = trace[:-1]
            self.lines.append(urwid.Text(('error', trace)))
        self.new_edit()


class ShellEdit(urwid.Edit):
    def __init__(self, parent):
        self.parent = parent
        self.__super.__init__(('prompt', ps1))

    def keypress(self, size, k):
        k = self.__super.keypress(size, k)
        if k == 'enter':
            self.parent.execute_edit()


def main():
    view = urwid.AttrWrap(ShellWindow(), 'body')
    screen = urwid.raw_display.Screen()
    # use the original display buffer so that text mixes with the command line
    screen.start(alternate_buffer=False)
    try:
        urwid.generic_main_loop(view, [
            ('body', 'light gray', 'black'),
            ('prompt', 'yellow', 'black'),
            ('error', 'light red', 'black'),
            ], screen)
    finally:
        # since we start()ed the screen we need to clean it up ourselves
        screen.stop()




if __name__ == "__main__":
    main()

#!/usr/bin/python

import urwid
import urwid.raw_display

import sys
import StringIO
import traceback

Screen = urwid.raw_display.Screen

class ShellManager(object):
    def __init__(self):
        self.ui = Screen()
        self.view = urwid.AttrWrap(ShellWindow(), 'body')

    def main(self):
        self.ui.register_palette([
            ('body', 'light gray', 'black'),
            ('prompt', 'yellow', 'black'),
            ('error', 'light red', 'black'),
            ])
        self.ui.run_wrapper(self.run)

    def run(self):
        size = self.ui.get_cols_rows()

        keys = ['force update']
        while 'alt x' not in keys:
            if keys:
                self.ui.draw_screen(size, self.view.render(size, focus=True))
            keys = self.ui.get_input()
            if 'window resize' in keys:
                size = self.ui.get_cols_rows()
            for k in keys:
                if urwid.is_mouse_event(k):
                    event, button, col, row = k
                    self.view.mouse_event(size, event, button, col, row, 
                        focus=True)
                else:
                    k = self.view.keypress(size, k)



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
        self.lines[-1] = urwid.Text([('prompt',">>> "),et])
        result, err = self.shenv.run(et)
        if result:
            if result[-1] == '\n': result = result[:-1]
            self.lines.append(urwid.Text(result[:-1]))
        if err:
            trace = traceback.format_exception_only(*err[:2])
            trace = "".join(trace)
            if trace[-1] == '\n': trace = trace[:-1]
            self.lines.append(urwid.Text(('error', trace)))
        self.new_edit()


class ShellEdit(urwid.Edit):
    def __init__(self, parent):
        self.parent = parent
        self.__super.__init__(('prompt',">>> "))

    def keypress(self, size, k):
        k = self.__super.keypress(size, k)
        if k == 'enter':
            self.parent.execute_edit()


def main():
    ShellManager().main()

if __name__ == "__main__":
    main()

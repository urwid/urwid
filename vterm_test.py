#!/usr/bin/python
import urwid

def main():
    event_loop = urwid.SelectEventLoop()

    mainframe = urwid.Frame(
        urwid.Columns([
            ('fixed', 3, urwid.SolidFill('|')),
            urwid.Pile([
                ('weight', 70, urwid.TerminalWidget(None, event_loop)),
                ('fixed', 1, urwid.Filler(urwid.Edit('focus test edit: '))),
            ]),
            ('fixed', 3, urwid.SolidFill('|')),
        ], box_columns=[1]),
        header=urwid.Columns([
            ('fixed', 3, urwid.Text('.,:')),
            urwid.Divider('-'),
            ('fixed', 3, urwid.Text(':,.')),
        ]),
        footer=urwid.Columns([
            ('fixed', 3, urwid.Text('`"*')),
            urwid.Divider('-'),
            ('fixed', 3, urwid.Text('*"\'')),
        ]),
    )

    def quit(key):
        if key in ('q', 'Q'):
            raise urwid.ExitMainLoop()

    loop = urwid.MainLoop(
        mainframe,
        unhandled_input=quit,
        event_loop=event_loop
    ).run()

if __name__ == '__main__':
    main()

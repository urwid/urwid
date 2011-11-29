#!/usr/bin/python

import subprocess
import urwid

factor_me = 362923067964327863989661926737477737673859044111968554257667

output_widget = urwid.Text("Factors of %d:\n" % factor_me)
edit_widget = urwid.Edit("Type anything or press enter to exit:")
frame_widget = urwid.Frame(
    header=edit_widget,
    body=urwid.Filler(output_widget, valign='bottom'),
    focus_part='header')

def exit_on_enter(key):
    if key == 'enter': raise urwid.ExitMainLoop()

loop = urwid.MainLoop(frame_widget, unhandled_input=exit_on_enter)

def received_output(data):
    output_widget.set_text(output_widget.text + data)

write_fd = loop.watch_pipe(received_output)
proc = subprocess.Popen(
    ['python', '-u', 'subproc2.py', str(factor_me)],
    stdout=write_fd,
    close_fds=True)

loop.run()
proc.kill()

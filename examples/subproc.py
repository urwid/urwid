#!/usr/bin/env python

from __future__ import annotations

import os
import subprocess
import sys

import urwid

factor_me = 362923067964327863989661926737477737673859044111968554257667
run_me = os.path.join(os.path.dirname(sys.argv[0]), "subproc2.py")

output_widget = urwid.Text(f"Factors of {factor_me:d}:\n")
edit_widget = urwid.Edit("Type anything or press enter to exit:")
frame_widget = urwid.Frame(
    header=edit_widget,
    body=urwid.Filler(output_widget, valign=urwid.BOTTOM),
    focus_part="header",
)


def exit_on_enter(key: str | tuple[str, int, int, int]) -> None:
    if key == "enter":
        raise urwid.ExitMainLoop()


loop = urwid.MainLoop(frame_widget, unhandled_input=exit_on_enter)


def received_output(data: bytes) -> bool:
    output_widget.set_text(output_widget.text + data.decode("utf8"))
    return True


write_fd = loop.watch_pipe(received_output)
with subprocess.Popen(  # noqa: S603
    ["python", "-u", run_me, str(factor_me)],  # noqa: S607  # Example can be insecure
    stdout=write_fd,
    close_fds=True,
) as proc:
    loop.run()

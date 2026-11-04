#!/usr/bin/env python

"""Example: a spinner for every frame preset, started and stopped together.

Space starts or stops the spinners, + and - make them faster or slower,
s shows the next frame of the stopped spinners, and q exits.
"""

from __future__ import annotations

import urwid

# Bounds for + and -: a shorter interval redraws the screen almost continuously.
MIN_INTERVAL = 0.0125
MAX_INTERVAL = 1.6
PALETTE = [("frame", "light cyan", ""), ("help", "black", "light gray")]


def main() -> None:
    """Build a row per frame preset and the key handling, and run the main loop."""
    spinners = [urwid.Spinner(frames) for frames in urwid.SpinnerFrames]
    rows = [
        urwid.Columns([(urwid.PACK, urwid.AttrMap(spinner, "frame")), urwid.Text(frames.name)], dividechars=1)
        for spinner, frames in zip(spinners, urwid.SpinnerFrames, strict=True)
    ]
    status = urwid.Text("")

    def show_status() -> None:
        state = "running" if spinners[0].running else "stopped"
        status.set_text(
            f"{state}, {spinners[0].interval:g} s per frame  space: start/stop  +/-: faster/slower  s: step  q: quit"
        )

    def start_all(_loop: urwid.MainLoop | None = None, _data: object = None) -> None:
        for spinner in spinners:
            spinner.start()
        show_status()

    def unhandled(key: str | tuple[str, int, int, int]) -> None:
        if key == "q":
            for spinner in spinners:
                spinner.stop()
            raise urwid.ExitMainLoop
        if key == " ":
            if spinners[0].running:
                for spinner in spinners:
                    spinner.stop()
                show_status()
            else:
                start_all()
        elif key in {"+", "-"}:
            for spinner in spinners:
                spinner.interval = min(MAX_INTERVAL, max(MIN_INTERVAL, spinner.interval * (0.5 if key == "+" else 2)))
            show_status()
        elif key == "s":
            for spinner in spinners:
                if not spinner.running:
                    spinner.step()

    body = urwid.Filler(urwid.Pile(rows), valign=urwid.TOP)
    frame: urwid.Frame[urwid.Filler[urwid.Pile], None, urwid.AttrMap[urwid.Text]] = urwid.Frame(
        body,
        footer=urwid.AttrMap(status, "help"),
    )
    loop = urwid.MainLoop(frame, PALETTE, unhandled_input=unhandled)
    # Started from an alarm, where the loop is running, so the spinners find it without loop=.
    loop.set_alarm_in(0, start_all)
    loop.run()


if __name__ == "__main__":
    main()

#!/usr/bin/env python

"""Example: run a slow computation on a worker thread and show its progress and result.

Press :kbd:`Enter` on the button to start the computation and :kbd:`q` to exit.
The interface keeps answering keys while the worker runs.
"""

from __future__ import annotations

import threading
import time

import urwid

STEPS = 20


def compute(loop: urwid.MainLoop, progress: urwid.ProgressBar, status: urwid.Text) -> None:
    """Sum the squares of 1 to :data:`STEPS` slowly, reporting each step to the loop.

    Runs on the worker thread: widgets are changed only through :meth:`urwid.MainLoop.call_from_thread`.

    :param loop: main loop that shows the progress
    :param progress: bar showing the steps done
    :param status: text showing the result
    """
    total = 0
    try:
        for step in range(1, STEPS + 1):
            time.sleep(0.2)
            total += step * step
            loop.call_from_thread(progress.set_completion, step)
        loop.call_from_thread(status.set_text, f"Done: the sum of squares is {total}.")
    except RuntimeError:
        pass  # the loop stopped, so nothing shows the result any more


def main() -> None:
    """Run the example."""
    status = urwid.Text("Not started.")
    progress = urwid.ProgressBar("pg normal", "pg complete", done=STEPS)
    worker: threading.Thread | None = None

    def start(_button: urwid.Button) -> None:
        """Start the worker, unless it is still running."""
        nonlocal worker
        if worker is not None and worker.is_alive():
            return
        status.set_text("Working...")
        progress.set_completion(0)
        # A daemon thread, so that q does not wait for the computation to finish.
        worker = threading.Thread(target=compute, args=(loop, progress, status), daemon=True)
        worker.start()

    def handle_key(key: str | tuple[str, int, int, int]) -> None:
        """Exit on :kbd:`q`.

        :param key: unhandled key or mouse event
        :raises urwid.ExitMainLoop: when the user presses :kbd:`q`
        """
        if key in {"q", "Q"}:
            raise urwid.ExitMainLoop

    body = urwid.Pile([urwid.Button("Compute", on_press=start), progress, status])
    loop = urwid.MainLoop(
        urwid.Filler(body, valign=urwid.TOP),
        palette=[("pg normal", "white", "dark gray"), ("pg complete", "white", "dark blue")],
        unhandled_input=handle_key,
    )
    loop.run()


if __name__ == "__main__":
    main()

#!/usr/bin/env python

"""Example: hand the terminal to an external editor and show what was written in it.

Press :kbd:`e` to edit the text in ``$EDITOR`` (``vi`` when it is not set) and :kbd:`q` to exit.
"""

from __future__ import annotations

import os
import pathlib
import shlex
import subprocess
import tempfile

import urwid

text_widget = urwid.Text("Press e to edit this text in $EDITOR, q to exit.\n")


def edit_text(loop: urwid.MainLoop) -> None:
    """Run the editor on a temporary file holding the text and show the edited content.

    :param loop: main loop whose screen is paused while the editor runs
    """
    # $EDITOR is a shell command line such as "vim -f" or "code --wait", not an executable name
    editor = shlex.split(os.environ.get("EDITOR", "")) or ["vi"]
    fd, name = tempfile.mkstemp(suffix=".txt")
    path = pathlib.Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(str(text_widget.text))
        with loop.paused():
            subprocess.run([*editor, str(path)], check=False)  # noqa: S603  # Example can be insecure
        text_widget.set_text(path.read_text(encoding="utf-8"))
    finally:
        path.unlink(missing_ok=True)


def main() -> None:
    """Run the example."""

    def handle_key(key: str | tuple[str, int, int, int]) -> None:
        """Handle keys not consumed by the widgets: :kbd:`e` to edit, :kbd:`q` to exit.

        :param key: unhandled key or mouse event
        :raises urwid.ExitMainLoop: when the user presses :kbd:`q`
        """
        if key == "e":
            edit_text(loop)
        elif key in {"q", "Q"}:
            raise urwid.ExitMainLoop

    loop = urwid.MainLoop(urwid.Filler(text_widget, valign=urwid.TOP), unhandled_input=handle_key)
    loop.run()


if __name__ == "__main__":
    main()

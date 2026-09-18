#!/usr/bin/env python
#
# Urwid graphics example program
#    Copyright (C) 2004-2011  Ian Ward
#
#    This library is free software; you can redistribute it and/or
#    modify it under the terms of the GNU Lesser General Public
#    License as published by the Free Software Foundation; either
#    version 2.1 of the License, or (at your option) any later version.
#
#    This library is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#    Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public
#    License along with this library; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#
# Urwid web site: https://urwid.org/

"""
Urwid example demonstrating use of the BarGraph widget and creating a
floating-window appearance.  Also shows use of alarms to create timed
animation.
"""

from __future__ import annotations

import math
import time
import typing

import urwid

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Sequence

UPDATE_INTERVAL = 0.2


def sin100(x: int) -> float:
    """Return a sine value scaled to the range 0-100 that repeats every 100 steps.

    :param x: input step
    :returns: sine wave value in the range 0-100
    """
    return 50 + 50 * math.sin(x * math.pi / 50)


class GraphModel:
    """Store the data that will be displayed on the graph, and keep track of which mode is enabled."""

    data_max_value: typing.ClassVar[int] = 100

    def __init__(self) -> None:
        data: list[tuple[str, Sequence[float | int]]] = [
            ("Saw", list(range(0, 100, 2)) * 2),
            ("Square", [0] * 30 + [100] * 30),
            ("Sine 1", [sin100(x) for x in range(100)]),
            ("Sine 2", [(sin100(x) + sin100(x * 2)) / 2 for x in range(100)]),
            ("Sine 3", [(sin100(x) + sin100(x * 3)) / 2 for x in range(100)]),
        ]
        self.modes: list[str] = []
        self.data: dict[str, Sequence[float | int]] = {}
        for m, d in data:
            self.modes.append(m)
            self.data[m] = d
        self.current_mode = self.modes[0]

    def get_modes(self) -> list[str]:
        """Return the available mode names."""
        return self.modes

    def set_mode(self, m: str) -> None:
        """Set the current mode.

        :param m: name of the mode to switch to
        """
        self.current_mode = m

    def get_data(self, offset: int, r: int) -> tuple[list[float | int], int, int]:
        """Return a slice of the current mode's data, its maximum value, and the length it repeats at.

        :param offset: start offset into the data, wrapped to the data length
        :param r: number of data points to return
        :returns: the requested data points, the maximum value among all items, and the length the data repeats at
        """
        lines: list[float | int] = []
        d = self.data[self.current_mode]
        while r:
            offset %= len(d)
            segment = d[offset : offset + r]
            r -= len(segment)
            offset += len(segment)
            lines += segment
        return lines, self.data_max_value, len(d)


class GraphView(urwid.WidgetWrap[urwid.Widget]):
    """Provide the application's interface and graph display."""

    palette: typing.ClassVar[list[tuple[str, str, str] | tuple[str, str, str, str]]] = [
        ("body", "black", "light gray", "standout"),
        ("header", "white", "dark red", "bold"),
        ("screen edge", "light blue", "dark cyan"),
        ("main shadow", "dark gray", "black"),
        ("line", "black", "light gray", "standout"),
        ("bg background", "light gray", "black"),
        ("bg 1", "black", "dark blue", "standout"),
        ("bg 1 smooth", "dark blue", "black"),
        ("bg 2", "black", "dark cyan", "standout"),
        ("bg 2 smooth", "dark cyan", "black"),
        ("button normal", "light gray", "dark blue", "standout"),
        ("button select", "white", "dark green"),
        ("line", "black", "light gray", "standout"),
        ("pg normal", "white", "black", "standout"),
        ("pg complete", "white", "dark magenta"),
        ("pg smooth", "dark magenta", "black"),
    ]

    graph_samples_per_bar: typing.ClassVar[int] = 10
    graph_num_bars: typing.ClassVar[int] = 5
    graph_offset_per_second: typing.ClassVar[int] = 5

    def __init__(self, controller: GraphController) -> None:
        self.controller = controller
        self.started = True
        self.start_time: float | None = None
        self.offset = 0
        self.last_offset: int | None = None
        super().__init__(self.main_window())

    def get_offset_now(self) -> int:
        """Return the current graph offset, accounting for elapsed animation time.

        :returns: graph offset
        """
        if self.start_time is None:
            return 0
        if not self.started:
            return self.offset
        tdelta = time.time() - self.start_time
        return int(self.offset + (tdelta * self.graph_offset_per_second))

    def update_graph(self, force_update: bool = False) -> bool:
        """Recompute the graph and progress bar for the current offset.

        :param force_update: redraw even if the offset has not changed since the last update
        :returns: whether the graph was actually redrawn
        """
        o = self.get_offset_now()
        if o == self.last_offset and not force_update:
            return False
        self.last_offset = o
        gspb = self.graph_samples_per_bar
        r = gspb * self.graph_num_bars
        d, max_value, repeat = self.controller.get_data(o, r)
        lines: list[list[float | int]] = []
        for n in range(self.graph_num_bars):
            value = sum(d[n * gspb : (n + 1) * gspb]) / gspb
            # toggle between two bar types
            if n & 1:
                lines.append([0, value])
            else:
                lines.append([value, 0])
        self.graph.set_data(lines, max_value)

        # also update progress
        prog: float
        if (o // repeat) & 1:
            # show 100% for first half, 0 for second half
            if o % repeat > repeat // 2:
                prog = 0
            else:
                prog = 1
        else:
            prog = float(o % repeat) / repeat
        self.animate_progress.current = prog
        return True

    def on_animate_button(self, button: urwid.Button) -> None:
        """Toggle started state and button text.

        :param button: button that was pressed
        """
        if self.started:  # stop animation
            button.set_label("Start")
            self.offset = self.get_offset_now()
            self.started = False
            self.controller.stop_animation()
        else:
            button.set_label("Stop")
            self.started = True
            self.start_time = time.time()
            self.controller.animate_graph()

    def on_reset_button(self, w: urwid.Button) -> None:
        """Reset the animation offset and restart the clock.

        :param w: button that was pressed
        """
        self.offset = 0
        self.start_time = time.time()
        self.update_graph(True)

    def on_mode_button(self, button: urwid.RadioButton, state: bool) -> None:
        """Notify the controller of a new mode setting.

        :param button: radio button whose state changed, carrying the mode name as its label
        :param state: new state of the radio button
        """
        if state:
            # The new mode is the label of the button
            self.controller.set_mode(typing.cast("str", button.get_label()))
        self.last_offset = None

    def on_mode_change(self, m: str) -> None:
        """Handle external mode change by updating radio buttons.

        :param m: name of the mode that is now selected
        """
        for rb in self.mode_buttons:
            if rb.original_widget.label == m:
                rb.original_widget.set_state(True, do_callback=False)
                break
        self.last_offset = None

    def on_unicode_checkbox(self, w: urwid.CheckBox, state: bool) -> None:
        """Switch the graph and progress bar between Unicode and ASCII rendering.

        :param w: checkbox that changed
        :param state: new state of the checkbox
        """
        self.graph = self.bar_graph(state)
        self.graph_wrap._w = self.graph
        self.animate_progress = self.progress_bar(state)
        self.animate_progress_wrap._w = self.animate_progress
        self.update_graph(True)

    def main_shadow(self, w: urwid.Widget) -> urwid.Widget:
        """Wrap a shadow and background around a widget.

        :param w: widget to wrap
        :returns: the wrapped widget
        """
        bg: urwid.Widget = urwid.AttrMap(urwid.SolidFill("▒"), "screen edge")
        shadow = urwid.AttrMap(urwid.SolidFill(" "), "main shadow")

        bg = urwid.Overlay(
            shadow,
            bg,
            align=urwid.LEFT,
            width=urwid.RELATIVE_100,
            valign=urwid.TOP,
            height=urwid.RELATIVE_100,
            left=3,
            right=1,
            top=2,
            bottom=1,
        )
        w = urwid.Overlay(
            w,
            bg,
            align=urwid.LEFT,
            width=urwid.RELATIVE_100,
            valign=urwid.TOP,
            height=urwid.RELATIVE_100,
            left=2,
            right=3,
            top=1,
            bottom=2,
        )
        return w

    def bar_graph(self, smooth: bool = False) -> urwid.BarGraph:
        """Create the bar graph widget.

        :param smooth: use smoothed (sub-character resolution) bars
        :returns: the bar graph widget
        """
        satt = None
        if smooth:
            satt = {(1, 0): "bg 1 smooth", (2, 0): "bg 2 smooth"}
        w = urwid.BarGraph(["bg background", "bg 1", "bg 2"], satt=satt)
        return w

    def button(
        self,
        t: str,
        fn: Callable[[urwid.Button], None],
    ) -> urwid.AttrMap[urwid.Button]:
        """Create a styled push button.

        :param t: button label
        :param fn: callback connected to the button's ``click`` signal
        :returns: the button wrapped in an :class:`urwid.AttrMap`
        """
        w = urwid.Button(t, fn)
        w = urwid.AttrMap(w, "button normal", "button select")
        return w

    def radio_button(
        self,
        g: list[urwid.RadioButton],
        label: str,
        fn: Callable[[urwid.RadioButton, bool], None],
    ) -> urwid.AttrMap[urwid.RadioButton]:
        """Create a styled radio button for selecting a mode.

        :param g: radio button group to add the new button to
        :param label: button label, also used as the mode name
        :param fn: callback connected to the button's ``change`` signal
        :returns: the radio button wrapped in an :class:`urwid.AttrMap`
        """
        w = urwid.RadioButton(g, label, False, on_state_change=fn)
        w = urwid.AttrMap(w, "button normal", "button select")
        return w

    def progress_bar(self, smooth: bool = False) -> urwid.ProgressBar:
        """Create the animation progress bar widget.

        :param smooth: use smoothed (sub-character resolution) rendering
        :returns: the progress bar widget
        """
        return urwid.ProgressBar(
            "pg normal",
            "pg complete",
            0,
            1,
            "pg smooth" if smooth else None,
        )

    def exit_program(self, w: urwid.Button) -> typing.NoReturn:
        """Exit the main loop.

        :param w: button that was pressed
        :raises urwid.ExitMainLoop: always
        """
        raise urwid.ExitMainLoop()

    def graph_controls(self) -> urwid.ListBox[int]:
        """Build the list of mode, animation and quit controls shown beside the graph.

        :returns: the controls list box
        """
        modes = self.controller.get_modes()
        # setup mode radio buttons
        self.mode_buttons: list[urwid.AttrMap[urwid.RadioButton]] = []
        group: list[urwid.RadioButton] = []
        for m in modes:
            rb = self.radio_button(group, m, self.on_mode_button)
            self.mode_buttons.append(rb)
        # setup animate button
        self.animate_button = self.button("", self.on_animate_button)
        self.on_animate_button(self.animate_button.original_widget)
        self.offset = 0
        self.animate_progress = self.progress_bar()
        animate_controls = urwid.GridFlow(
            [
                self.animate_button,
                self.button("Reset", self.on_reset_button),
            ],
            9,
            2,
            0,
            urwid.CENTER,
        )

        unicode_checkbox: urwid.Widget
        if urwid.get_encoding_mode() == "utf8":
            unicode_checkbox = urwid.CheckBox("Enable Unicode Graphics", on_state_change=self.on_unicode_checkbox)
        else:
            unicode_checkbox = urwid.Text("UTF-8 encoding not detected")

        self.animate_progress_wrap = urwid.WidgetWrap(self.animate_progress)

        lines: list[urwid.Widget] = [
            urwid.Text("Mode", align=urwid.CENTER),
            *self.mode_buttons,
            urwid.Divider(),
            urwid.Text("Animation", align=urwid.CENTER),
            animate_controls,
            self.animate_progress_wrap,
            urwid.Divider(),
            urwid.LineBox(unicode_checkbox),
            urwid.Divider(),
            self.button("Quit", self.exit_program),
        ]
        w = urwid.ListBox(urwid.SimpleListWalker(lines))  # type: ignore[arg-type]  # all lines are flow widgets
        return w

    def main_window(self) -> urwid.Widget:
        """Build the complete application window.

        :returns: the top-level widget
        """
        self.graph = self.bar_graph()
        self.graph_wrap = urwid.WidgetWrap(self.graph)
        vline = urwid.AttrMap(urwid.SolidFill("│"), "line")
        c = self.graph_controls()
        w: urwid.Widget = urwid.Columns(
            [(urwid.WEIGHT, 2, self.graph_wrap), (1, vline), c],
            dividechars=1,
            focus_column=2,
        )
        w = urwid.Padding(w, urwid.LEFT, left=1)
        w = urwid.AttrMap(w, "body")
        w = urwid.LineBox(w)
        w = urwid.AttrMap(w, "line")
        w = self.main_shadow(w)
        return w


class GraphController:
    """Set up the model and view and run the application."""

    def __init__(self) -> None:
        self.animate_alarm: typing.Any = None
        self.model = GraphModel()
        self.view = GraphView(self)
        # use the first mode as the default
        mode = self.get_modes()[0]
        self.model.set_mode(mode)
        # update the view
        self.view.on_mode_change(mode)
        self.view.update_graph(True)

    def get_modes(self) -> list[str]:
        """Allow our view access to the list of modes."""
        return self.model.get_modes()

    def set_mode(self, m: str) -> None:
        """Allow our view to set the mode."""
        self.model.set_mode(m)
        self.view.update_graph(True)

    def get_data(self, offset: int, data_range: int) -> tuple[list[float | int], int, int]:
        """Provide data to our view for the graph.

        :param offset: start offset into the data
        :param data_range: number of data points to return
        :returns: the requested data points, their maximum value, and the length the data repeats at
        """
        return self.model.get_data(offset, data_range)

    def main(self) -> None:
        """Run the main loop."""
        self.loop: urwid.MainLoop = urwid.MainLoop(self.view, self.view.palette)
        self.loop.run()

    def animate_graph(self, loop: urwid.MainLoop | None = None, user_data: typing.Any = None) -> None:
        """Update the graph and schedule the next update.

        :param loop: main loop that triggered this alarm, unused
        :param user_data: alarm user data, unused
        """
        self.view.update_graph()
        self.animate_alarm = self.loop.set_alarm_in(UPDATE_INTERVAL, self.animate_graph)

    def stop_animation(self) -> None:
        """Stop animating the graph."""
        if self.animate_alarm:
            self.loop.remove_alarm(self.animate_alarm)
        self.animate_alarm = None


def main() -> None:
    """Run the graph example program."""
    GraphController().main()


if __name__ == "__main__":
    main()

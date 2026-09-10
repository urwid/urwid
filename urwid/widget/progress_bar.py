from __future__ import annotations

import typing

from .constants import BAR_SYMBOLS, Align, Sizing, WrapMode
from .text import Text
from .widget import Widget, nocache_widget_render_instance

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Hashable

    from urwid.canvas import TextCanvas


class ProgressBar(Widget):
    _sizing = frozenset([Sizing.FLOW])

    eighths = BAR_SYMBOLS.HORISONTAL[:8]  # Full width line is made by style

    text_align = Align.CENTER

    def __init__(
        self,
        normal: Hashable,
        complete: Hashable,
        current: int = 0,
        done: int = 100,
        satt: Hashable = None,
    ) -> None:
        """
        :param normal: display attribute for incomplete part of progress bar
        :param complete: display attribute for complete part of progress bar
        :param current: current progress
        :param done: progress amount at 100%
        :param satt: display attribute for smoothed part of bar where the
                     foreground of satt corresponds to the normal part and the
                     background corresponds to the complete part.
                     If satt is ``None`` then no smoothing will be done.

        >>> from urwid import LineBox
        >>> pb = ProgressBar("a", "b")
        >>> pb
        <ProgressBar flow widget>
        >>> print(pb.get_text())
        0 %
        >>> pb.set_completion(34.42)
        >>> print(pb.get_text())
        34 %
        >>> class CustomProgressBar(ProgressBar):
        ...     def get_text(self):
        ...         return "Foobar"
        >>> cpb = CustomProgressBar("a", "b")
        >>> print(cpb.get_text())
        Foobar
        >>> for x in range(101):
        ...     cpb.set_completion(x)
        ...     s = cpb.render((10,))
        >>> cpb2 = CustomProgressBar("a", "b", satt="c")
        >>> for x in range(101):
        ...     cpb2.set_completion(x)
        ...     s = cpb2.render((10,))
        >>> pb = ProgressBar("a", "b", satt="c")
        >>> pb.set_completion(34.56)
        >>> print(LineBox(pb).render((20,)))
        ┌──────────────────┐
        │      ▏34 %       │
        └──────────────────┘
        """
        super().__init__()
        self.normal = normal
        self.complete = complete
        self._current = current
        self._done = done
        self.satt = satt
        # The label widget is built on first render rather than here, so that an unsupported
        # `text_align` keeps raising from `render` as it did when the widget was built per call.
        self._label: Text | None = None
        self._render_label: Callable[..., TextCanvas] | None = None

    def set_completion(self, current: int) -> None:
        """
        :param current: current progress
        """
        self._current = current
        self._invalidate()

    current = property(lambda self: self._current, set_completion)

    @property
    def done(self) -> int:
        return self._done

    @done.setter
    def done(self, done: int) -> None:
        """
        :param done: progress amount at 100%
        """
        self._done = done
        self._invalidate()

    def rows(self, size: tuple[int], focus: bool = False) -> int:
        return 1

    def get_text(self) -> str:
        """
        Return the progress bar percentage text.
        You can override this method to display custom text.
        """
        percent = min(100, max(0, int(self.current * 100 / self.done)))
        return f"{percent!s} %"

    def render(
        self,
        size: tuple[int],  # type: ignore[override]
        focus: bool = False,
    ) -> TextCanvas:
        """
        Render the progress bar.
        """
        # pylint: disable=protected-access
        (maxcol,) = size
        label, render_label = self._label, self._render_label
        if label is None or render_label is None:
            label = self._label = Text("", self.text_align, WrapMode.CLIP)
            # The label canvas is thrown away once its attributes are rewritten below, so it is
            # rendered outside `CanvasCache`: caching it only costs a weakref, a store and a cleanup.
            render_label = self._render_label = typing.cast(
                "Callable[..., TextCanvas]",
                nocache_widget_render_instance(label),
            )
        label.set_text(self.get_text())
        if label.align != self.text_align:
            label.set_align_mode(self.text_align)
        c = render_label((maxcol,))

        cf = float(self.current) * maxcol / self.done
        ccol_dirty = int(cf)
        ccol = len(c._text[0][:ccol_dirty].decode("utf-8", "ignore").encode("utf-8"))
        cs = 0
        if self.satt is not None:
            cs = int((cf - ccol) * 8)
        if ccol < 0 or (ccol == cs == 0):
            c._attr = [[(self.normal, maxcol)]]
        elif ccol >= maxcol:
            c._attr = [[(self.complete, maxcol)]]
        elif cs and c._text[0][ccol] == 32:
            t = c._text[0]
            cenc = self.eighths[cs].encode("utf-8")
            c._text[0] = t[:ccol] + cenc + t[ccol + 1 :]
            a = []
            if ccol > 0:
                a.append((self.complete, ccol))
            a.append((self.satt, len(cenc)))
            if maxcol - ccol - 1 > 0:
                a.append((self.normal, maxcol - ccol - 1))
            c._attr = [a]
            c._cs = [[(None, len(c._text[0]))]]
        else:
            c._attr = [[(self.complete, ccol), (self.normal, maxcol - ccol)]]
        return c

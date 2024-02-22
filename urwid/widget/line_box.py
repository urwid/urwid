from __future__ import annotations

import typing

from .columns import Columns
from .constants import BOX_SYMBOLS, Align, WHSettings
from .divider import Divider
from .pile import Pile
from .solid_fill import SolidFill
from .text import Text
from .widget_decoration import WidgetDecoration, delegate_to_widget_mixin

if typing.TYPE_CHECKING:
    from typing_extensions import Literal

    from .widget import Widget

WrappedWidget = typing.TypeVar("WrappedWidget")


class LineBox(WidgetDecoration[WrappedWidget], delegate_to_widget_mixin("_wrapped_widget")):
    Symbols = BOX_SYMBOLS

    def __init__(
        self,
        original_widget: WrappedWidget,
        title: str = "",
        title_align: Literal["left", "center", "right"] | Align = Align.CENTER,
        title_attr=None,
        tlcorner: str = BOX_SYMBOLS.LIGHT.TOP_LEFT,
        tline: str = BOX_SYMBOLS.LIGHT.HORIZONTAL,
        lline: str = BOX_SYMBOLS.LIGHT.VERTICAL,
        trcorner: str = BOX_SYMBOLS.LIGHT.TOP_RIGHT,
        blcorner: str = BOX_SYMBOLS.LIGHT.BOTTOM_LEFT,
        rline: str = BOX_SYMBOLS.LIGHT.VERTICAL,
        bline: str = BOX_SYMBOLS.LIGHT.HORIZONTAL,
        brcorner: str = BOX_SYMBOLS.LIGHT.BOTTOM_RIGHT,
    ) -> None:
        """
        Draw a line around original_widget.

        Use 'title' to set an initial title text with will be centered
        on top of the box.

        Use `title_attr` to apply a specific attribute to the title text.

        Use `title_align` to align the title to the 'left', 'right', or 'center'.
        The default is 'center'.

        You can also override the widgets used for the lines/corners:
            tline: top line
            bline: bottom line
            lline: left line
            rline: right line
            tlcorner: top left corner
            trcorner: top right corner
            blcorner: bottom left corner
            brcorner: bottom right corner

        If empty string is specified for one of the lines/corners, then no character will be output there.
        If no top/bottom/left/right lines - whole lines will be omitted.
        This allows for seamless use of adjoining LineBoxes.

        Class attribute `Symbols` can be used as source for standard lines:

        >>> print(LineBox(Text("Some text")).render(()))
        ┌─────────┐
        │Some text│
        └─────────┘
        >>> print(
        ...   LineBox(
        ...     Text("Some text"),
        ...     tlcorner=LineBox.Symbols.LIGHT.TOP_LEFT_ROUNDED,
        ...     trcorner=LineBox.Symbols.LIGHT.TOP_RIGHT_ROUNDED,
        ...     blcorner=LineBox.Symbols.LIGHT.BOTTOM_LEFT_ROUNDED,
        ...     brcorner=LineBox.Symbols.LIGHT.BOTTOM_RIGHT_ROUNDED,
        ...   ).render(())
        ... )
        ╭─────────╮
        │Some text│
        ╰─────────╯
        >>> print(
        ...   LineBox(
        ...     Text("Some text"),
        ...     tline=LineBox.Symbols.HEAVY.HORIZONTAL,
        ...     bline=LineBox.Symbols.HEAVY.HORIZONTAL,
        ...     lline=LineBox.Symbols.HEAVY.VERTICAL,
        ...     rline=LineBox.Symbols.HEAVY.VERTICAL,
        ...     tlcorner=LineBox.Symbols.HEAVY.TOP_LEFT,
        ...     trcorner=LineBox.Symbols.HEAVY.TOP_RIGHT,
        ...     blcorner=LineBox.Symbols.HEAVY.BOTTOM_LEFT,
        ...     brcorner=LineBox.Symbols.HEAVY.BOTTOM_RIGHT,
        ...   ).render(())
        ... )
        ┏━━━━━━━━━┓
        ┃Some text┃
        ┗━━━━━━━━━┛

        To make Table constructions, some lineboxes need to be drawn without sides
        and T or CROSS symbols used for corners of cells.
        """

        w_lline = SolidFill(lline)
        w_rline = SolidFill(rline)

        w_tlcorner, w_tline, w_trcorner = Text(tlcorner), Divider(tline), Text(trcorner)
        w_blcorner, w_bline, w_brcorner = Text(blcorner), Divider(bline), Text(brcorner)

        if not tline and title:
            raise ValueError("Cannot have a title when tline is empty string")

        if title_attr:
            self.title_widget = Text((title_attr, self.format_title(title)))
        else:
            self.title_widget = Text(self.format_title(title))

        if tline:
            if title_align not in {Align.LEFT, Align.CENTER, Align.RIGHT}:
                raise ValueError('title_align must be one of "left", "right", or "center"')
            if title_align == Align.LEFT:
                tline_widgets = [(WHSettings.PACK, self.title_widget), w_tline]
            else:
                tline_widgets = [w_tline, (WHSettings.PACK, self.title_widget)]
                if title_align == Align.CENTER:
                    tline_widgets.append(w_tline)

            self.tline_widget = Columns(tline_widgets)
            top = Columns(
                (
                    (int(bool(tlcorner and lline)), w_tlcorner),
                    self.tline_widget,
                    (int(bool(trcorner and rline)), w_trcorner),
                )
            )

        else:
            self.tline_widget = None
            top = None

        # Note: We need to define a fixed first widget (even if it's 0 width) so that the other
        # widgets have something to anchor onto
        middle = Columns(
            ((int(bool(lline)), w_lline), original_widget, (int(bool(rline)), w_rline)),
            box_columns=[0, 2],
            focus_column=original_widget,
        )

        if bline:
            bottom = Columns(
                (
                    (int(bool(blcorner and lline)), w_blcorner),
                    w_bline,
                    (int(bool(brcorner and rline)), w_brcorner),
                )
            )
        else:
            bottom = None

        pile_widgets = []
        if top:
            pile_widgets.append((WHSettings.PACK, top))
        pile_widgets.append(middle)
        if bottom:
            pile_widgets.append((WHSettings.PACK, bottom))

        self._wrapped_widget = Pile(pile_widgets, focus_item=middle)

        super().__init__(original_widget)

    @property
    def _w(self) -> Pile:
        return self._wrapped_widget

    def format_title(self, text: str) -> str:
        if text:
            return f" {text} "

        return ""

    def set_title(self, text: str) -> None:
        if not self.tline_widget:
            raise ValueError("Cannot set title when tline is unset")
        self.title_widget.set_text(self.format_title(text))
        self.tline_widget._invalidate()

    @property
    def focus(self) -> Widget | None:
        """LineBox is partially container.

        While focus position is a bit hacky
        (formally it's not container and only position 0 available),
        focus widget is always provided by original widget.
        """
        return self._original_widget.focus

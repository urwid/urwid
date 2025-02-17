from __future__ import annotations

import abc
import enum
import typing

from .constants import Sizing, WHSettings

if typing.TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from .widget import Widget


# Ideally, we would like to use an IntFlag coupled with enum.auto().
# However, doing many bitwise operations (which happens when nesting too many
# widgets ...) on IntFlag is orders of magnitude slower than doing the same
# operations on IntEnum.
class _ContainerElementSizingFlag(enum.IntEnum):
    # fmt: off
    NONE      = 0b000000
    BOX       = 0b000001
    FLOW      = 0b000010
    FIXED     = 0b000100
    WH_WEIGHT = 0b001000
    WH_PACK   = 0b010000
    WH_GIVEN  = 0b100000
    # fmt: on

    @staticmethod
    def reverse_flag(bitfield: int) -> tuple[frozenset[Sizing], WHSettings | None]:
        """Get flag in public API format."""
        sizing: set[Sizing] = set()

        if bitfield & _ContainerElementSizingFlag.BOX:
            sizing.add(Sizing.BOX)
        if bitfield & _ContainerElementSizingFlag.FLOW:
            sizing.add(Sizing.FLOW)
        if bitfield & _ContainerElementSizingFlag.FIXED:
            sizing.add(Sizing.FIXED)

        if bitfield & _ContainerElementSizingFlag.WH_WEIGHT:
            return frozenset(sizing), WHSettings.WEIGHT
        if bitfield & _ContainerElementSizingFlag.WH_PACK:
            return frozenset(sizing), WHSettings.PACK
        if bitfield & _ContainerElementSizingFlag.WH_GIVEN:
            return frozenset(sizing), WHSettings.GIVEN
        return frozenset(sizing), None

    @staticmethod
    def log_string(bitfield: int) -> str:
        """Get desctiprion in public API format."""
        sizing, render = _ContainerElementSizingFlag.reverse_flag(bitfield)
        render_string = f" {render.upper()}" if render else ""
        return "|".join(sorted(mode.upper() for mode in sizing)) + render_string


class WidgetContainerMixin:
    """
    Mixin class for widget containers implementing common container methods
    """

    def __getitem__(self, position) -> Widget:
        """
        Container short-cut for self.contents[position][0].base_widget
        which means "give me the child widget at position without any
        widget decorations".

        This allows for concise traversal of nested container widgets
        such as:

            my_widget[position0][position1][position2] ...
        """
        return self.contents[position][0].base_widget

    def get_focus_path(self) -> list[int | str]:
        """
        Return the .focus_position values starting from this container
        and proceeding along each child widget until reaching a leaf
        (non-container) widget.
        """
        out = []
        w = self
        while True:
            try:
                p = w.focus_position
            except IndexError:
                return out
            out.append(p)
            w = w.focus.base_widget

    def set_focus_path(self, positions: Iterable[int | str]) -> None:
        """
        Set the .focus_position property starting from this container
        widget and proceeding along newly focused child widgets.  Any
        failed assignment due do incompatible position types or invalid
        positions will raise an IndexError.

        This method may be used to restore a particular widget to the
        focus by passing in the value returned from an earlier call to
        get_focus_path().

        positions -- sequence of positions
        """
        w: Widget = self
        for p in positions:
            if p != w.focus_position:
                w.focus_position = p  # modifies w.focus
            w = w.focus.base_widget  # type: ignore[assignment]

    def get_focus_widgets(self) -> list[Widget]:
        """
        Return the .focus values starting from this container
        and proceeding along each child widget until reaching a leaf
        (non-container) widget.

        Note that the list does not contain the topmost container widget
        (i.e., on which this method is called), but does include the
        lowest leaf widget.
        """
        out = []
        w = self
        while (w := w.base_widget.focus) is not None:
            out.append(w)

        return out

    @property
    @abc.abstractmethod
    def focus(self) -> Widget:
        """
        Read-only property returning the child widget in focus for
        container widgets.  This default implementation
        always returns ``None``, indicating that this widget has no children.
        """


class WidgetContainerListContentsMixin:
    """
    Mixin class for widget containers whose positions are indexes into
    a list available as self.contents.
    """

    def __iter__(self) -> Iterator[int]:
        """
        Return an iterable of positions for this container from first
        to last.
        """
        return iter(range(len(self.contents)))

    def __reversed__(self) -> Iterator[int]:
        """
        Return an iterable of positions for this container from last
        to first.
        """
        return iter(range(len(self.contents) - 1, -1, -1))

    def __len__(self) -> int:
        return len(self.contents)

    @property
    @abc.abstractmethod
    def contents(self) -> list[tuple[Widget, typing.Any]]:
        """The contents of container as a list of (widget, options)"""

    @contents.setter
    def contents(self, new_contents: list[tuple[Widget, typing.Any]]) -> None:
        """The contents of container as a list of (widget, options)"""

    @property
    @abc.abstractmethod
    def focus_position(self) -> int | None:
        """
        index of child widget in focus.
        """

    @focus_position.setter
    def focus_position(self, position: int) -> None:
        """
        index of child widget in focus.
        """

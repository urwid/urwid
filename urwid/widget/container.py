"""Mixins that give container widgets their common API."""

from __future__ import annotations

import abc
import enum
import inspect
import typing
import warnings

from urwid.command_map import Command

from .constants import Sizing, WHSettings
from .widget import AbstractWidget, Widget, WidgetWarning, _select_enter_child

if typing.TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, MutableSequence, Sequence

    from urwid.command_map import CommandMap

    _KT_contra = typing.TypeVar("_KT_contra", contravariant=True)

    class WidgetContainerProto(typing.Protocol[_KT_contra]):
        """Structural type for a container's ``contents`` mapping, indexable by position."""

        def __getitem__(
            self,
            index: _KT_contra,
        ) -> tuple[AbstractWidget, typing.Any]:
            """Return the `(widget, options)` entry at `index`."""
            ...

    class WidgetContainerMixinProto(AbstractWidget, typing.Protocol[_KT_contra]):
        """Structural type for a widget exposing ``contents`` and a settable ``focus_position``."""

        @property
        def contents(self) -> WidgetContainerProto[_KT_contra]:
            """Return the container's contents, indexable by position."""
            ...

        @property
        def focus_position(self) -> int | str:
            """Return the position of the container's currently focused element."""
            ...

        @focus_position.setter
        def focus_position(self, position: int | str) -> None: ...

else:
    _KT_contra = typing.TypeVar("_KT_contra", contravariant=True)

    class WidgetContainerMixinProto(typing.Protocol[_KT_contra]):
        """Generic protocol support."""


_ContentsItem = typing.TypeVar("_ContentsItem", bound=tuple[AbstractWidget, typing.Any])


class _ContainerElementSizingFlag(enum.IntEnum):
    """Bitfield describing the sizing modes and the width/height setting a container element supports.

    .. note::
        Ideally this would be an :class:`enum.IntFlag` coupled with :func:`enum.auto`, but doing many bitwise
        operations on an ``IntFlag`` - which happens when widgets are deeply nested - is orders of magnitude
        slower than doing the same operations on an :class:`enum.IntEnum`.
    """

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


_SELECT_COMMANDS: typing.Final = frozenset((Command.SELECT_NEXT, Command.SELECT_PREVIOUS))
# The Widget.focus_position property, which raises IndexError: a container that keeps it has no positions.
_WIDGET_FOCUS_POSITION: typing.Final = inspect.getattr_static(Widget, "focus_position")


class WidgetContainerMixin(WidgetContainerMixinProto[_KT_contra]):
    """Mixin class for widget containers implementing common container methods."""

    def __getitem__(self, position: _KT_contra) -> AbstractWidget:
        """Give the child widget at position without any widget decorations.

        This is a short-cut for self.contents[position][0].base_widget, allowing for concise traversal of nested
        container widgets such as:

            my_widget[position0][position1][position2] ...
        """
        return self.contents[position][0].base_widget

    def get_focus_path(self) -> list[int | str]:
        """Return the .focus_position values starting from this container.

        Proceeds along each child widget until reaching a leaf (non-container) widget.
        """
        out: list[int | str] = []
        w = self
        while True:
            try:
                # pyrefly: ignore[missing-attribute]  # AbstractWidget does not declare focus_position
                p = w.focus_position
            except IndexError:
                return out
            out.append(p)
            if w.focus is None:
                return out
            # a child is not known to be a container; a leaf ends the loop through IndexError above
            w = w.focus.base_widget  # type: ignore[assignment]

    def set_focus_path(self, positions: Iterable[int | str]) -> None:
        """Set the .focus_position property starting from this container widget.

        Proceeds along newly focused child widgets. Any failed assignment due to incompatible position types or
        invalid positions will raise an IndexError.

        This method may be used to restore a particular widget to the
        focus by passing in the value returned from an earlier call to
        get_focus_path().

        :param positions: sequence of positions
        """
        w: WidgetContainerMixin[typing.Any] | AbstractWidget = self
        for p in positions:
            if p != w.focus_position:  # type: ignore[union-attr]
                w.focus_position = p  # type: ignore[union-attr]  # modifies w.focus
            w = w.focus.base_widget  # type: ignore[union-attr]

    def get_focus_widgets(self) -> list[WidgetContainerMixin[typing.Any] | AbstractWidget]:
        """Return the .focus values starting from this container.

        Proceeds along each child widget until reaching a leaf (non-container) widget.

        Note that the list does not contain the topmost container widget
        (i.e., on which this method is called), but does include the
        lowest leaf widget.
        """
        out: list[WidgetContainerMixin[typing.Any] | AbstractWidget] = []
        w: AbstractWidget = self
        while (focus := w.base_widget.focus) is not None:
            out.append(focus)
            w = focus

        return out

    @property
    @abc.abstractmethod
    def focus(self) -> AbstractWidget | None:
        """Read-only property returning the child widget in focus for container widgets.

        This default implementation always returns ``None``, indicating that this widget has no children.
        """


class WidgetContainerListContentsMixin(typing.Generic[_ContentsItem]):
    """Mixin class for widget containers whose positions are indexes into a list available as self.contents."""

    def __iter__(self) -> Iterator[int]:
        """Return an iterable of positions for this container from first to last."""
        return iter(range(len(self.contents)))

    def __reversed__(self) -> Iterator[int]:
        """Return an iterable of positions for this container from last to first."""
        return iter(range(len(self.contents) - 1, -1, -1))

    def __len__(self) -> int:
        """Return the number of items in this container."""
        return len(self.contents)

    @property
    @abc.abstractmethod
    def contents(self) -> MutableSequence[_ContentsItem]:
        """Return the contents of container as a list of (widget, options)."""

    @contents.setter
    def contents(self, new_contents: Sequence[_ContentsItem]) -> None:
        """Set the contents of container from a list of (widget, options)."""

    @property
    @abc.abstractmethod
    def focus_position(self) -> int | None:
        """Index of child widget in focus."""

    @focus_position.setter
    def focus_position(self, position: int) -> None:
        """Index of child widget in focus."""


class SelectNavigationMixin(WidgetContainerMixin[_KT_contra]):
    """Mixin for container widgets that handle the ``'next selectable'`` and ``'prev selectable'`` commands.

    The behaviour is described in :ref:`select-navigation`. A container class that uses it is a :class:`Widget` and:

    - implements the :class:`WidgetContainerMixin` interface, with a settable :attr:`focus_position`;
    - implements :meth:`_select_candidates` and :meth:`_select_enter_focus`;
    - in :meth:`keypress`, passes a select command that its child in focus returned unhandled
      to :meth:`_select_keypress_unhandled` when :attr:`select_navigation` is set.

    :class:`SelectNavigationListContentsMixin` implements both methods for containers with list contents.

    A container that keeps the :attr:`Widget.focus_position` of :class:`Widget`, which raises :exc:`IndexError`,
    is a single stop instead: the select commands are returned unhandled, its focus is not changed,
    and a :class:`WidgetWarning` names the class.
    """

    #: Whether the container handles the ``'next selectable'`` and ``'prev selectable'`` commands.
    #: The urwid containers set it from their ``select_navigation`` argument; the class default
    #: keeps a subclass that does not set it working, with the commands left unhandled.
    select_navigation: bool = False

    if typing.TYPE_CHECKING:
        # Provided by Widget.
        _command_map: CommandMap

    @abc.abstractmethod
    def _select_candidates(self, *, reverse: bool, from_edge: bool) -> Iterator[typing.Any]:
        """Yield the positions of the selectable children in the traversal order.

        Positions are produced lazily, so the search stops at the first one used.

        :param reverse: yield them from the last to the first.
        :param from_edge: start at the first (last when *reverse*) position instead of after the focus.
        """

    @abc.abstractmethod
    def _select_enter_focus(self, *, reverse: bool) -> None:
        """Call ``enter_selectable(reverse=reverse)`` of the child in focus, when it has one."""

    def _select_focus(self, *, reverse: bool, from_edge: bool) -> bool:
        """Focus the first candidate through the ``focus_position`` setter and enter it.

        :returns: whether a selectable candidate exists.
        :warns WidgetWarning: the container has no ``focus_position`` of its own, so its focus is left unchanged.
        """
        if inspect.getattr_static(type(self), "focus_position") is _WIDGET_FOCUS_POSITION:
            warnings.warn(
                f"{type(self).__name__} has no focus_position of its own: select navigation leaves its focus unchanged",
                WidgetWarning,
                stacklevel=3,
            )
            return False
        for position in self._select_candidates(reverse=reverse, from_edge=from_edge):
            self.focus_position = position
            self._select_enter_focus(reverse=reverse)
            return True
        return False

    def _select_keypress_unhandled(self, key: str) -> str | None:
        """Handle a select command that the child in focus returned unhandled.

        Move the focus to the next (previous) selectable child and enter it.
        Past the last (first) one, focus the first (last) selectable child, enter it and return *key*,
        so an opted-in parent moves on to its own next child.
        """
        reverse = self._command_map[key] == Command.SELECT_PREVIOUS
        if self._select_focus(reverse=reverse, from_edge=False):
            return None
        self._select_focus(reverse=reverse, from_edge=True)
        return key

    def focus_first_selectable(self) -> bool:
        """Focus the first selectable child through the :attr:`focus_position` setter and enter it.

        It acts whether or not :attr:`select_navigation` is set, see :ref:`select-navigation`.

        :returns: whether a selectable child exists.
        """
        return self._select_focus(reverse=False, from_edge=True)

    def focus_last_selectable(self) -> bool:
        """Focus the last selectable child through the :attr:`focus_position` setter and enter it.

        It acts whether or not :attr:`select_navigation` is set, see :ref:`select-navigation`.

        :returns: whether a selectable child exists.
        """
        return self._select_focus(reverse=True, from_edge=True)

    def enter_selectable(self, *, reverse: bool = False) -> None:
        """Start at the first selectable child, or at the last one when *reverse* is set.

        It is the entry hook a parent container calls, and acts only when :attr:`select_navigation` is set,
        see :ref:`select-navigation`.

        :param reverse: start at the last selectable child instead of the first one.
        """
        if self.select_navigation:
            self._select_focus(reverse=reverse, from_edge=True)


class SelectNavigationListContentsMixin(
    SelectNavigationMixin[int],
    WidgetContainerListContentsMixin[_ContentsItem],
):
    """:class:`SelectNavigationMixin` for containers whose positions are indexes into ``self.contents``.

    It implements :meth:`_select_candidates` and :meth:`_select_enter_focus` from ``contents`` and
    ``focus_position`` only, in the order of ``contents``. A child whose options start with ``(GIVEN, 0)``
    is not drawn, so it is not a candidate.
    """

    # Both base mixins declare `contents` and `focus_position`, with types that differ: this mixin uses the list forms.
    @property
    @abc.abstractmethod
    def contents(self) -> MutableSequence[_ContentsItem]:
        """Return the contents of container as a list of (widget, options)."""

    @contents.setter
    def contents(self, new_contents: Sequence[_ContentsItem]) -> None:
        """Set the contents of container from a list of (widget, options)."""

    @property
    @abc.abstractmethod
    def focus_position(self) -> int:
        """Index of child widget in focus."""

    @focus_position.setter
    def focus_position(self, position: int) -> None:
        """Index of child widget in focus."""

    def _select_candidates(self, *, reverse: bool, from_edge: bool) -> Iterator[int]:
        """Yield the positions of the selectable children in the order of ``contents``, skipping hidden ones."""
        contents = self.contents
        # A child may have emptied the container while handling the key: there is no focus to start from then.
        if not contents:
            return
        if from_edge:
            positions = range(len(contents) - 1, -1, -1) if reverse else range(len(contents))
        else:
            focus = self.focus_position
            positions = range(focus - 1, -1, -1) if reverse else range(focus + 1, len(contents))
        for position in positions:
            widget, options = contents[position]
            # A container defined outside urwid may keep options of any shape.
            hidden = isinstance(options, tuple) and options[:2] == (WHSettings.GIVEN, 0)
            if widget.selectable() and not hidden:
                yield position

    def _select_enter_focus(self, *, reverse: bool) -> None:
        _select_enter_child(self.contents[self.focus_position][0], reverse=reverse)

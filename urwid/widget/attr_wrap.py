from __future__ import annotations

import typing
import warnings

from .attr_map import AttrMap

if typing.TYPE_CHECKING:
    from collections.abc import Hashable

    from .constants import Sizing
    from .widget import Widget


class AttrWrap(AttrMap):
    def __init__(self, w: Widget, attr, focus_attr=None):
        """
        w -- widget to wrap (stored as self.original_widget)
        attr -- attribute to apply to w
        focus_attr -- attribute to apply when in focus, if None use attr

        This widget is a special case of the new AttrMap widget, and it
        will pass all function calls and variable references to the wrapped
        widget.  This class is maintained for backwards compatibility only,
        new code should use AttrMap instead.

        >>> from urwid import Divider, Edit, Text
        >>> AttrWrap(Divider(u"!"), 'bright')
        <AttrWrap flow widget <Divider flow widget '!'> attr='bright'>
        >>> AttrWrap(Edit(), 'notfocus', 'focus')
        <AttrWrap selectable flow widget <Edit selectable flow widget '' edit_pos=0> attr='notfocus' focus_attr='focus'>
        >>> size = (5,)
        >>> aw = AttrWrap(Text(u"hi"), 'greeting', 'fgreet')
        >>> next(aw.render(size, focus=False).content())
        [('greeting', None, ...'hi   ')]
        >>> next(aw.render(size, focus=True).content())
        [('fgreet', None, ...'hi   ')]
        """
        warnings.warn(
            "AttrWrap is maintained for backwards compatibility only, new code should use AttrMap instead.",
            PendingDeprecationWarning,
            stacklevel=2,
        )
        super().__init__(w, attr, focus_attr)

    def _repr_attrs(self) -> dict[str, typing.Any]:
        # only include the focus_attr when it takes effect (not None)
        d = {**super()._repr_attrs(), "attr": self.attr}
        del d["attr_map"]
        if "focus_map" in d:
            del d["focus_map"]
        if self.focus_attr is not None:
            d["focus_attr"] = self.focus_attr
        return d

    @property
    def w(self) -> Widget:
        """backwards compatibility, widget used to be stored as w"""
        warnings.warn(
            "backwards compatibility, widget used to be stored as original_widget",
            PendingDeprecationWarning,
            stacklevel=2,
        )
        return self.original_widget

    @w.setter
    def w(self, new_widget: Widget) -> None:
        warnings.warn(
            "backwards compatibility, widget used to be stored as original_widget",
            PendingDeprecationWarning,
            stacklevel=2,
        )
        self.original_widget = new_widget

    def get_w(self):
        warnings.warn(
            "backwards compatibility, widget used to be stored as original_widget",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.original_widget

    def set_w(self, new_widget: Widget) -> None:
        warnings.warn(
            "backwards compatibility, widget used to be stored as original_widget",
            DeprecationWarning,
            stacklevel=2,
        )
        self.original_widget = new_widget

    def get_attr(self) -> Hashable:
        return self.attr_map[None]

    def set_attr(self, attr: Hashable) -> None:
        """
        Set the attribute to apply to the wrapped widget

        >> w = AttrWrap(Divider("-"), None)
        >> w.set_attr('new_attr')
        >> w
        <AttrWrap flow widget <Divider flow widget '-'> attr='new_attr'>
        """
        self.set_attr_map({None: attr})

    attr = property(get_attr, set_attr)

    def get_focus_attr(self) -> Hashable | None:
        focus_map = self.focus_map
        if focus_map:
            return focus_map[None]
        return None

    def set_focus_attr(self, focus_attr: Hashable) -> None:
        """
        Set the attribute to apply to the wapped widget when it is in
        focus

        If None this widget will use the attr instead (no change when in
        focus).

        >> w = AttrWrap(Divider("-"), 'old')
        >> w.set_focus_attr('new_attr')
        >> w
        <AttrWrap flow widget <Divider flow widget '-'> attr='old' focus_attr='new_attr'>
        >> w.set_focus_attr(None)
        >> w
        <AttrWrap flow widget <Divider flow widget '-'> attr='old'>
        """
        self.set_focus_map({None: focus_attr})

    focus_attr = property(get_focus_attr, set_focus_attr)

    def __getattr__(self, name: str):
        """
        Call getattr on wrapped widget.  This has been the longstanding
        behaviour of AttrWrap, but is discouraged.  New code should be
        using AttrMap and .base_widget or .original_widget instead.
        """
        return getattr(self._original_widget, name)

    def sizing(self) -> frozenset[Sizing]:
        return self._original_widget.sizing()

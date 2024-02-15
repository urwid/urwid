from __future__ import annotations

import typing
from collections.abc import Hashable, Mapping

from urwid.canvas import CompositeCanvas

from .widget import WidgetError, delegate_to_widget_mixin
from .widget_decoration import WidgetDecoration

WrappedWidget = typing.TypeVar("WrappedWidget")


class AttrMapError(WidgetError):
    pass


class AttrMap(delegate_to_widget_mixin("_original_widget"), WidgetDecoration[WrappedWidget]):
    """
    AttrMap is a decoration that maps one set of attributes to another.
    This object will pass all function calls and variable references to the
    wrapped widget.
    """

    def __init__(
        self,
        w: WrappedWidget,
        attr_map: Hashable | Mapping[Hashable | None, Hashable] | None,
        focus_map: Hashable | Mapping[Hashable | None, Hashable] | None = None,
    ) -> None:
        """
        :param w: widget to wrap (stored as self.original_widget)
        :type w: widget

        :param attr_map: attribute to apply to *w*, or dict of old display
            attribute: new display attribute mappings
        :type attr_map: display attribute or dict

        :param focus_map: attribute to apply when in focus or dict of
            old display attribute: new display attribute mappings;
            if ``None`` use *attr*
        :type focus_map: display attribute or dict

        >>> from urwid import Divider, Edit, Text
        >>> AttrMap(Divider(u"!"), 'bright')
        <AttrMap flow widget <Divider flow widget '!'> attr_map={None: 'bright'}>
        >>> AttrMap(Edit(), 'notfocus', 'focus').attr_map
        {None: 'notfocus'}
        >>> AttrMap(Edit(), 'notfocus', 'focus').focus_map
        {None: 'focus'}
        >>> size = (5,)
        >>> am = AttrMap(Text(u"hi"), 'greeting', 'fgreet')
        >>> next(am.render(size, focus=False).content()) # ... = b in Python 3
        [('greeting', None, ...'hi   ')]
        >>> next(am.render(size, focus=True).content())
        [('fgreet', None, ...'hi   ')]
        >>> am2 = AttrMap(Text(('word', u"hi")), {'word':'greeting', None:'bg'})
        >>> am2
        <AttrMap fixed/flow widget <Text fixed/flow widget 'hi'> attr_map={'word': 'greeting', None: 'bg'}>
        >>> next(am2.render(size).content())
        [('greeting', None, ...'hi'), ('bg', None, ...'   ')]
        """
        super().__init__(w)

        if isinstance(attr_map, Mapping):
            self.attr_map = dict(attr_map)
        else:
            self.attr_map = {None: attr_map}

        if isinstance(focus_map, Mapping):
            self.focus_map = dict(focus_map)
        elif focus_map is None:
            self.focus_map = focus_map
        else:
            self.focus_map = {None: focus_map}

    def _repr_attrs(self) -> dict[str, typing.Any]:
        # only include the focus_attr when it takes effect (not None)
        d = {**super()._repr_attrs(), "attr_map": self._attr_map}
        if self._focus_map is not None:
            d["focus_map"] = self._focus_map
        return d

    def get_attr_map(self) -> dict[Hashable | None, Hashable]:
        # make a copy so ours is not accidentally modified
        # FIXME: a dictionary that detects modifications would be better
        return dict(self._attr_map)

    def set_attr_map(self, attr_map: dict[Hashable | None, Hashable] | None) -> None:
        """
        Set the attribute mapping dictionary {from_attr: to_attr, ...}

        Note this function does not accept a single attribute the way the
        constructor does.  You must specify {None: attribute} instead.

        >>> from urwid import Text
        >>> w = AttrMap(Text(u"hi"), None)
        >>> w.set_attr_map({'a':'b'})
        >>> w
        <AttrMap fixed/flow widget <Text fixed/flow widget 'hi'> attr_map={'a': 'b'}>
        """
        for from_attr, to_attr in attr_map.items():
            if not isinstance(from_attr, Hashable) or not isinstance(to_attr, Hashable):
                raise AttrMapError(
                    f"{from_attr!r}:{to_attr!r} attribute mapping is invalid. Attributes must be hashable"
                )

        self._attr_map = attr_map
        self._invalidate()

    attr_map = property(get_attr_map, set_attr_map)

    def get_focus_map(self) -> dict[Hashable | None, Hashable] | None:
        # make a copy so ours is not accidentally modified
        # FIXME: a dictionary that detects modifications would be better
        if self._focus_map:
            return dict(self._focus_map)
        return None

    def set_focus_map(self, focus_map: dict[Hashable | None, Hashable] | None) -> None:
        """
        Set the focus attribute mapping dictionary
        {from_attr: to_attr, ...}

        If None this widget will use the attr mapping instead (no change
        when in focus).

        Note this function does not accept a single attribute the way the
        constructor does.  You must specify {None: attribute} instead.

        >>> from urwid import Text
        >>> w = AttrMap(Text(u"hi"), {})
        >>> w.set_focus_map({'a':'b'})
        >>> w
        <AttrMap fixed/flow widget <Text fixed/flow widget 'hi'> attr_map={} focus_map={'a': 'b'}>
        >>> w.set_focus_map(None)
        >>> w
        <AttrMap fixed/flow widget <Text fixed/flow widget 'hi'> attr_map={}>
        """
        if focus_map is not None:
            for from_attr, to_attr in focus_map.items():
                if not isinstance(from_attr, Hashable) or not isinstance(to_attr, Hashable):
                    raise AttrMapError(
                        f"{from_attr!r}:{to_attr!r} attribute mapping is invalid. Attributes must be hashable"
                    )
        self._focus_map = focus_map
        self._invalidate()

    focus_map = property(get_focus_map, set_focus_map)

    def render(self, size, focus: bool = False) -> CompositeCanvas:
        """
        Render wrapped widget and apply attribute. Return canvas.
        """
        attr_map = self._attr_map
        if focus and self._focus_map is not None:
            attr_map = self._focus_map
        canv = self._original_widget.render(size, focus=focus)
        canv = CompositeCanvas(canv)
        canv.fill_attr_apply(attr_map)
        return canv

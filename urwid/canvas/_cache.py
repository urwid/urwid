# Urwid canvas class and functions
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


"""Cache of finalized widget canvases, keyed by widget and render arguments."""

from __future__ import annotations

import typing
import weakref

if typing.TYPE_CHECKING:
    from urwid.canvas._base import Canvas
    from urwid.widget import AbstractWidget


def _walk_depends(canv: Canvas) -> list[AbstractWidget]:
    """Collect all child widgets of *canv* for determining who a cached canvas depends on."""
    # FIXME: is this recursion necessary?  The cache invalidating might work with only one level.
    depends = []
    for _x, _y, c, _pos in canv.children:  # type: ignore[attr-defined]  # we made `hasattr` check
        if c.widget_info:
            depends.append(c.widget_info[0])
        elif hasattr(c, "children"):
            depends.extend(_walk_depends(c))
    return depends


class CanvasCache:
    """Cache for rendered canvases.

    Automatically populated and accessed by Widget render() MetaClass magic, cleared by
    Widget._invalidate().

    Stores weakrefs to the canvas objects, so an external class
    must maintain a reference for this cache to be effective.
    At present the Screen classes store the last topmost canvas
    after redrawing the screen, keeping the canvases from being
    garbage collected.

    _widgets[widget] = {(wcls, size, focus): weakref.ref(canvas), ...}
    _refs[weakref.ref(canvas)] = (widget, wcls, size, focus)
    _deps[widget] = {dependent_widget, ...}
    _children[dependent_widget] = {widget, ...}

    _children is the reverse of _deps.
    It removes a dependent widget from _deps once that widget has no cached canvas left.
    Widgets are not guaranteed to be weak-referenceable, so neither index can use weak references.
    """

    _widgets: typing.ClassVar[
        dict[
            AbstractWidget,
            dict[
                tuple[type[AbstractWidget], tuple[int, int] | tuple[int] | tuple[()], bool],
                weakref.ReferenceType[Canvas],
            ],
        ]
    ] = {}
    _refs: typing.ClassVar[
        dict[
            weakref.ReferenceType[Canvas],
            tuple[AbstractWidget, type[AbstractWidget], tuple[int, int] | tuple[int] | tuple[()], bool],
        ]
    ] = {}
    _deps: typing.ClassVar[dict[AbstractWidget, set[AbstractWidget]]] = {}
    _children: typing.ClassVar[dict[AbstractWidget, set[AbstractWidget]]] = {}
    hits = 0
    fetches = 0
    cleanups = 0

    @classmethod
    def store(cls, wcls: type[AbstractWidget], canvas: Canvas) -> None:
        """
        Store a weakref to canvas in the cache.

        :param wcls: widget class that contains render() function
        :param canvas: rendered canvas with widget_info (widget, size, focus)
        :raises TypeError: *canvas* has not been finalized, so it carries no widget_info.
        """
        if not canvas.cacheable:
            return

        info = canvas.widget_info
        if not info:
            raise TypeError("Can't store canvas without widget_info")
        widget, size, focus = info

        # use explicit depends_on if available from the canvas
        depends_on = getattr(canvas, "depends_on", None)
        if depends_on is None and hasattr(canvas, "children"):
            depends_on = _walk_depends(canvas)
        widgets = cls._widgets
        if depends_on:
            for w in depends_on:
                if w not in widgets:
                    return

        # cleanup() is a weakref callback and can run between any two lines below.
        # It drops a widget's dependencies once its sizes are empty,
        # so they are added only after the live canvas keeps the sizes non-empty.
        key = (wcls, size, focus)
        ref = weakref.ref(canvas, cls.cleanup)
        cls._refs[ref] = (widget, wcls, size, focus)
        sizes = widgets.get(widget)
        if sizes is None:
            sizes = widgets[widget] = {key: ref}
        else:
            sizes[key] = ref
        if not depends_on or widgets.get(widget) is not sizes:
            # A cleanup dropped the emptied sizes before ref was added to them: the canvas is not cached.
            return

        cls._children.setdefault(widget, set()).update(depends_on)
        deps = cls._deps
        for w in depends_on:
            deps.setdefault(w, set()).add(widget)
            if widget not in deps.get(w, ()):
                # A cleanup emptied and dropped the set between the lookup and the add.
                deps[w] = {widget}

    @classmethod
    def fetch(
        cls,
        widget: AbstractWidget,
        wcls: type[AbstractWidget],
        size: tuple[int, int] | tuple[int] | tuple[()],
        focus: bool,
    ) -> Canvas | None:
        """
        Return the cached canvas or None.

        :param widget: widget object requested
        :param wcls: widget class that contains render() function
        :param size: size parameter passed to the widget's render method
        :param focus: focus parameter passed to the widget's render method
        """
        cls.fetches += 1  # collect stats

        sizes = cls._widgets.get(widget, None)
        if not sizes:
            return None
        ref = sizes.get((wcls, size, focus), None)
        if not ref:
            return None
        canv = ref()
        if canv:
            cls.hits += 1  # more stats
        return canv

    @classmethod
    def invalidate(cls, widget: AbstractWidget) -> None:
        """Remove all canvases cached for widget."""
        sizes = cls._widgets.pop(widget, None)
        if sizes:
            refs = cls._refs
            for ref in sizes.values():
                refs.pop(ref, None)
        cls._forget(widget)

        # The popped set is out of reach of every other frame, so the recursion cannot change it.
        dependants = cls._deps.pop(widget, None)
        if not dependants:
            return
        for w in dependants:
            cls.invalidate(w)

    @classmethod
    def cleanup(cls, ref: weakref.ReferenceType[Canvas]) -> None:
        """Drop the cache entry for a canvas weakref once the canvas it points to has been garbage collected."""
        cls.cleanups += 1  # collect stats

        w = cls._refs.pop(ref, None)
        if not w:
            return
        widget, wcls, size, focus = w
        key = (wcls, size, focus)
        sizes = cls._widgets.get(widget, None)
        # A later store() for the same key replaced ref: that entry belongs to a live canvas.
        if not sizes or sizes.get(key) is not ref:
            return
        sizes.pop(key, None)
        if not sizes:
            cls._widgets.pop(widget, None)
            # Dependants still cached under another key must not keep this widget alive through _children.
            children = cls._children
            for dependant in cls._deps.pop(widget, ()):
                siblings = children.get(dependant)
                if siblings is not None:
                    siblings.discard(widget)
            cls._forget(widget)

    @classmethod
    def _forget(cls, widget: AbstractWidget) -> None:
        """Remove *widget* from the dependants of every widget its cached canvases depended on."""
        # Iterate the popped set: no other frame can reach it, so a nested cleanup() cannot change it.
        children = cls._children.pop(widget, None)
        if not children:
            return
        deps = cls._deps
        for child in children:
            dependants = deps.get(child)
            if dependants is not None:
                dependants.discard(widget)
                if not dependants:
                    deps.pop(child, None)

    @classmethod
    def clear(cls) -> None:
        """Empty the cache."""
        cls._widgets = {}
        cls._refs = {}
        cls._deps = {}
        cls._children = {}

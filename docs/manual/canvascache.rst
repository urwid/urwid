.. _canvas-cache:

****************
  Canvas Cache
****************

.. currentmodule:: urwid

In an Urwid application each time the screen is redrawn typically only part of
the screen actually needs to be updated. A canvas cache is used to store
visible, unchanged canvases so that not all of the visible widgets need to be
rendered for each update.

The :class:`Widget` base class uses some metaclass magic to
capture the canvas objects returned when :meth:`Widget.render` is called and return
them the next time :meth:`Widget.render` is called again with the same parameters. The
:meth:`Widget._invalidate` method is provided as a way to remove cached widgets so
that changes to the widget are visible the next time the screen is redrawn.

Similar metaclass magic is used for flow widgets' :meth:`Widget.rows` method. If a
canvas for that widget with the same parameters is cached then the rows of that
canvas are returned instead of calling the widget's actual :meth:`Widget.rows` method.

Composite Canvases
==================

When container and decoration widgets are rendered, they collect the canvases
returned by their children and arrange them into a composite canvas. Composite
canvases are nested to form a tree with the topmost widget's :meth:`Widget.render`
method returning the root of the tree. That canvas is sent to the display
module to be rendered on the screen.

Composite canvases reference the content and layout from their children,
reducing the number of copies required to build them. When a canvas is removed
from the cache by a call to :meth:`Widget._invalidate` all the direct parents of that
canvas are removed from the cache as well, forcing those widgets to be re-drawn
on the next screen update. This cascade-removal happens only once per update
(the canvas is then no longer in the cache) so batched changes to visible
widgets may be made efficiently. This is important when a user's input gets
ahead of the screen updating -- Urwid handles all the pending input first then
updates the screen with the final result, instead of falling further and
further behind.

Cache Lifetime
==============

The canvases "stored" in the canvas cache are actually weak references to the
canvases. The canvases must have a real reference somewhere for the cache to
function properly. Urwid's display modules store the currently displayed
topmost canvas for this reason. All canvases that are visible on the screen
will remain in the cache, and others will be garbage collected.

Future Work
===========

An updating method that invalidates regions of the display without redrawing
parent widgets would be more efficient for the common case of a single change
on the screen that does not affect the screen layout. Send an email to the
mailing list if you're interested in helping with this or other display
optimizations.

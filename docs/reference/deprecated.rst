Deprecated Classes
------------------

.. currentmodule:: urwid

.. autoclass:: AttrWrap

.. data:: MetaSuper

   Alias of :class:`type`, kept so that class definitions naming it keep importing.
   Drop it from ``metaclass=`` arguments and from base lists; while it is still listed as a base, it has to be the last one.
   The name will be removed in version 7.0.

Deprecated Import Paths
-----------------------

.. deprecated:: 2.4.0
    The display modules moved into the :mod:`urwid.display` package.
    The old names will be removed in version 6.0.

    .. list-table::
       :header-rows: 1

       * - Old import
         - New import
       * - ``urwid.display_common``
         - ``urwid.display.common``
       * - ``urwid.raw_display``
         - ``urwid.display.raw``
       * - ``urwid.curses_display``
         - ``urwid.display.curses``
       * - ``urwid.escape``
         - ``urwid.display.escape``

.. deprecated:: 2.6.0
    Names defined in ``urwid.str_util`` and reachable as attributes of ``urwid.util`` (``from urwid.util import ...``)
    have to be imported from ``urwid`` instead.

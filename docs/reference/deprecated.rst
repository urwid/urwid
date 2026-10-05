Deprecated Classes
------------------

.. currentmodule:: urwid

.. autoclass:: AttrWrap

.. data:: MetaSuper

   Alias of :class:`type`, kept so that class definitions naming it keep importing.
   Drop it from ``metaclass=`` arguments and from base lists; while it is still listed as a base, it has to be the last one.
   The name will be removed.

# Urwid selector construction
#    Copyright (C) 2026  urwid contributors
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
"""Selectors for descriptors that the application supplies, such as its terminal input."""

from __future__ import annotations

import contextlib
import errno
import selectors
import typing

if typing.TYPE_CHECKING:
    from collections.abc import Iterable

    from _typeshed import FileDescriptorLike

__all__ = ("read_selector",)


def read_selector(files: Iterable[tuple[FileDescriptorLike, typing.Any]]) -> selectors.BaseSelector:
    """Return a selector with every file of *files* registered for reading, each with its data.

    :class:`selectors.DefaultSelector` is used when it accepts every file.
    When it refuses one with ``EINVAL``, :class:`selectors.SelectSelector` is used instead:
    on macOS ``kqueue`` refuses a descriptor opened from ``/dev/tty`` this way, and ``poll`` does not support it either.

    :param files: pairs of a file object or descriptor and the data to register it with.
    :returns: the selector, which the caller closes.
    :raises OSError: a file could not be registered.
    """
    files = tuple(files)
    try:
        return _register(selectors.DefaultSelector(), files)
    except OSError as exc:
        if exc.errno != errno.EINVAL:
            raise
    return _register(selectors.SelectSelector(), files)


def _register(
    selector: selectors.BaseSelector,
    files: Iterable[tuple[FileDescriptorLike, typing.Any]],
) -> selectors.BaseSelector:
    """Register every file of *files* with *selector* for reading and return *selector*, closed if one is refused."""
    with contextlib.ExitStack() as on_error:
        on_error.callback(selector.close)
        for fileobj, data in files:
            selector.register(fileobj, selectors.EVENT_READ, data)
        on_error.pop_all()
    return selector

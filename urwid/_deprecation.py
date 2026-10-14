# Urwid deprecation warnings
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
"""Deprecation warnings with one message format, attributed to the first caller outside urwid.

A callable deprecated as a whole is also decorated with ``@deprecated(..., category=None)``,
so that static type checkers report its use while the run-time warning still comes from :func:`warn`.
The decorator's message repeats the format of :func:`warn`, because the checkers read it only from a string literal.
A module imports the decorator by name, as ``typing_extensions.deprecated`` under ``typing.TYPE_CHECKING``
and from this module otherwise:
Pyrefly recognises the decorator neither through a re-export nor through an import under a ``sys.version_info`` check.
"""

from __future__ import annotations

import inspect
import os
import pathlib
import sys
import typing
import warnings

if sys.version_info >= (3, 13):
    from warnings import deprecated
else:
    from typing_extensions import deprecated

__all__ = ("deprecated", "warn")

# Frames from files under this directory belong to urwid and are skipped when choosing the warning location.
_PACKAGE_PREFIX: typing.Final[str] = f"{pathlib.Path(__file__).absolute().parent}{os.sep}"


def warn(message: str, *, since: str, removed_in: str | None) -> None:
    """Emit a :exc:`DeprecationWarning` attributed to the first frame outside urwid.

    The warning points at the application line that used the deprecated API,
    also when the check runs several urwid frames deep (a ``Padding`` passing its argument to ``WidgetDecoration``).
    Python shows a :exc:`DeprecationWarning` by default only when it is attributed to ``__main__``.

    :param message: what is deprecated and what to use instead, as complete sentences
    :param since: the release that deprecated it
    :param removed_in: the release that removes it, or ``None`` when no removal release is decided
    """
    if removed_in is None:
        full_message = f"{message} Deprecated since urwid {since}."
    else:
        full_message = f"{message} Deprecated since urwid {since}, will be removed in version {removed_in}."

    if sys.version_info >= (3, 12):
        warnings.warn(full_message, DeprecationWarning, skip_file_prefixes=(_PACKAGE_PREFIX,))
    else:
        # The frame calling warnings.warn() is stack level 1.
        frame = inspect.currentframe()
        stacklevel = 1
        while frame is not None and frame.f_code.co_filename.startswith(_PACKAGE_PREFIX):
            frame = frame.f_back
            stacklevel += 1
        warnings.warn(full_message, DeprecationWarning, stacklevel=stacklevel)

# Urwid standalone ANSI/VT100 escape-sequence line parser
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

"""Resolve the bodies of OSC title, OSC 8 hyperlink and keyboard-LED sequences, for both parsers."""

from __future__ import annotations

import typing

from urwid.display import NO_HYPERLINK, AttrSpec, Hyperlink
from urwid.display.common import _depth

#: Recognised, ready-to-render values of :attr:`ParsedLine.leds`.
LedsLiteral = "Literal['clear', 'scroll_lock', 'num_lock', 'caps_lock']"

_LED_STATES: dict[int, str] = {
    0: "clear",
    1: "scroll_lock",
    2: "num_lock",
    3: "caps_lock",
}


def led_state(mode: int) -> str | None:
    """Map a keyboard-LED ``CSI n q`` mode number to its urwid-facing state name.

    Shared by :class:`AnsiParser` and :mod:`urwid.canvas.term`'s ``TermCanvas.csi_set_keyboard_leds`` so the LED code
    mapping is maintained in exactly one place.

    :param mode: the ``CSI n q`` mode number to resolve.
    :returns: one of ``"clear"``, ``"scroll_lock"``, ``"num_lock"`` or ``"caps_lock"``, or ``None`` if ``mode`` is
        not recognised.

    >>> led_state(0)
    'clear'
    >>> led_state(3)
    'caps_lock'
    >>> led_state(99) is None
    True
    """
    return _LED_STATES.get(mode)


def resolve_osc_title(buf: str) -> str | None:
    """Resolve the window-title text encoded in an OSC command body, if it matches a recognised title prefix.

    Applies the same prefix rules xterm and :mod:`urwid.canvas.term` use to recognise an OSC window-title request -- a
    body starting (after stripping leading zeros) with ``;``, ``0;`` or ``2;`` -- and returns the text following
    the first ``;``. Returns ``None`` for any other OSC body (e.g. an unrecognised or palette-setting OSC), rather
    than raising.

    :param buf: the OSC command body, excluding the ``ESC ]`` framing and terminator.
    :returns: the resolved window-title text, or ``None`` if ``buf`` does not match a recognised title prefix.

    >>> resolve_osc_title(";hello")
    'hello'
    >>> resolve_osc_title("2;hello")
    'hello'
    >>> resolve_osc_title("666not a title") is None
    True
    """
    stripped = buf.lstrip("0")
    if stripped.startswith((";", "0;", "2;")):
        return stripped.partition(";")[2]
    return None


def resolve_osc_hyperlink(buf: str) -> Hyperlink | None:
    """Resolve the hyperlink an OSC 8 command body starts or ends.

    The body is ``8;params;URI`` after leading zeros are stripped, as :func:`resolve_osc_title` strips them.
    *params* are ``key=value`` pairs separated by ``:``; ``id`` is used and other keys are ignored,
    as the OSC 8 specification asks.

    :param buf: the OSC command body, excluding the ``ESC ]`` framing and terminator.
    :returns: the link the following text is drawn with, :data:`~urwid.NO_HYPERLINK` when the body ends the link
        (an empty URI), or ``None`` when ``buf`` is not an OSC 8 command.
    :raises ValueError: ``buf`` is an OSC 8 command without the URI field,
        or with a URI or id :class:`~urwid.Hyperlink` refuses.

    >>> resolve_osc_hyperlink("8;id=home;https://urwid.org")
    Hyperlink(uri='https://urwid.org', id='home')
    >>> resolve_osc_hyperlink("8;;") is NO_HYPERLINK
    True
    >>> resolve_osc_hyperlink("2;title") is None
    True
    """
    stripped = buf.lstrip("0")
    if not stripped.startswith("8;"):
        return None
    params, sep, uri = stripped[2:].partition(";")
    if not sep:
        raise ValueError(f"OSC 8 command without a URI field: {buf!r}")
    if not uri:
        return NO_HYPERLINK
    link_id = ""
    for param in params.split(":"):
        key, _, value = param.partition("=")
        if key == "id":
            link_id = value
    return Hyperlink(uri, id=link_id)


def attrspec_with_hyperlink(
    attrspec: AttrSpec | None,
    link: Hyperlink | None,
    *,
    unset_color: typing.Literal["default", "inherit"],
) -> AttrSpec | None:
    """Return *attrspec* with its hyperlink replaced by *link*, in the form :func:`sgi_params_to_attrspec` returns.

    :data:`~urwid.NO_HYPERLINK` and ``None`` both mean that the text has no link of its own.
    The result is a plain :class:`~urwid.AttrSpec`, as from :func:`sgi_params_to_attrspec`, so a subclass of
    *attrspec* whose constructor takes no *hyperlink* keyword cannot make parsing raise.

    :param attrspec: the attribute in effect, or ``None`` for "no attributes".
    :param link: the link to set, :data:`~urwid.NO_HYPERLINK` or ``None`` to remove the link.
    :param unset_color: the color of a foreground or background no SGR parameter has set, as for
        :func:`sgi_params_to_attrspec`.
    :returns: the resulting attribute, or ``None`` when it sets neither colors, settings nor a link.

    >>> attrspec_with_hyperlink(None, Hyperlink("https://urwid.org"), unset_color="inherit")
    AttrSpec('inherit', 'inherit', hyperlink=Hyperlink(uri='https://urwid.org', id=''))
    >>> attrspec_with_hyperlink(AttrSpec(hyperlink="https://urwid.org"), None, unset_color="inherit") is None
    True
    """
    if link == NO_HYPERLINK:
        link = None
    if attrspec is None:
        if link is None:
            return None
        return AttrSpec(unset_color, unset_color, hyperlink=link)
    if link is None and attrspec.foreground == attrspec.background == unset_color and attrspec.underline_color is None:
        return None
    return AttrSpec(
        attrspec.foreground,
        attrspec.background,
        # the mode the spec was made for, not the colors it needs, so a 24-bit spec stays equal to itself
        _depth.declared_mode(attrspec),
        hyperlink=link,
        underline_color=attrspec.underline_color,
    )

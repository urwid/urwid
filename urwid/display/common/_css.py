# Urwid common display code
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


"""CSS for :class:`AttrSpec` and hyperlinks, for the web displays."""

from __future__ import annotations

import functools
import types
import typing

from urwid.display.common._attr_spec import (
    _RESOLVED_ATTRS_LIMIT,
    AttrSpec,
    Hyperlink,
)

if typing.TYPE_CHECKING:
    from collections.abc import Mapping


# the CSS text-decoration-style of each underline style other than a single one
_CSS_UNDERLINE_STYLES: Mapping[str | None, str] = types.MappingProxyType(
    {"double": "double", "curly": "wavy", "dotted": "dotted", "dashed": "dashed"},
)
# URI schemes an HTML-producing screen turns into a link, none of which can run script in the page
_BROWSER_SCHEMES = frozenset({"file", "http", "https", "mailto", "sftp"})


def _browser_href(link: Hyperlink) -> str | None:
    """Return the URI of *link* to use as an HTML ``href``, or ``None`` when a browser must not follow it.

    The URI is stripped of spaces the way the WHATWG URL parser strips it before reading the scheme
    (the control characters it also strips cannot occur in a :class:`Hyperlink`).
    Only the schemes in ``_BROWSER_SCHEMES`` are allowed, so a link can never run script in the page.

    >>> _browser_href(Hyperlink(" https://urwid.org"))
    'https://urwid.org'
    >>> _browser_href(Hyperlink("JaVaScRiPt:alert(1)")) is None
    True
    """
    href = link.uri.strip(" ")
    scheme, sep, _rest = href.partition(":")
    if sep and scheme.lower() in _BROWSER_SCHEMES:
        return href
    return None


#: default RGB values substituted for a palette entry's 'default' foreground/background,
#: matching the black-on-light-gray terminal default used by the HTML-producing screens
_default_aspec = AttrSpec("black", "light gray")
_default_fg_rgb = _default_aspec.get_rgb_values()[:3]
_default_bg_rgb = _default_aspec.get_rgb_values()[3:]


def attr_spec_to_css(aspec: AttrSpec) -> tuple[str, str, str]:
    """Return the (foreground, background, extra CSS declarations) hex colors for *aspec*.

    Covers every :class:`AttrSpec` display setting a browser can render: color (falling back to
    the default black-on-light-gray for an unset foreground/background), ``standout`` (swaps
    foreground and background), ``underline``/``strikethrough`` (combined into one
    ``text-decoration``), ``bold``, ``italics``, ``blink`` (a step-start CSS animation of the text and its lines,
    which leaves the background drawn, since the ``text-decoration:blink`` value browsers used to support has been
    dropped) and ``faint``.
    The style and the color of an underline become the ``text-decoration`` style and color,
    which a browser also gives the line of ``strikethrough`` drawn with it.
    The hyperlink is not part of the style.
    """
    return _style_to_css(aspec.style_only())


@functools.lru_cache(maxsize=_RESOLVED_ATTRS_LIMIT)
def _style_to_css(aspec: AttrSpec) -> tuple[str, str, str]:
    """Return :func:`attr_spec_to_css` for an attribute without a hyperlink, cached per style."""
    fg_r, fg_g, fg_b, bg_r, bg_g, bg_b = aspec.get_rgb_values()
    if fg_r is None:
        fg_r, fg_g, fg_b = _default_fg_rgb
    if bg_r is None:
        bg_r, bg_g, bg_b = _default_bg_rgb
    fg = f"#{fg_r:02x}{fg_g:02x}{fg_b:02x}"
    bg = f"#{bg_r:02x}{bg_g:02x}{bg_b:02x}"
    if aspec.standout:
        fg, bg = bg, fg

    decoration = [name for name, on in (("underline", aspec.underline), ("line-through", aspec.strikethrough)) if on]

    extra = ""
    if decoration:
        extra += f";text-decoration:{' '.join(decoration)}"
    if aspec.underline:
        extra += _underline_css(aspec)
    if aspec.bold:
        extra += ";font-weight:bold"
    if aspec.italics:
        extra += ";font-style:italic"
    if aspec.blink:
        extra += ";animation:urwid-blink 1s step-start infinite"
    if aspec.faint:
        extra += ";opacity:0.5"
    return fg, bg, extra


def _underline_css(aspec: AttrSpec) -> str:
    """Return the CSS declarations of the style and the color of the underline of *aspec*, each after a ``;``."""
    extra = ""
    if (style := _CSS_UNDERLINE_STYLES.get(aspec.underline_style)) is not None:
        extra += f";text-decoration-style:{style}"
    if (line := aspec.underline_rgb_values()) is not None:
        extra += f";text-decoration-color:#{line[0]:02x}{line[1]:02x}{line[2]:02x}"
    return extra

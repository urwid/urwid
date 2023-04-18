#!/usr/bin/python
#
# Urwid BigText fonts
#    Copyright (C) 2004-2006  Ian Ward
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


from __future__ import annotations

import typing
import warnings
from pprint import pformat

from urwid.canvas import CanvasError, TextCanvas
from urwid.escape import SAFE_ASCII_DEC_SPECIAL_RE
from urwid.util import apply_target_encoding, str_util

if typing.TYPE_CHECKING:
    from typing_extensions import Literal


def separate_glyphs(gdata: str, height: int) -> tuple[dict[str, tuple[int, list[str]]], bool]:
    """return (dictionary of glyphs, utf8 required)"""
    gl: list[str] = gdata.split("\n")[1: -1]

    if any("\t" in elem for elem in gl):
        raise ValueError(f"Incorrect glyphs data:\n{gdata!r}")

    if len(gl) != height + 1:
        raise ValueError(f"Incorrect glyphs height (expected: {height}):\n{gdata}")

    key_line: str = gl[0]

    character: str | None = None  # current character
    key_index = 0  # index into character key line
    end_col = 0  # column position at end of glyph
    start_col = 0  # column position at start of glyph
    jl: list[int] = [0] * height  # indexes into lines of gdata (gl)
    result: dict[str, tuple[int, list[str]]] = {}
    utf8_required = False
    while True:
        if character is None:
            if key_index >= len(key_line):
                break
            character = key_line[key_index]

        if key_index < len(key_line) and key_line[key_index] == character:
            end_col += str_util.get_width(ord(character))
            key_index += 1
            continue

        out: list[str] = []
        y = 0
        fill = 0

        for k, line in enumerate(gl[1:]):
            j: int = jl[k]
            y = 0
            fill = 0
            while y < end_col - start_col:
                if j >= len(line):
                    fill = end_col - start_col - y
                    break
                y += str_util.get_width(ord(line[j]))
                j += 1
            assert y + fill == end_col - start_col, repr((y, fill, end_col))

            segment = line[jl[k]:j]
            if not SAFE_ASCII_DEC_SPECIAL_RE.match(segment):
                utf8_required = True

            out.append(segment + " " * fill)
            jl[k] = j

        start_col = end_col
        result[character] = (y + fill, out)
        character = None
    return result, utf8_required


_all_fonts: list[tuple[str, type[Font]]] = []


def get_all_fonts() -> list[tuple[str, type[Font]]]:
    """
    Return a list of (font name, font class) tuples.
    """
    return _all_fonts[:]


def add_font(name: str, cls: type[Font]) -> None:
    _all_fonts.append((name, cls))


class Font:
    height: int
    data: list[str]

    def __init__(self) -> None:
        assert self.height
        assert self.data
        self.char: dict[str, tuple[int, list[str]]] = {}
        self.canvas: dict[str, TextCanvas] = {}
        self.utf8_required = False
        data: list[str] = [self._to_text(block) for block in self.data]
        for gdata in data:
            self.add_glyphs(gdata)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()\n  {self.height!r}\n  {pformat(self.data, indent=4)}"

    @staticmethod
    def _to_text(
        obj: str | bytes,
        encoding: str = 'utf-8',
        errors: Literal['strict', 'ignore', 'replace'] | str = 'strict',
    ) -> str:
        if isinstance(obj, str):
            return obj
        elif isinstance(obj, bytes):
            warnings.warn(
                "Bytes based fonts are deprecated, please switch to the text one",
                DeprecationWarning,
                stacklevel=3,
            )
            return obj.decode(encoding, errors)
        raise TypeError(f"{obj!r} is not str|bytes")

    def add_glyphs(self, gdata: str) -> None:
        d, utf8_required = separate_glyphs(gdata, self.height)
        self.char.update(d)
        self.utf8_required |= utf8_required

    def characters(self) -> str:
        return "".join(sorted(self.char))

    def char_width(self, character: str) -> int:
        if character in self.char:
            return self.char[character][0]
        return 0

    def char_data(self, character: str) -> list[str]:
        return self.char[character][1]

    def render(self, character: str) -> TextCanvas:
        if character in self.canvas:
            return self.canvas[character]
        width, line = self.char[character]
        byte_lines = []
        character_set_lines = []
        for d in line:
            t, cs = apply_target_encoding(d)
            byte_lines.append(t)
            character_set_lines.append(cs)

        try:
            canv = TextCanvas(byte_lines, None, character_set_lines, maxcol=width, check_width=False)
        except CanvasError as exc:
            raise CanvasError(
                f"Failed render of {character!r} from line {line!r}:\n{self!r}\n:{exc}"
            ).with_traceback(exc.__traceback__) from exc

        self.canvas[character] = canv
        return canv


#safe_palette = u"┘┐┌└┼─├┤┴┬│"
#more_palette = u"═║╒╓╔╕╖╗╘╙╚╛╜╝╞╟╠╡╢╣╤╥╦╧╨╩╪╫╬○"
#block_palette = u"▄#█#▀#▌#▐#▖#▗#▘#▙#▚#▛#▜#▝#▞#▟"


class Thin3x3Font(Font):
    height = 3
    data = ["""
000111222333444555666777888999  !
┌─┐ ┐ ┌─┐┌─┐  ┐┌─ ┌─ ┌─┐┌─┐┌─┐  │
│ │ │ ┌─┘ ─┤└─┼└─┐├─┐  ┼├─┤└─┤  │
└─┘ ┴ └─ └─┘  ┴ ─┘└─┘  ┴└─┘ ─┘  .
""", r"""
"###$$$%%%'*++,--.///:;==???[[\\\]]^__`
" ┼┼┌┼┐O /'         /.. _┌─┐┌ \   ┐^  `
  ┼┼└┼┐ /  * ┼  ─  / ., _ ┌┘│  \  │
    └┼┘/ O    ,  ./       . └   \ ┘ ──
"""]


add_font("Thin 3x3",Thin3x3Font)


class Thin4x3Font(Font):
    height = 3
    data = Thin3x3Font.data + ["""
0000111122223333444455556666777788889999  ####$$$$
┌──┐  ┐ ┌──┐┌──┐   ┐┌── ┌── ┌──┐┌──┐┌──┐   ┼─┼┌┼┼┐
│  │  │ ┌──┘  ─┤└──┼└──┐├──┐   ┼├──┤└──┤   ┼─┼└┼┼┐
└──┘  ┴ └── └──┘   ┴ ──┘└──┘   ┴└──┘ ──┘      └┼┼┘
"""]


add_font("Thin 4x3",Thin4x3Font)


class Sextant3x3Font(Font):
    height = 3
    data = [u"""
   !!!###$$$%%%&&&'''((()))***+++,,,---...///
    ▐ 🬞🬲🬲🬞🬍🬋🬉🬄🬖🬦🬧  🬉 🬞🬅 🬁🬢 🬞🬦🬞 🬦            🬖
    🬉 🬇🬛🬛🬞🬰🬗🬞🬅🬭🬦🬈🬖   🬉🬏  🬘 🬇🬨🬈🬁🬨🬂 🬭 🬁🬂🬂 🬭 🬞🬅
    🬁  🬀🬀 🬁   🬂 🬂🬁    🬁 🬁         🬅     🬂
""", u"""
000111222333444555666777888999
🬦🬂🬧🬞🬫 🬇🬂🬧🬁🬂🬧 🬞🬫▐🬂🬂🬞🬅🬀🬁🬂🬙🬦🬂🬧🬦🬂🬧
▐🬁▐ ▐ 🬞🬅🬀 🬂🬧🬇🬌🬫🬁🬂🬧▐🬂🬧 🬔 🬦🬂🬧 🬂🬙
 🬂🬀 🬁 🬁🬂🬂🬁🬂🬀  🬁🬁🬂🬀 🬂🬀 🬀  🬂🬀 🬂
""", u"""
\"\"\"
 🬄🬄


""", u"""
:::;;;<<<===>>>???@@@
 🬭  🬭  🬖🬀   🬁🬢 🬇🬂🬧🬦🬂🬧
 🬰  🬰 🬁🬢 🬠🬰🬰 🬖🬀 🬇🬀▐🬉🬅
 🬂  🬅   🬀   🬁   🬁  🬂🬀
""", u"""
AAABBBCCCDDDEEEFFFGGGHHHIIIJJJKKKLLLMMMNNNOOOPPPQQQ
🬞🬅🬢▐🬂🬧🬦🬂🬈▐🬂🬧▐🬂🬂▐🬂🬂🬦🬂🬈▐ ▐ 🬨🬀  ▐▐🬞🬅▐  ▐🬢🬫▐🬢▐🬦🬂🬧▐🬂🬧🬦🬂🬧
▐🬋🬫▐🬂🬧▐ 🬞▐ ▐▐🬂 ▐🬂 ▐ 🬨▐🬂🬨 ▐ 🬞 ▐▐🬈🬏▐  ▐🬁▐▐ 🬨▐ ▐▐🬂🬀▐🬇🬘
🬁 🬁🬁🬂🬀 🬂🬀🬁🬂🬀🬁🬂🬂🬁   🬂🬂🬁 🬁 🬂🬀 🬂🬀🬁 🬁🬁🬂🬂🬁 🬁🬁 🬁 🬂🬀🬁   🬂🬁
""", u"""
RRRSSSTTTUUUVVVWWWXXXYYYZZZ[[[]]]^^^___```
▐🬂🬧🬦🬂🬈🬁🬨🬂▐ ▐▐ ▐▐ ▐🬉🬏🬘▐ ▐🬁🬂🬙 🬕🬀 🬂▌🬞🬅🬢    🬈🬏
▐🬊🬐🬞🬂🬧 ▐ ▐ ▐🬉🬏🬘▐🬖🬷🬞🬅🬢 🬧🬀🬞🬅  ▌   ▌
🬁 🬁 🬂🬀 🬁  🬂🬀 🬁 🬁 🬁🬁 🬁 🬁 🬁🬂🬂 🬂🬀 🬂🬀   🬂🬂🬂
""", u"""
\\\\\\
🬇🬏
 🬁🬢

"""]


add_font("Sextant 3x3", Sextant3x3Font)


class Sextant2x2Font(Font):
    height = 2
    data = [u"""
..,,%%00112233445566778899
    🬁🬖▐🬨🬇▌🬁🬗🬠🬸🬦▐▐🬒▐🬭🬁🬙▐🬸▐🬸
🬇 🬇🬀🬁🬇🬉🬍 🬄🬉🬋🬇🬍🬁🬊🬇🬅🬉🬍 🬄🬉🬍 🬉
"""]
add_font("Sextant 2x2", Sextant2x2Font)


class HalfBlock5x4Font(Font):
    height = 4
    data = ["""
00000111112222233333444445555566666777778888899999  !!
▄▀▀▄  ▄█  ▄▀▀▄ ▄▀▀▄ ▄  █ █▀▀▀ ▄▀▀  ▀▀▀█ ▄▀▀▄ ▄▀▀▄   █
█  █   █    ▄▀   ▄▀ █▄▄█ █▄▄  █▄▄    ▐▌ ▀▄▄▀ ▀▄▄█   █
█  █   █  ▄▀   ▄  █    █    █ █  █   █  █  █    █   ▀
 ▀▀   ▀▀▀ ▀▀▀▀  ▀▀     ▀ ▀▀▀   ▀▀    ▀   ▀▀   ▀▀    ▀
""", '''
"""######$$$$$$%%%%%&&&&&((()))******++++++,,,-----..////::;;;
█▐▌ █ █  ▄▀█▀▄ ▐▌▐▌ ▄▀▄   █ █   ▄ ▄    ▄              ▐▌
   ▀█▀█▀ ▀▄█▄    █  ▀▄▀  ▐▌ ▐▌ ▄▄█▄▄ ▄▄█▄▄    ▄▄▄▄    █  ▀  ▀
   ▀█▀█▀ ▄ █ █  ▐▌▄ █ ▀▄▌▐▌ ▐▌  ▄▀▄    █             ▐▌  ▀ ▄▀
    ▀ ▀   ▀▀▀   ▀ ▀  ▀▀   ▀ ▀              ▄▀      ▀ ▀
''', r"""
<<<<<=====>>>>>?????@@@@@@[[[[\\\\]]]]^^^^____```{{{{||}}}}~~~~''´´´
  ▄▀      ▀▄   ▄▀▀▄ ▄▀▀▀▄ █▀▀ ▐▌  ▀▀█ ▄▀▄     ▀▄  ▄▀ █ ▀▄   ▄  █ ▄▀
▄▀   ▀▀▀▀   ▀▄   ▄▀ █ █▀█ █    █    █            ▄▀  █  ▀▄ ▐▐▌▌
 ▀▄  ▀▀▀▀  ▄▀    ▀  █ ▀▀▀ █    ▐▌   █             █  █  █    ▀
   ▀      ▀      ▀   ▀▀▀  ▀▀▀   ▀ ▀▀▀     ▀▀▀▀     ▀ ▀ ▀
""", '''
AAAAABBBBBCCCCCDDDDDEEEEEFFFFFGGGGGHHHHHIIJJJJJKKKKK
▄▀▀▄ █▀▀▄ ▄▀▀▄ █▀▀▄ █▀▀▀ █▀▀▀ ▄▀▀▄ █  █ █    █ █  █
█▄▄█ █▄▄▀ █    █  █ █▄▄  █▄▄  █    █▄▄█ █    █ █▄▀
█  █ █  █ █  ▄ █  █ █    █    █ ▀█ █  █ █ ▄  █ █ ▀▄
▀  ▀ ▀▀▀   ▀▀  ▀▀▀  ▀▀▀▀ ▀     ▀▀  ▀  ▀ ▀  ▀▀  ▀  ▀
''', '''
LLLLLMMMMMMNNNNNOOOOOPPPPPQQQQQRRRRRSSSSSTTTTT
█    █▄ ▄█ ██ █ ▄▀▀▄ █▀▀▄ ▄▀▀▄ █▀▀▄ ▄▀▀▄ ▀▀█▀▀
█    █ ▀ █ █▐▌█ █  █ █▄▄▀ █  █ █▄▄▀ ▀▄▄    █
█    █   █ █ ██ █  █ █    █ ▌█ █  █ ▄  █   █
▀▀▀▀ ▀   ▀ ▀  ▀  ▀▀  ▀     ▀▀▌ ▀  ▀  ▀▀    ▀
''', '''
UUUUUVVVVVVWWWWWWXXXXXXYYYYYYZZZZZ
█  █ █   █ █   █ █   █ █   █ ▀▀▀█
█  █ ▐▌ ▐▌ █ ▄ █  ▀▄▀   ▀▄▀   ▄▀
█  █  █ █  ▐▌█▐▌ ▄▀ ▀▄   █   █
 ▀▀    ▀    ▀ ▀  ▀   ▀   ▀   ▀▀▀▀
''', '''
aaaaabbbbbcccccdddddeeeeeffffggggghhhhhiijjjjkkkkk
     █            █       ▄▀▀     █    ▄   ▄ █
 ▀▀▄ █▀▀▄ ▄▀▀▄ ▄▀▀█ ▄▀▀▄ ▀█▀ ▄▀▀▄ █▀▀▄ ▄   ▄ █ ▄▀
▄▀▀█ █  █ █  ▄ █  █ █▀▀   █  ▀▄▄█ █  █ █   █ █▀▄
 ▀▀▀ ▀▀▀   ▀▀   ▀▀▀  ▀▀   ▀   ▄▄▀ ▀  ▀ ▀ ▄▄▀ ▀  ▀
''', '''
llmmmmmmnnnnnooooopppppqqqqqrrrrssssstttt
█                                     █
█ █▀▄▀▄ █▀▀▄ ▄▀▀▄ █▀▀▄ ▄▀▀█ █▀▀ ▄▀▀▀ ▀█▀
█ █ █ █ █  █ █  █ █  █ █  █ █    ▀▀▄  █
▀ ▀   ▀ ▀  ▀  ▀▀  █▀▀   ▀▀█ ▀   ▀▀▀    ▀
''', '''
uuuuuvvvvvwwwwwwxxxxxxyyyyyzzzzz

█  █ █  █ █ ▄ █ ▀▄ ▄▀ █  █ ▀▀█▀
█  █ ▐▌▐▌ ▐▌█▐▌  ▄▀▄  ▀▄▄█ ▄▀
 ▀▀   ▀▀   ▀ ▀  ▀   ▀  ▄▄▀ ▀▀▀▀
''']


add_font("Half Block 5x4",HalfBlock5x4Font)


class HalfBlock6x5Font(Font):
    height = 5
    data = ["""
000000111111222222333333444444555555666666777777888888999999  ..::////
▄▀▀▀▄  ▄█   ▄▀▀▀▄ ▄▀▀▀▄ ▄  █  █▀▀▀▀ ▄▀▀▀  ▀▀▀▀█ ▄▀▀▀▄ ▄▀▀▀▄         █
█   █   █       █     █ █  █  █     █        ▐▌ █   █ █   █     ▀  ▐▌
█   █   █     ▄▀    ▀▀▄ ▀▀▀█▀ ▀▀▀▀▄ █▀▀▀▄    █  ▄▀▀▀▄  ▀▀▀█     ▄  █
█   █   █   ▄▀    ▄   █    █      █ █   █   ▐▌  █   █     █       ▐▌
 ▀▀▀   ▀▀▀  ▀▀▀▀▀  ▀▀▀     ▀  ▀▀▀▀   ▀▀▀    ▀    ▀▀▀   ▀▀▀    ▀   ▀
"""]


add_font("Half Block 6x5",HalfBlock6x5Font)


class HalfBlockHeavy6x5Font(Font):
    height = 5
    data = ["""
000000111111222222333333444444555555666666777777888888999999  ..::////
▄███▄  ▐█▌  ▄███▄ ▄███▄    █▌ █████ ▄███▄ █████ ▄███▄ ▄███▄         █▌
█▌ ▐█  ▀█▌  ▀  ▐█ ▀  ▐█ █▌ █▌ █▌    █▌       █▌ █▌ ▐█ █▌ ▐█     █▌ ▐█
█▌ ▐█   █▌    ▄█▀   ██▌ █████ ████▄ ████▄   ▐█  ▐███▌ ▀████        █▌
█▌ ▐█   █▌  ▄█▀   ▄  ▐█    █▌    ▐█ █▌ ▐█   █▌  █▌ ▐█    ▐█     █▌▐█
▀███▀  ███▌ █████ ▀███▀    █▌ ████▀ ▀███▀  ▐█   ▀███▀ ▀███▀   █▌  █▌
"""]


add_font("Half Block Heavy 6x5",HalfBlockHeavy6x5Font)


class Thin6x6Font(Font):
    height = 6
    data = ["""
000000111111222222333333444444555555666666777777888888999999''
┌───┐   ┐   ┌───┐ ┌───┐    ┐  ┌───  ┌───  ┌───┐ ┌───┐ ┌───┐ │
│   │   │       │     │ ┌  │  │     │         │ │   │ │   │
│ / │   │   ┌───┘    ─┤ └──┼─ └───┐ ├───┐     ┼ ├───┤ └───┤
│   │   │   │         │    │      │ │   │     │ │   │     │
└───┘   ┴   └───  └───┘    ┴   ───┘ └───┘     ┴ └───┘  ───┘

""", r'''
!!   """######$$$$$$%%%%%%&&&&&&((()))******++++++
│    ││  ┌ ┌  ┌─┼─┐ ┌┐  /  ┌─┐   / \
│       ─┼─┼─ │ │   └┘ /   │ │  │   │  \ /    │
│        │ │  └─┼─┐   /   ┌─\┘  │   │ ──X── ──┼──
│       ─┼─┼─   │ │  / ┌┐ │  \, │   │  / \    │
.        ┘ ┘  └─┼─┘ /  └┘ └───\  \ /

''', r"""
,,-----..//////::;;<<<<=====>>>>??????@@@@@@
             /                  ┌───┐ ┌───┐
            /  . .   / ──── \       │ │┌──┤
  ────     /        /        \    ┌─┘ ││  │
          /    . ,  \  ────  /    │   │└──┘
,      . /           \      /     .   └───┘

""", r"""
[[\\\\\\]]^^^____``{{||}}~~~~~~
┌ \     ┐ /\     \ ┌ │ ┐
│  \    │          │ │ │ ┌─┐
│   \   │          ┤ │ ├   └─┘
│    \  │          │ │ │
└     \ ┘    ────  └ │ ┘

""", """
AAAAAABBBBBBCCCCCCDDDDDDEEEEEEFFFFFFGGGGGGHHHHHHIIJJJJJJ
┌───┐ ┬───┐ ┌───┐ ┬───┐ ┬───┐ ┬───┐ ┌───┐ ┬   ┬ ┬     ┬
│   │ │   │ │     │   │ │     │     │     │   │ │     │
├───┤ ├───┤ │     │   │ ├──   ├──   │ ──┬ ├───┤ │     │
│   │ │   │ │     │   │ │     │     │   │ │   │ │ ┬   │
┴   ┴ ┴───┘ └───┘ ┴───┘ ┴───┘ ┴     └───┘ ┴   ┴ ┴ └───┘

""", """
KKKKKKLLLLLLMMMMMMNNNNNNOOOOOOPPPPPPQQQQQQRRRRRRSSSSSS
┬   ┬ ┬     ┌─┬─┐ ┬─┐ ┬ ┌───┐ ┬───┐ ┌───┐ ┬───┐ ┌───┐
│ ┌─┘ │     │ │ │ │ │ │ │   │ │   │ │   │ │   │ │
├─┴┐  │     │ │ │ │ │ │ │   │ ├───┘ │   │ ├─┬─┘ └───┐
│  └┐ │     │   │ │ │ │ │   │ │     │  ┐│ │ └─┐     │
┴   ┴ ┴───┘ ┴   ┴ ┴ └─┴ └───┘ ┴     └──┼┘ ┴   ┴ └───┘
                                       └
""", """
TTTTTTUUUUUUVVVVVVWWWWWWXXXXXXYYYYYYZZZZZZ
┌─┬─┐ ┬   ┬ ┬   ┬ ┬   ┬ ┬   ┬ ┬   ┬ ┌───┐
  │   │   │ │   │ │   │ └┐ ┌┘ │   │   ┌─┘
  │   │   │ │   │ │ │ │  ├─┤  └─┬─┘  ┌┘
  │   │   │ └┐ ┌┘ │ │ │ ┌┘ └┐   │   ┌┘
  ┴   └───┘  └─┘  └─┴─┘ ┴   ┴   ┴   └───┘

""", """
aaaaaabbbbbbccccccddddddeeeeeefffgggggghhhhhhiijjj
                              ┌─┐
      │               │       │        │     .  .
┌───┐ ├───┐ ┌───┐ ┌───┤ ┌───┐ ┼  ┌───┐ ├───┐ ┐  ┐
┌───┤ │   │ │     │   │ ├───┘ │  │   │ │   │ │  │
└───┴ └───┘ └───┘ └───┘ └───┘ ┴  └───┤ ┴   ┴ ┴  │
                                 └───┘         ─┘
""", """
kkkkkkllmmmmmmnnnnnnooooooppppppqqqqqqrrrrrssssss

│     │
│ ┌─  │ ┬─┬─┐ ┬───┐ ┌───┐ ┌───┐ ┌───┐ ┬──┐ ┌───┐
├─┴┐  │ │ │ │ │   │ │   │ │   │ │   │ │    └───┐
┴  └─ └ ┴   ┴ ┴   ┴ └───┘ ├───┘ └───┤ ┴    └───┘
                          │         │
""", """
ttttuuuuuuvvvvvvwwwwwwxxxxxxyyyyyyzzzzzz

 │
─┼─ ┬   ┬ ┬   ┬ ┬   ┬ ─┐ ┌─ ┬   ┬ ────┬
 │  │   │ └┐ ┌┘ │ │ │  ├─┤  │   │ ┌───┘
 └─ └───┴  └─┘  └─┴─┘ ─┘ └─ └───┤ ┴────
                            └───┘
"""]


add_font("Thin 6x6", Thin6x6Font)


class HalfBlock7x7Font(Font):
    height = 7
    data = ["""
0000000111111122222223333333444444455555556666666777777788888889999999'''
 ▄███▄   ▐█▌   ▄███▄  ▄███▄     █▌ ▐█████▌ ▄███▄ ▐█████▌ ▄███▄  ▄███▄ ▐█
▐█   █▌  ▀█▌  ▐█   █▌▐█   █▌▐█  █▌ ▐█     ▐█         ▐█ ▐█   █▌▐█   █▌▐█
▐█ ▐ █▌   █▌       █▌   ▐██ ▐█████▌▐████▄ ▐████▄     █▌  █████  ▀████▌
▐█ ▌ █▌   █▌     ▄█▀      █▌    █▌      █▌▐█   █▌   ▐█  ▐█   █▌     █▌
▐█   █▌   █▌   ▄█▀   ▐█   █▌    █▌      █▌▐█   █▌   █▌  ▐█   █▌     █▌
 ▀███▀   ███▌ ▐█████▌ ▀███▀     █▌ ▐████▀  ▀███▀   ▐█    ▀███▀  ▀███▀

""", '''
!!!   """""#######$$$$$$$%%%%%%%&&&&&&&(((())))*******++++++
▐█    ▐█ █▌ ▐█ █▌    █    ▄  █▌   ▄█▄    █▌▐█   ▄▄ ▄▄
▐█    ▐█ █▌▐█████▌ ▄███▄ ▐█▌▐█   ▐█ █▌  ▐█  █▌  ▀█▄█▀   ▐█
▐█          ▐█ █▌ ▐█▄█▄▄  ▀ █▌    ███   █▌  ▐█ ▐█████▌ ████▌
▐█         ▐█████▌ ▀▀█▀█▌  ▐█ ▄  ███▌▄  █▌  ▐█  ▄█▀█▄   ▐█
            ▐█ █▌  ▀███▀   █▌▐█▌▐█  █▌  ▐█  █▌  ▀▀ ▀▀
▐█                   █    ▐█  ▀  ▀██▀█▌  █▌▐█

''', """
,,,------.../////:::;;;<<<<<<<======>>>>>>>???????@@@@@@@
               █▌          ▄█▌      ▐█▄     ▄███▄  ▄███▄
              ▐█ ▐█ ▐█   ▄█▀  ▐████▌  ▀█▄  ▐█   █▌▐█ ▄▄█▌
   ▐████▌     █▌       ▐██              ██▌    █▌ ▐█▐█▀█▌
             ▐█  ▐█ ▐█   ▀█▄  ▐████▌  ▄█▀     █▌  ▐█▐█▄█▌
             █▌     ▀      ▀█▌      ▐█▀           ▐█ ▀▀▀
▐█       ▐█ ▐█                                █▌   ▀███▀
▀
""", r"""
[[[[\\\\\]]]]^^^^^^^_____```{{{{{|||}}}}}~~~~~~~´´´
▐██▌▐█   ▐██▌  ▐█▌       ▐█    █▌▐█ ▐█           █▌
▐█   █▌    █▌ ▐█ █▌       █▌  █▌ ▐█  ▐█   ▄▄    ▐█
▐█   ▐█    █▌▐█   █▌         ▄█▌ ▐█  ▐█▄ ▐▀▀█▄▄▌
▐█    █▌   █▌                ▀█▌ ▐█  ▐█▀     ▀▀
▐█    ▐█   █▌                 █▌ ▐█  ▐█
▐██▌   █▌▐██▌       █████      █▌▐█ ▐█

""", """
AAAAAAABBBBBBBCCCCCCCDDDDDDDEEEEEEEFFFFFFFGGGGGGGHHHHHHHIIIIJJJJJJJ
 ▄███▄ ▐████▄  ▄███▄ ▐████▄ ▐█████▌▐█████▌ ▄███▄ ▐█   █▌ ██▌     █▌
▐█   █▌▐█   █▌▐█     ▐█   █▌▐█     ▐█     ▐█     ▐█   █▌ ▐█      █▌
▐█████▌▐█████ ▐█     ▐█   █▌▐████  ▐████  ▐█     ▐█████▌ ▐█      █▌
▐█   █▌▐█   █▌▐█     ▐█   █▌▐█     ▐█     ▐█  ██▌▐█   █▌ ▐█      █▌
▐█   █▌▐█   █▌▐█     ▐█   █▌▐█     ▐█     ▐█   █▌▐█   █▌ ▐█ ▐█   █▌
▐█   █▌▐████▀  ▀███▀ ▐████▀ ▐█████▌▐█      ▀███▀ ▐█   █▌ ██▌ ▀███▀

""", """
KKKKKKKLLLLLLLMMMMMMMMNNNNNNNOOOOOOOPPPPPPPQQQQQQQRRRRRRRSSSSSSS
▐█   █▌▐█      ▄█▌▐█▄ ▐██  █▌ ▄███▄ ▐████▄  ▄███▄ ▐████▄  ▄███▄
▐█  █▌ ▐█     ▐█ ▐▌ █▌▐██▌ █▌▐█   █▌▐█   █▌▐█   █▌▐█   █▌▐█
▐█▄█▌  ▐█     ▐█ ▐▌ █▌▐█▐█ █▌▐█   █▌▐████▀ ▐█   █▌▐█████  ▀███▄
▐█▀█▌  ▐█     ▐█    █▌▐█ █▌█▌▐█   █▌▐█     ▐█   █▌▐█   █▌     █▌
▐█  █▌ ▐█     ▐█    █▌▐█ ▐██▌▐█   █▌▐█     ▐█ █▌█▌▐█   █▌     █▌
▐█   █▌▐█████▌▐█    █▌▐█  ██▌ ▀███▀ ▐█      ▀███▀ ▐█   █▌ ▀███▀
                                               ▀▀
""", """
TTTTTTTUUUUUUUVVVVVVVWWWWWWWWXXXXXXXYYYYYYYZZZZZZZ
 █████▌▐█   █▌▐█   █▌▐█    █▌▐█   █▌ █▌  █▌▐█████▌
   █▌  ▐█   █▌ █▌ ▐█ ▐█    █▌ ▐█ █▌  ▐█ ▐█     █▌
   █▌  ▐█   █▌ ▐█ █▌ ▐█    █▌  ▐█▌    ▐██     █▌
   █▌  ▐█   █▌  ███  ▐█ ▐▌ █▌  ███     █▌    █▌
   █▌  ▐█   █▌  ▐█▌  ▐█ ▐▌ █▌ █▌ ▐█    █▌   █▌
   █▌   ▀███▀    █    ▀█▌▐█▀ ▐█   █▌   █▌  ▐█████▌

""", """
aaaaaaabbbbbbbcccccccdddddddeeeeeeefffffggggggghhhhhhhiiijjjj
       ▐█                 █▌         ▄█▌       ▐█      █▌  █▌
       ▐█                 █▌        ▐█         ▐█
 ▄███▄ ▐████▄  ▄███▄  ▄████▌ ▄███▄ ▐███  ▄███▄ ▐████▄ ▐█▌ ▐█▌
  ▄▄▄█▌▐█   █▌▐█     ▐█   █▌▐█▄▄▄█▌ ▐█  ▐█   █▌▐█   █▌ █▌  █▌
▐█▀▀▀█▌▐█   █▌▐█     ▐█   █▌▐█▀▀▀   ▐█  ▐█▄▄▄█▌▐█   █▌ █▌  █▌
 ▀████▌▐████▀  ▀███▀  ▀████▌ ▀███▀  ▐█    ▀▀▀█▌▐█   █▌ █▌  █▌
                                         ▀███▀           ▐██
""", """
kkkkkkkllllmmmmmmmmnnnnnnnooooooopppppppqqqqqqqrrrrrrsssssss
▐█      ██
▐█      ▐█
▐█  ▄█▌ ▐█  ▄█▌▐█▄ ▐████▄  ▄███▄ ▐████▄  ▄████▌ ▄███▌ ▄███▄
▐█▄█▀   ▐█ ▐█ ▐▌ █▌▐█   █▌▐█   █▌▐█   █▌▐█   █▌▐█    ▐█▄▄▄
▐█▀▀█▄  ▐█ ▐█ ▐▌ █▌▐█   █▌▐█   █▌▐█   █▌▐█   █▌▐█      ▀▀▀█▌
▐█   █▌ ▐█▌▐█    █▌▐█   █▌ ▀███▀ ▐████▀  ▀████▌▐█     ▀███▀
                                 ▐█          █▌
""", """
tttttuuuuuuuvvvvvvvwwwwwwwwxxxxxxxyyyyyyyzzzzzzz
  █▌
  █▌
 ███▌▐█   █▌▐█   █▌▐█    █▌▐█   █▌▐█   █▌▐█████▌
  █▌ ▐█   █▌ █▌ ▐█ ▐█    █▌ ▀█▄█▀ ▐█   █▌   ▄█▀
  █▌ ▐█   █▌  ███  ▐█ ▐▌ █▌ ▄█▀█▄ ▐█▄▄▄█▌ ▄█▀
  █▌  ▀███▀   ▐█▌   ▀█▌▐█▀ ▐█   █▌  ▀▀▀█▌▐█████▌
                                   ▀███▀
"""]


add_font("Half Block 7x7", HalfBlock7x7Font)


if __name__ == "__main__":
    all_ascii = frozenset(chr(x) for x in range(32, 127))
    print("Available Fonts:     (U) = UTF-8 required")
    print("----------------")
    for n, cls in get_all_fonts():
        f = cls()
        u = ""
        if f.utf8_required:
            u = "(U)"
        print(f"{n:<20} {u:>3} ", end=' ')
        chars = f.characters()
        font_chars = frozenset(chars)
        if font_chars == all_ascii:
            print("Full ASCII")
        elif font_chars & all_ascii == all_ascii:
            print(f"Full ASCII + {''.join(font_chars^all_ascii)!r}")
        else:
            print(f"Characters: {chars!r}")

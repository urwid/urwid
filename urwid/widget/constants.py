from __future__ import annotations

import dataclasses
import enum
import typing

if typing.TYPE_CHECKING:
    from typing_extensions import Literal


# define some names for these constants to avoid misspellings in the source
# and to document the constant strings we are using


class Sizing(str, enum.Enum):
    """Widget sizing methods."""

    FLOW = "flow"
    BOX = "box"
    FIXED = "fixed"


class Align(str, enum.Enum):
    """Text alignment modes"""

    LEFT = "left"
    RIGHT = "right"
    CENTER = "center"


class VAlign(str, enum.Enum):
    """Filler alignment"""

    TOP = "top"
    MIDDLE = "middle"
    BOTTOM = "bottom"


class WrapMode(str, enum.Enum):
    """Text wrapping modes"""

    SPACE = "space"
    ANY = "any"
    CLIP = "clip"
    ELLIPSIS = "ellipsis"


class WHSettings(str, enum.Enum):
    """Width and Height settings"""

    PACK = "pack"
    GIVEN = "given"
    RELATIVE = "relative"
    WEIGHT = "weight"
    CLIP = "clip"  # Used as "given" for widgets with fixed width (with clipping part of it)
    FLOW = "flow"  # Used as pack for flow widgets


RELATIVE_100 = (WHSettings.RELATIVE, 100)


@typing.overload
def normalize_align(
    align: Literal["left", "center", "right"] | Align,
    err: type[BaseException],
) -> tuple[Align, None]: ...


@typing.overload
def normalize_align(
    align: tuple[Literal["relative", WHSettings.RELATIVE], int],
    err: type[BaseException],
) -> tuple[Literal[WHSettings.RELATIVE], int]: ...


def normalize_align(
    align: Literal["left", "center", "right"] | Align | tuple[Literal["relative", WHSettings.RELATIVE], int],
    err: type[BaseException],
) -> tuple[Align, None] | tuple[Literal[WHSettings.RELATIVE], int]:
    """
    Split align into (align_type, align_amount).  Raise exception err
    if align doesn't match a valid alignment.
    """
    if align in {Align.LEFT, Align.CENTER, Align.RIGHT}:
        return (Align(align), None)

    if isinstance(align, tuple) and len(align) == 2 and align[0] == WHSettings.RELATIVE:
        _align_type, align_amount = align
        return (WHSettings.RELATIVE, align_amount)

    raise err(
        f"align value {align!r} is not one of 'left', 'center', 'right', ('relative', percentage 0=left 100=right)"
    )


@typing.overload
def simplify_align(
    align_type: Literal["relative", WHSettings.RELATIVE],
    align_amount: int,
) -> tuple[Literal[WHSettings.RELATIVE], int]: ...


@typing.overload
def simplify_align(
    align_type: Literal["relative", WHSettings.RELATIVE],
    align_amount: None,
) -> typing.NoReturn: ...


@typing.overload
def simplify_align(
    align_type: Literal["left", "center", "right"] | Align,
    align_amount: int | None,
) -> Align: ...


def simplify_align(
    align_type: Literal["left", "center", "right", "relative", WHSettings.RELATIVE] | Align,
    align_amount: int | None,
) -> Align | tuple[Literal[WHSettings.RELATIVE], int]:
    """
    Recombine (align_type, align_amount) into an align value.
    Inverse of normalize_align.
    """
    if align_type == WHSettings.RELATIVE:
        if not isinstance(align_amount, int):
            raise TypeError(align_amount)

        return (WHSettings.RELATIVE, align_amount)
    return Align(align_type)


@typing.overload
def normalize_valign(
    valign: Literal["top", "middle", "bottom"] | VAlign,
    err: type[BaseException],
) -> tuple[VAlign, None]: ...


@typing.overload
def normalize_valign(
    valign: tuple[Literal["relative", WHSettings.RELATIVE], int],
    err: type[BaseException],
) -> tuple[Literal[WHSettings.RELATIVE], int]: ...


def normalize_valign(
    valign: Literal["top", "middle", "bottom"] | VAlign | tuple[Literal["relative", WHSettings.RELATIVE], int],
    err: type[BaseException],
) -> tuple[VAlign, None] | tuple[Literal[WHSettings.RELATIVE], int]:
    """
    Split align into (valign_type, valign_amount).  Raise exception err
    if align doesn't match a valid alignment.
    """
    if valign in {VAlign.TOP, VAlign.MIDDLE, VAlign.BOTTOM}:
        return (VAlign(valign), None)

    if isinstance(valign, tuple) and len(valign) == 2 and valign[0] == WHSettings.RELATIVE:
        _valign_type, valign_amount = valign
        return (WHSettings.RELATIVE, valign_amount)

    raise err(
        f"valign value {valign!r} is not one of 'top', 'middle', 'bottom', ('relative', percentage 0=left 100=right)"
    )


@typing.overload
def simplify_valign(
    valign_type: Literal["top", "middle", "bottom"] | VAlign,
    valign_amount: int | None,
) -> VAlign: ...


@typing.overload
def simplify_valign(
    valign_type: Literal["relative", WHSettings.RELATIVE],
    valign_amount: int,
) -> tuple[Literal[WHSettings.RELATIVE], int]: ...


@typing.overload
def simplify_valign(
    valign_type: Literal["relative", WHSettings.RELATIVE],
    valign_amount: None,
) -> typing.NoReturn: ...


def simplify_valign(
    valign_type: Literal["top", "middle", "bottom", "relative", WHSettings.RELATIVE] | VAlign,
    valign_amount: int | None,
) -> VAlign | tuple[Literal[WHSettings.RELATIVE], int]:
    """
    Recombine (valign_type, valign_amount) into an valign value.
    Inverse of normalize_valign.
    """
    if valign_type == WHSettings.RELATIVE:
        if not isinstance(valign_amount, int):
            raise TypeError(valign_amount)
        return (WHSettings.RELATIVE, valign_amount)
    return VAlign(valign_type)


@typing.overload
def normalize_width(
    width: Literal["clip", "pack", WHSettings.CLIP, WHSettings.PACK],
    err: type[BaseException],
) -> tuple[Literal[WHSettings.CLIP, WHSettings.PACK], None]: ...


@typing.overload
def normalize_width(
    width: int,
    err: type[BaseException],
) -> tuple[Literal[WHSettings.GIVEN], int]: ...


@typing.overload
def normalize_width(
    width: tuple[Literal["relative", WHSettings.RELATIVE], int],
    err: type[BaseException],
) -> tuple[Literal[WHSettings.RELATIVE], int]: ...


@typing.overload
def normalize_width(
    width: tuple[Literal["weight", WHSettings.WEIGHT], int | float],
    err: type[BaseException],
) -> tuple[Literal[WHSettings.WEIGHT], int | float]: ...


def normalize_width(
    width: (
        Literal["clip", "pack", WHSettings.CLIP, WHSettings.PACK]
        | int
        | tuple[Literal["relative", WHSettings.RELATIVE], int]
        | tuple[Literal["weight", WHSettings.WEIGHT], int | float]
    ),
    err: type[BaseException],
) -> (
    tuple[Literal[WHSettings.CLIP, WHSettings.PACK], None]
    | tuple[Literal[WHSettings.GIVEN, WHSettings.RELATIVE], int]
    | tuple[Literal[WHSettings.WEIGHT], int | float]
):
    """
    Split width into (width_type, width_amount).  Raise exception err
    if width doesn't match a valid alignment.
    """
    if width in {WHSettings.CLIP, WHSettings.PACK}:
        return (WHSettings(width), None)

    if isinstance(width, int):
        return (WHSettings.GIVEN, width)

    if isinstance(width, tuple) and len(width) == 2 and width[0] in {WHSettings.RELATIVE, WHSettings.WEIGHT}:
        width_type, width_amount = width
        return (WHSettings(width_type), width_amount)

    raise err(
        f"width value {width!r} is not one of"
        f"fixed number of columns, 'pack', ('relative', percentage of total width), 'clip'"
    )


@typing.overload
def simplify_width(
    width_type: Literal["clip", "pack", WHSettings.CLIP, WHSettings.PACK],
    width_amount: int | None,
) -> Literal[WHSettings.CLIP, WHSettings.PACK]: ...


@typing.overload
def simplify_width(
    width_type: Literal["given", WHSettings.GIVEN],
    width_amount: int,
) -> int: ...


@typing.overload
def simplify_width(
    width_type: Literal["relative", WHSettings.RELATIVE],
    width_amount: int,
) -> tuple[Literal[WHSettings.RELATIVE], int]: ...


@typing.overload
def simplify_width(
    width_type: Literal["weight", WHSettings.WEIGHT],
    width_amount: int | float,  # noqa: PYI041  # provide explicit for IDEs
) -> tuple[Literal[WHSettings.WEIGHT], int | float]: ...


@typing.overload
def simplify_width(
    width_type: Literal["given", "relative", "weight", WHSettings.GIVEN, WHSettings.RELATIVE, WHSettings.WEIGHT],
    width_amount: None,
) -> typing.NoReturn: ...


def simplify_width(
    width_type: Literal["clip", "pack", "given", "relative", "weight"] | WHSettings,
    width_amount: int | float | None,  # noqa: PYI041  # provide explicit for IDEs
) -> (
    Literal[WHSettings.CLIP, WHSettings.PACK]
    | int
    | tuple[Literal[WHSettings.RELATIVE], int]
    | tuple[Literal[WHSettings.WEIGHT], int | float]
):
    """
    Recombine (width_type, width_amount) into an width value.
    Inverse of normalize_width.
    """
    if width_type in {WHSettings.CLIP, WHSettings.PACK}:
        return WHSettings(width_type)

    if not isinstance(width_amount, int):
        raise TypeError(width_amount)

    if width_type == WHSettings.GIVEN:
        return width_amount

    return (WHSettings(width_type), width_amount)


@typing.overload
def normalize_height(
    height: int,
    err: type[BaseException],
) -> tuple[Literal[WHSettings.GIVEN], int]: ...


@typing.overload
def normalize_height(
    height: Literal["flow", "pack", Sizing.FLOW, WHSettings.PACK],
    err: type[BaseException],
) -> tuple[Literal[Sizing.FLOW, WHSettings.PACK], None]: ...


@typing.overload
def normalize_height(
    height: tuple[Literal["relative", WHSettings.RELATIVE], int],
    err: type[BaseException],
) -> tuple[Literal[WHSettings.RELATIVE], int]: ...


@typing.overload
def normalize_height(
    height: tuple[Literal["weight", WHSettings.WEIGHT], int | float],
    err: type[BaseException],
) -> tuple[Literal[WHSettings.WEIGHT], int | float]: ...


def normalize_height(
    height: (
        int
        | Literal["flow", "pack", Sizing.FLOW, WHSettings.PACK]
        | tuple[Literal["relative", WHSettings.RELATIVE], int]
        | tuple[Literal["weight", WHSettings.WEIGHT], int | float]
    ),
    err: type[BaseException],
) -> (
    tuple[Literal[Sizing.FLOW, WHSettings.PACK], None]
    | tuple[Literal[WHSettings.RELATIVE, WHSettings.GIVEN], int]
    | tuple[Literal[WHSettings.WEIGHT], int | float]
):
    """
    Split height into (height_type, height_amount).  Raise exception err
    if height isn't valid.
    """
    if height == Sizing.FLOW:
        return (Sizing.FLOW, None)

    if height == WHSettings.PACK:
        return (WHSettings.PACK, None)

    if isinstance(height, tuple) and len(height) == 2 and height[0] in {WHSettings.RELATIVE, WHSettings.WEIGHT}:
        return (WHSettings(height[0]), height[1])

    if isinstance(height, int):
        return (WHSettings.GIVEN, height)

    raise err(
        f"height value {height!r} is not one of "
        f"fixed number of columns, 'pack', ('relative', percentage of total height)"
    )


@typing.overload
def simplify_height(
    height_type: Literal["flow", "pack", WHSettings.FLOW, WHSettings.PACK],
    height_amount: int | None,
) -> Literal[WHSettings.FLOW, WHSettings.PACK]: ...


@typing.overload
def simplify_height(
    height_type: Literal["given", WHSettings.GIVEN],
    height_amount: int,
) -> int: ...


@typing.overload
def simplify_height(
    height_type: Literal["relative", WHSettings.RELATIVE],
    height_amount: int | None,
) -> tuple[Literal[WHSettings.RELATIVE], int]: ...


@typing.overload
def simplify_height(
    height_type: Literal["weight", WHSettings.WEIGHT],
    height_amount: int | float | None,  # noqa: PYI041  # provide explicit for IDEs
) -> tuple[Literal[WHSettings.WEIGHT], int | float]: ...


@typing.overload
def simplify_height(
    height_type: Literal["relative", "given", "weight", WHSettings.RELATIVE, WHSettings.GIVEN, WHSettings.WEIGHT],
    height_amount: None,
) -> typing.NoReturn: ...


def simplify_height(
    height_type: Literal[
        "flow",
        "pack",
        "relative",
        "given",
        "weight",
        WHSettings.FLOW,
        WHSettings.PACK,
        WHSettings.RELATIVE,
        WHSettings.GIVEN,
        WHSettings.WEIGHT,
    ],
    height_amount: int | float | None,  # noqa: PYI041  # provide explicit for IDEs
) -> (
    int
    | Literal[WHSettings.FLOW, WHSettings.PACK]
    | tuple[Literal[WHSettings.RELATIVE], int]
    | tuple[Literal[WHSettings.WEIGHT], int | float]
):
    """
    Recombine (height_type, height_amount) into a height value.
    Inverse of normalize_height.
    """
    if height_type in {WHSettings.FLOW, WHSettings.PACK}:
        return WHSettings(height_type)

    if not isinstance(height_amount, int):
        raise TypeError(height_amount)

    if height_type == WHSettings.GIVEN:
        return height_amount

    return (WHSettings(height_type), height_amount)


@dataclasses.dataclass(frozen=True)
class _BoxSymbols:
    """Box symbols for drawing."""

    HORIZONTAL: str
    VERTICAL: str
    TOP_LEFT: str
    TOP_RIGHT: str
    BOTTOM_LEFT: str
    BOTTOM_RIGHT: str
    # Joints for tables making
    LEFT_T: str
    RIGHT_T: str
    TOP_T: str
    BOTTOM_T: str
    CROSS: str


@dataclasses.dataclass(frozen=True)
class _BoxSymbolsWithDashes(_BoxSymbols):
    """Box symbols for drawing.

    Extra dashes symbols.
    """

    HORIZONTAL_4_DASHES: str
    HORIZONTAL_3_DASHES: str
    HORIZONTAL_2_DASHES: str
    VERTICAL_2_DASH: str
    VERTICAL_3_DASH: str
    VERTICAL_4_DASH: str


@dataclasses.dataclass(frozen=True)
class _LightBoxSymbols(_BoxSymbolsWithDashes):
    """Box symbols for drawing.

    The Thin version includes extra symbols.
    Symbols are ordered as in Unicode except dashes.
    """

    TOP_LEFT_ROUNDED: str
    TOP_RIGHT_ROUNDED: str
    BOTTOM_LEFT_ROUNDED: str
    BOTTOM_RIGHT_ROUNDED: str


class _BoxSymbolsCollection(typing.NamedTuple):
    """Standard Unicode box symbols for basic tables drawing.

    .. note::
        Transitions are not included: depends on line types, different kinds of transitions are available.
        Please check Unicode table for transitions symbols if required.
    """

    # fmt: off

    LIGHT: _LightBoxSymbols = _LightBoxSymbols(
        "─", "│", "┌", "┐", "└", "┘", "├", "┤", "┬", "┴", "┼", "┈", "┄", "╌", "╎", "┆", "┊", "╭", "╮", "╰", "╯"
    )
    HEAVY: _BoxSymbolsWithDashes = _BoxSymbolsWithDashes(
        "━", "┃", "┏", "┓", "┗", "┛", "┣", "┫", "┳", "┻", "╋", "┉", "┅", "╍", "╏", "┇", "┋"
    )
    DOUBLE: _BoxSymbols = _BoxSymbols(
        "═", "║", "╔", "╗", "╚", "╝", "╠", "╣", "╦", "╩", "╬"
    )


BOX_SYMBOLS = _BoxSymbolsCollection()


class BAR_SYMBOLS(str, enum.Enum):
    """Standard Unicode bar symbols excluding empty space.

    Start from space (0), then 1/8 till full block (1/1).
    Typically used only 8 from this symbol collection depends on use-case:
    * empty - 7/8 and styles for BG different on both sides (like standard `ProgressBar` and `BarGraph`)
    * 1/8 - full block and single style for BG on the right side
    """

    # fmt: off

    HORISONTAL = " ▏▎▍▌▋▊▉█"
    VERTICAL =   " ▁▂▃▄▅▆▇█"


class _SHADE_SYMBOLS(typing.NamedTuple):
    """Standard shade symbols excluding empty space."""

    # fmt: off

    FULL_BLOCK: str =   "█"
    DARK_SHADE: str =   "▓"
    MEDIUM_SHADE: str = "▒"
    LITE_SHADE: str =   "░"


SHADE_SYMBOLS = _SHADE_SYMBOLS()

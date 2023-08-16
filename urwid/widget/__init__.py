from __future__ import annotations

from .divider import Divider
from .edit import Edit, EditError, IntEdit
from .solid_fill import SolidFill
from .text import Text, TextError
from .widget import (
    Align,
    BoxWidget,
    FixedWidget,
    FlowWidget,
    Sizing,
    VAlign,
    WHSettings,
    Widget,
    WidgetError,
    WidgetMeta,
    WidgetWrap,
    WidgetWrapError,
    WrapMode,
    delegate_to_widget_mixin,
    fixed_size,
    nocache_widget_render,
    nocache_widget_render_instance,
)

__all__ = (
    "Align",
    "BoxWidget",
    "Divider",
    "Edit",
    "EditError",
    "FixedWidget",
    "FlowWidget",
    "IntEdit",
    "Sizing",
    "SolidFill",
    "Text",
    "TextError",
    "VAlign",
    "WHSettings",
    "Widget",
    "WidgetError",
    "WidgetMeta",
    "WidgetWrap",
    "WidgetWrapError",
    "WrapMode",
    "delegate_to_widget_mixin",
    "fixed_size",
    "nocache_widget_render",
    "nocache_widget_render_instance",
    "FLOW",
    "BOX",
    "FIXED",
    "LEFT",
    "RIGHT",
    "CENTER",
    "TOP",
    "MIDDLE",
    "BOTTOM",
    "SPACE",
    "ANY",
    "CLIP",
    "ELLIPSIS",
    "PACK",
    "GIVEN",
    "RELATIVE",
    "RELATIVE_100",
    "WEIGHT",
)

# Backward compatibility
FLOW = Sizing.FLOW
BOX = Sizing.BOX
FIXED = Sizing.FIXED

LEFT = Align.LEFT
RIGHT = Align.RIGHT
CENTER = Align.CENTER

TOP = VAlign.TOP
MIDDLE = VAlign.MIDDLE
BOTTOM = VAlign.BOTTOM

SPACE = WrapMode.SPACE
ANY = WrapMode.ANY
CLIP = WrapMode.CLIP
ELLIPSIS = WrapMode.ELLIPSIS

PACK = WHSettings.PACK
GIVEN = WHSettings.GIVEN
RELATIVE = WHSettings.RELATIVE
RELATIVE_100 = (WHSettings.RELATIVE, 100)
WEIGHT = WHSettings.WEIGHT

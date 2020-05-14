from enum import Enum, auto

class WidgetAlignment(Enum):
    """ Widget's position/gravity """
    TOP = auto()
    LEFT = auto()
    RIGHT = auto()
    CENTER = auto()
    MIDDLE = CENTER
    BOTTOM = auto()

class WidgetSize(Enum):
    """ Widget size is measured in screen cols and rows.

        :data BOX: fixed cols and rows, by container
        :data FLOW: fixed cols by container, rows decided by widget
        :data FIXED: widget decides about both cols and rows
    """
    BOX = auto()
    FLOW = auto()
    FIXED = auto()

class WidgetsChildrenSize(Enum):
    """ Describes widget children behaviour in container

        :data PACK: child calculates its size
        :data GIVEN: child gets fixed amount of space
        :data WEIGHT: child gets space amounting to siblings ratio
        :data RELATIVE: child gets percent of cols/rows in parent
        :data FILL_PARENT: child gets all space a container has
    """
    PACK = auto()
    GIVEN = auto()
    WEIGHT = auto()
    RELATIVE = auto()
    FILL_PARENT = (RELATIVE, 100)

class TextWrapping(Enum):
    SPACE = auto()
    ANY = auto()
    CLIP = auto()
    ELLIPSIS = auto()

# TODO: update "constants.rst"

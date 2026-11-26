"""Edit: a text editing widget, and IntEdit for integers."""

from __future__ import annotations

from ._edit import Edit, EditError, IntEdit
from ._validation import _validation_messages as _validation_messages

__all__ = ("Edit", "EditError", "IntEdit")

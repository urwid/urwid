"""Type checker fixture for the Table widget and its layout.

mypy and Pyrefly check this module; nothing in it runs.
"""

from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    from typing import assert_type

    import urwid
    from urwid.widget import TableLayout

    def table(edit: urwid.Edit) -> None:
        """Accept widgets and text markup as cells, and type the rows as TableRow."""
        columns = [
            urwid.TableColumn("Name"),
            urwid.TableColumn("Size", width=6, align=urwid.RIGHT),
            urwid.TableColumn(("bold", "Note"), width=(urwid.WEIGHT, 1), wrap=urwid.ELLIPSIS),
        ]
        widget = urwid.Table(columns, [["a", "1", edit], [("attr", "b")]], max_rows=4)
        widget.body.append(["c", "2"])
        assert_type(widget.body[0], urwid.TableRow)
        assert_type(widget.focus, urwid.TableRow | None)
        assert_type(widget.body[0].data, typing.Any)
        assert_type(widget.layout.widths(20), tuple[int, ...])

    def layout() -> None:
        """Build rows without a table."""
        shared = TableLayout([urwid.TableColumn(), urwid.TableColumn(align=urwid.RIGHT)])
        assert_type(shared.row(["label", "value"], data=1), urwid.TableRow)
        urwid.Pile([shared.row(["a", "b"])])

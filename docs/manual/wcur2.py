from __future__ import annotations

import urwid


class Widget(urwid.ListBox):
    def get_pref_col(self, size: tuple[int, int]) -> int:
        return self.cursor_x

    def move_cursor_to_coords(self, size: tuple[int, int], col: int, row: int) -> bool:
        assert row == 0  # noqa: S101  # in examples we can use `assert`
        self.cursor_x = col
        return True

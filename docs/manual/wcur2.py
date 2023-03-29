from __future__ import annotations

import urwid


class Widget(urwid.ListBox):
    def get_pref_col(self, size):
        return self.cursor_x

    def move_cursor_to_coords(self, size, col, row):
        assert row == 0
        self.cursor_x = col
        return True

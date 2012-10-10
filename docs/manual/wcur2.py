    def get_pref_col(self, (maxcol,)):
        return self.cursor_x

    def move_cursor_to_coords(self, (maxcol,), col, row):
        assert row == 0
        self.cursor_x = col
        return True

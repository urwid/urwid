    def get_pref_col(self, maxsize):
        maxcol, = maxsize[:1]
        return self.cursor_x

    def move_cursor_to_coords(self, maxsize, col, row):
        maxcol, = maxsize[:1]
        assert row == 0
        self.cursor_x = col
        return True

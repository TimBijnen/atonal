class Demo:
    """Automated demo mode that changes rows, modes and variants."""

    def __init__(self, app):
        self.app = app

    def next(self):
        q, r = self.app.seq, self.app.rounds
        if q.mode == 'matrix':
            if r % 8 == 0:
                q.mode, q.hour, q.variant = 'clock', (r // 8 - 1) % 12 + 1, 0
                self.app.changed('top')
            elif r % 4 == 0:
                q.new_matrix()
                self.app.changed('top')
            else:
                q.form = ('P', 'R', 'I', 'RI')[r % 4]
                q.num = (q.num + 5) % 12
                self.app.changed('line')
        else:
            if r % 8 == 3:
                q.mode = 'matrix'
                self.app.changed('top')
            else:
                q.variant = (q.variant + 1) % q.variants()
                self.app.changed('top')
        self.app.draw_status(all_lines=False)

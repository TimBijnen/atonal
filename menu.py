# menu.py - the encoder menu, drawn in the text area under the square
#
#   click in play view  -> open menu
#   turn                -> move between items
#   click on an item    -> edit it (turn to change, click again when done)
#   click on Mode       -> full-screen picker: turn to choose, click to switch
#   click on Exit       -> back to play view (also closes after 12 s idle)

import time
import display as D
import logic
import terts
from sequencer import FORMS, toneclock_roman

NOTE = D.NAMES
MODE_NAMES = {'matrix': 'Matrix', 'clock': 'Clock', 'terts': 'Terts'}


def _items(app):
    q = app.seq
    it = [
        # (label, current value as text, change(delta), what to redraw)
        ('Mode', lambda: MODE_NAMES[q.mode], None, 'mode'),
    ]
    if q.mode == 'matrix':
        it += [
            ('Form', lambda: q.form,
             lambda d: setattr(q, 'form', FORMS[(FORMS.index(q.form) + d) % 4]), 'line'),
            ('Number', lambda: str(q.num),
             lambda d: setattr(q, 'num', (q.num + d) % 12), 'line'),
            ('New row', lambda: 'click', None, 'new'),
            ('Chords', lambda: 'strict' if logic.CHORDS is logic.STRICT else 'maj/min',
             lambda d: logic.set_strict(logic.CHORDS is not logic.STRICT), 'none'),
        ]
    elif q.mode == 'clock':
        it += [
            ('Hour', lambda: toneclock_roman(q.hour),
             lambda d: (setattr(q, 'hour', (q.hour - 1 + d) % 12 + 1), setattr(q, 'variant', 0)), 'top'),
            ('Field', lambda: '%d/%d' % (q.variant + 1, q.variants()),
             lambda d: setattr(q, 'variant', (q.variant + d) % q.variants()), 'top'),
        ]
    else:
        it += [
            ('Shared', lambda: terts.FILTERS[q.terts_filter][0],
             lambda d: setattr(q, 'terts_filter', (q.terts_filter + d) % len(terts.FILTERS)), 'filter'),
            ('Restart', lambda: 'click', None, 'new'),
        ]
    it += [
        ('Transpose', lambda: NOTE[q.transpose],
         lambda d: setattr(q, 'transpose', (q.transpose + d) % 12), 'top'),
        ('Octave', lambda: str(q.octave),
         lambda d: setattr(q, 'octave', max(0, min(4, q.octave + d))), 'none'),
        ('Clock', lambda: app.clock_src,
         lambda d: app.set_clock('int' if app.clock_src == 'ext' else 'ext'), 'none'),
        ('Tempo', lambda: '%d bpm' % app.bpm,
         lambda d: setattr(app, 'bpm', max(20, min(400, app.bpm + 4 * d))), 'none'),
        ('Gate', lambda: '%d%%' % app.gate_pct,
         lambda d: setattr(app, 'gate_pct', max(5, min(95, app.gate_pct + 5 * d))), 'none'),
        ('Labels', lambda: 'notes' if D.USE_NAMES else 'numbers',
         lambda d: _toggle_names(app), 'top'),
        ('Exit', lambda: '', None, 'exit'),
    ]
    return it


def _toggle_names(app):
    D.USE_NAMES = not D.USE_NAMES
    app.screen.matrix.flush_cache()


class Menu:
    VISIBLE = D.STATUS_LINES - 1          # first line is the title

    def __init__(self, app):
        self.app = app
        self.open = False
        self.cur = 0
        self.top = 0
        self.editing = False
        self.picking = False                # mode picker open (covers the screen)
        self.pick = 0
        self.t = 0

    def items(self):
        return _items(self.app)

    def show(self):
        self.open, self.editing = True, False
        self.t = time.ticks_ms()
        self.app.screen.clear_text()
        self.draw(full=True)

    def close(self):
        self.open = False
        self.app.screen.clear_text()
        self.app.draw_status(all_lines=True)

    def draw(self, full=False):
        sc = self.app.screen
        items = self.items()
        self.cur = min(self.cur, len(items) - 1)
        if self.cur < self.top:
            self.top = self.cur
        if self.cur >= self.top + self.VISIBLE:
            self.top = self.cur - self.VISIBLE + 1
        if full:
            sc.line(0, 'MENU', D.DIM)
        for i in range(self.VISIBLE):
            k = self.top + i
            if k >= len(items):
                sc.line(i + 1, '')
                continue
            lab, val, _, _ = items[k]
            txt = '%-9s %s' % (lab, val())
            if k == self.cur:
                bg = D.EDIT_BG if self.editing else D.SEL_BG
                fg = D.NOW_TXT if self.editing else D.TXT
                sc.line(i + 1, txt, fg, bg)
            else:
                sc.line(i + 1, txt)

    # ---- mode picker
    def _modes(self):
        return [m for m, _ in D.MODES]

    def open_picker(self):
        self.picking = True
        self.pick = self._modes().index(self.app.seq.mode)
        self.app.screen.picker.show(self.pick, self.pick)

    def close_picker(self, apply):
        """Leave the picker, switching mode if apply, and go back to play view."""
        self.picking = False
        if apply:
            self.app.seq.mode = self._modes()[self.pick]
        self.app.redraw_top()
        self.close()

    def turn(self, d):
        self.t = time.ticks_ms()
        if self.picking:
            self.pick = (self.pick + d) % len(D.MODES)
            self.app.screen.picker.select(self.pick)
            return
        items = self.items()
        if self.editing:
            lab, _, change, redraw = items[self.cur]
            change(d)
            self.app.changed(redraw)
        else:
            self.cur = (self.cur + d) % len(items)
        self.draw()

    def click(self):
        self.t = time.ticks_ms()
        if self.picking:
            self.close_picker(apply=True)
            return
        items = self.items()
        lab, _, change, redraw = items[self.cur]
        if redraw == 'exit':
            self.close()
            return
        if redraw == 'mode':
            self.open_picker()
            return
        if redraw == 'new':
            self.app.changed('new')
            self.draw()
            return
        self.editing = not self.editing
        self.draw()

    def idle(self):
        if self.open and time.ticks_diff(time.ticks_ms(), self.t) > 12000:
            if self.picking:
                self.close_picker(apply=False)
            else:
                self.close()

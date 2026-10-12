# main.py - twelve-tone sequencer, 4 voices: matrix, tone clock and
# tertsverwanten modes, menu
#
# Controls
#   turn encoder        play view: next/previous row number (matrix), hour
#                       (tone clock) or which chords may follow (terts)
#   click               open the menu
#   hold (0.7 s)        new row (matrix) / next field (tone clock) /
#                       back to the home chord (terts)
#   DIR toggle          play backwards (P<->R, I<->RI, clock reversed)
#   MODE toggle         swap rows and columns (P<->I)
#   CLK in              next step (when Clock = ext)
#   RST in              back to the first step (terts: the home chord)
#
# Clock sources (menu): ext = CLK jack, int = internal tempo.

import time
import display as D
import hw
import config
import terts
from sequencer import Sequencer
from menu import Menu


def chord_name(chord):
    root, q = chord
    return D.label(root) + ('m' if q == terts.MINOR else '')


class App:
    def __init__(self):
        self.screen = D.init()
        self.out = hw.Outputs()
        self.enc = hw.Encoder(config.PIN_ENC_A, config.PIN_ENC_B)
        self.btn = hw.Button(config.PIN_ENC_SW)
        self.clk = hw.TrigIn(config.PIN_CLK_IN)
        self.rst = hw.TrigIn(config.PIN_RST_IN)
        self.sw_dir = hw.Toggle(config.PIN_SW_DIR)
        self.sw_mode = hw.Toggle(config.PIN_SW_MODE)
        self.seq = Sequencer()
        self.menu = Menu(self)

        self.clock_src = 'int'       # start on the internal clock so it plays without a cable
        self.bpm = 120
        self.gate_pct = 50
        self.next_tick = time.ticks_ms()
        self.gate_off_at = None
        self.trig_off_at = None
        self.flips = (False, False)
        self.last_notes = None       # the 4 voices of the last step

        global app
        app = self

        self.redraw_top()
        self.draw_status(all_lines=True)

    # ---------------------------------------------------------- drawing
    def _terts_text(self):
        """Terts: (chord name, how it got there) for the middle of the view."""
        q = self.seq
        if q.chord is None:
            return '-', 'home ' + chord_name((q.home, terts.MAJOR))
        if q.prev is None:
            return chord_name(q.chord), 'home'
        return chord_name(q.chord), 'from %s, %d shared' % (chord_name(q.prev), q.shared)

    def _terts_pcs(self):
        q = self.seq
        cur = terts.triad(*q.chord) if q.chord else ()
        prev = terts.triad(*q.prev) if q.prev else ()
        return cur, prev

    def redraw_top(self):
        q, sc = self.seq, self.screen
        q.build(*self.flips)
        if self.menu.picking:
            return                    # covered by the mode picker; redrawn when it closes
        if q.mode == 'matrix':
            sc.matrix.show(q.matrix())
            sc.matrix.set_lines(q.lines())
        elif q.mode == 'clock':
            sub = 'field %d/%d' % (q.variant + 1, q.variants()) if q.full else 'no 12-tone field'
            sc.clock.show(q.groups, q.hour, sub)
        else:
            cur, prev = self._terts_pcs()
            title, sub = self._terts_text()
            sc.terts.show(cur, prev, title, sub, terts.FILTERS[q.terts_filter][0])

    def draw_status(self, all_lines=False):
        if self.menu.open:
            return
        q, sc = self.seq, self.screen
        if q.mode == 'matrix':
            sc.line(0, 'MATRIX  %s' % q.name())
        elif q.mode == 'clock':
            sc.line(0, 'CLOCK %s  %d/%d' % (q.name()[5:], q.variant + 1, q.variants()))
        elif q.chord is None or q.prev is None:
            sc.line(0, 'TERTS  %s' % chord_name((q.home, terts.MAJOR)))
        else:
            sc.line(0, 'TERTS %s > %s (%d)' % (chord_name(q.prev), chord_name(q.chord), q.shared))
        self.draw_notes()
        if all_lines:
            sc.line(2, 'Trans %s  Oct %d' % (D.NAMES[q.transpose], q.octave), D.DIM)
            if self.clock_src == 'ext':
                sc.line(3, 'Clock ext (CLK in)', D.DIM)
            else:
                sc.line(3, 'Int %d bpm' % self.bpm, D.DIM)
            sc.line(4, 'DAC ok' if self.out.dac_ok else 'No DAC (screen)', D.DIM)
            sc.line(5, 'Click=menu Hold=new', D.DIM)

    def draw_notes(self):
        """Status line 1: the note of each voice, in the voice colours."""
        if self.menu.open:
            return
        q = self.seq
        if self.last_notes is None:
            self.screen.line(1, '-')
            return
        if q.mode == 'clock':
            colours = [D.GROUP[i % 4] for i in range(4)]    # voice i = trichord i
        elif q.mode == 'matrix':
            colours = D.VOICE
        else:
            colours = (D.TXT,) * 4                          # bass, tenor, alto, soprano
        parts = [('%-3s' % D.NAMES[n % 12], colours[i]) for i, n in enumerate(self.last_notes)]
        if q.items:
            n = q.step if q.step else len(q.items)
            parts.append(('%2d/%d' % (n, len(q.items)), D.TXT))
        self.screen.parts(1, parts)

    def changed(self, what):
        """Something changed. what: 'top', 'line', 'filter', 'new' or 'none'."""
        q = self.seq
        if what == 'new':
            if q.mode == 'matrix':
                q.new_matrix()
            elif q.mode == 'clock':
                q.variant = (q.variant + 1) % q.variants()
            else:
                q.restart()
            what = 'top'
        if what == 'top':
            self.redraw_top()
        elif what == 'line' and q.mode == 'matrix' and not self.menu.picking:
            q.build(*self.flips)
            self.screen.matrix.set_lines(q.lines())
        elif what == 'filter' and q.mode == 'terts' and not self.menu.picking:
            self.screen.terts.set_filter(terts.FILTERS[q.terts_filter][0])
        else:
            q.build(*self.flips)

    def set_clock(self, src):
        self.clock_src = src
        self.next_tick = time.ticks_ms()

    # ---------------------------------------------------------- playing
    def play_step(self):
        q = self.seq
        flips = (self.sw_dir.flipped(), self.sw_mode.flipped())
        if flips != self.flips and q.step == 0:       # toggles act at the start of a row
            self.flips = flips
            self.changed('line' if q.mode == 'matrix' else 'top')
        notes, key, wrapped = q.next()
        self.last_notes = notes
        self.out.notes([q.semis(n) for n in notes])
        now = time.ticks_ms()
        self.out.set(self.out.gate, True)
        self.out.set(self.out.trig, True)
        self.out.led.value(1)
        self.trig_off_at = time.ticks_add(now, config.TRIG_MS)
        if self.clock_src != 'ext':
            period = 60000 // self.bpm
            self.gate_off_at = time.ticks_add(now, period * self.gate_pct // 100)
        else:
            self.gate_off_at = None                   # follows the clock input
        if not self.menu.picking:                 # views are hidden under the mode picker
            if q.mode == 'matrix':
                self.screen.matrix.set_now(key)
            elif q.mode == 'clock':
                self.screen.clock.set_now(key)
            else:
                cur, prev = self._terts_pcs()
                title, sub = self._terts_text()
                self.screen.terts.set_chord(cur, prev, title, sub)
        if q.mode == 'terts':
            self.draw_status()                    # the move is on line 0
        else:
            self.draw_notes()
        if wrapped:
            self.out.set(self.out.end, True)

    def outputs_off(self, now):
        if self.trig_off_at is not None and time.ticks_diff(now, self.trig_off_at) >= 0:
            self.out.set(self.out.trig, False)
            self.out.set(self.out.end, False)
            self.out.led.value(0)
            self.trig_off_at = None
        if self.clock_src == 'ext':
            if not self.clk.high():
                self.out.set(self.out.gate, False)
        elif self.gate_off_at is not None and time.ticks_diff(now, self.gate_off_at) >= 0:
            self.out.set(self.out.gate, False)
            self.gate_off_at = None

    # ---------------------------------------------------------- main loop
    def run(self):
        while True:
            now = time.ticks_ms()

            # encoder
            d = self.enc.delta()
            if d:
                if self.menu.open:
                    self.menu.turn(d)
                else:
                    q = self.seq
                    if q.mode == 'matrix':
                        q.num = (q.num + d) % 12
                        self.changed('line')
                    elif q.mode == 'clock':
                        q.hour = (q.hour - 1 + d) % 12 + 1
                        q.variant = 0
                        self.changed('top')
                    else:
                        q.terts_filter = (q.terts_filter + d) % len(terts.FILTERS)
                        self.changed('filter')
                    self.draw_status()
            b = self.btn.poll()
            if b == 'click':
                if self.menu.open:
                    self.menu.click()
                else:
                    self.menu.show()
            elif b == 'long':
                self.changed('new')
                self.draw_status()
            self.menu.idle()

            # reset input
            if self.rst.take():
                self.seq.reset()

            # clock
            if self.clock_src == 'ext':
                if self.clk.take():
                    self.play_step()
            else:
                self.clk.take()                       # ignore the jack
                if time.ticks_diff(now, self.next_tick) >= 0:
                    self.next_tick = time.ticks_add(self.next_tick, 60000 // self.bpm)
                    if time.ticks_diff(now, self.next_tick) > 0:     # fell behind
                        self.next_tick = time.ticks_add(now, 60000 // self.bpm)
                    self.play_step()

            self.outputs_off(time.ticks_ms())
            time.sleep_ms(1)


app = None

if __name__ == "__main__":
    app = App()
    app.run()

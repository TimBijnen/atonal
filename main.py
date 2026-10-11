# main.py - twelve-tone sequencer: matrix mode, tone clock mode, menu, demo
#
# Controls
#   turn encoder        play view: next/previous row number (matrix) or hour (tone clock)
#   click               open the menu
#   hold (0.7 s)        new row (matrix) / next field (tone clock)
#   DIR toggle          play backwards (P<->R, I<->RI, clock reversed)
#   MODE toggle         swap rows and columns (P<->I)
#   CLK in              next note (when Clock = ext)
#   RST in              back to the first note
#
# Clock sources (menu): ext = CLK jack, int = internal tempo, demo = internal
# tempo that also changes rows, modes and hours by itself.

import time
import display as D
import hw
import config
from sequencer import Sequencer
from menu import Menu
from demo import Demo


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
        self.demo = Demo(self)

        self.clock_src = 'demo'      # start in demo so it plays without a clock
        self.bpm = 120
        self.gate_pct = 50
        self.next_tick = time.ticks_ms()
        self.gate_off_at = None
        self.trig_off_at = None
        self.rounds = 0              # completed rows, for demo mode
        self.flips = (False, False)
        self.last_note = None

        self.redraw_top()
        self.draw_status(all_lines=True)

    # ---------------------------------------------------------- drawing
    def redraw_top(self):
        q, sc = self.seq, self.screen
        q.build(*self.flips)
        if q.mode == 'matrix':
            sc.matrix.show(q.matrix())
            kind, i = q.line()
            sc.matrix.set_line(kind, i)
        else:
            sub = 'field %d/%d' % (q.variant + 1, q.variants()) if q.full else 'no 12-tone field'
            sc.clock.show(q.groups, q.hour, sub)

    def draw_status(self, all_lines=False):
        if self.menu.open:
            return
        q, sc = self.seq, self.screen
        if q.mode == 'matrix':
            sc.line(0, 'MATRIX  %s' % q.name())
        else:
            sc.line(0, 'CLOCK %s  %d/%d' % (q.name()[5:], q.variant + 1, q.variants()))
        self.draw_note()
        if all_lines:
            sc.line(2, 'Trans %s  Oct %d' % (D.NAMES[q.transpose], q.octave), D.DIM)
            if self.clock_src == 'ext':
                sc.line(3, 'Clock ext (CLK in)', D.DIM)
            else:
                sc.line(3, '%s %d bpm' % ('DEMO' if self.clock_src == 'demo' else 'Int', self.bpm), D.DIM)
            sc.line(4, 'DAC ok' if self.out.dac_ok else 'No DAC (screen)', D.DIM)
            sc.line(5, 'Click=menu Hold=new', D.DIM)

    def draw_note(self):
        if self.menu.open:
            return
        q = self.seq
        n = q.step if q.step else len(q.items)
        if self.last_note is None:
            self.screen.line(1, 'Note -')
        else:
            self.screen.line(1, 'Note %-3s %2d/%d' % (D.NAMES[self.last_note], n, len(q.items)))

    def changed(self, what):
        """Something changed. what: 'top', 'line', 'new' or 'none'."""
        q = self.seq
        if what == 'new':
            if q.mode == 'matrix':
                q.new_matrix()
            else:
                q.variant = (q.variant + 1) % q.variants()
            what = 'top'
        if what == 'top':
            self.redraw_top()
        elif what == 'line' and q.mode == 'matrix':
            q.build(*self.flips)
            kind, i = q.line()
            self.screen.matrix.set_line(kind, i)
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
        pc, key, wrapped = q.next()
        self.last_note = pc
        self.out.note(q.semis(pc))
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
        if q.mode == 'matrix':
            self.screen.matrix.set_now(key)
        else:
            self.screen.clock.set_now(key)
        self.draw_note()
        if wrapped:
            self.out.set(self.out.end, True)
            self.rounds += 1
            if self.clock_src == 'demo':
                self.demo.next()

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
                    else:
                        q.hour = (q.hour - 1 + d) % 12 + 1
                        q.variant = 0
                        self.changed('top')
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
                self.seq.step = 0

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


App().run()

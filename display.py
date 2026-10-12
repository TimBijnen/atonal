# display.py - screen drawing for the twelve-tone module (ST7796, 320x480, SPI)
#
# Wiring:
#   SCK  -> GP18    MOSI -> GP19    CS -> GP17    DC -> GP20    RST -> GP21
#   VCC  -> +5V     LED  -> +3V3    GND -> GND    MISO / touch pins: not connected
#
# The Pico has too little RAM for a full-screen buffer (320*480*2 = 300 KB),
# so everything is drawn in small pieces: one cell, one dot, one line of text.
#
# Screen layout (portrait):
#   y   0..320   the square (matrix mode) or the clock face (tone clock mode)
#   y 332..480   status lines, or the menu while it is open
# The mode picker covers the whole screen while it is open.

from machine import Pin, SPI
import framebuf
import time
import math
import config

W, H = 320, 480


def rgb(r, g, b):
    """RGB888 -> RGB565, byte-swapped so framebuf writes it in display order."""
    c = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
    return ((c & 0xFF) << 8) | (c >> 8)


# colours (change to taste)
BG      = rgb(10, 12, 16)      # screen background
CELL    = rgb(28, 32, 40)      # normal cell
TXT     = rgb(220, 224, 230)   # normal text
LINE_BG = rgb(30, 70, 140)     # the row/column being played
NOW_BG  = rgb(255, 170, 0)     # the note playing now
NOW_TXT = rgb(0, 0, 0)
DIM     = rgb(120, 128, 140)   # labels, inactive text
SEL_BG  = rgb(30, 70, 140)     # selected menu line
EDIT_BG = rgb(255, 170, 0)     # menu value being edited
PANEL   = rgb(18, 21, 27)      # mode picker panel
BORDER  = rgb(60, 66, 78)      # mode picker panel edge
# one colour per trichord on the tone clock
GROUP = (rgb(80, 160, 255), rgb(255, 110, 110), rgb(110, 220, 130), rgb(220, 130, 255))
# one colour per voice (matrix cells, note names in the status line)
VOICE = (NOW_BG, GROUP[1], GROUP[2], GROUP[3])
HELD = GROUP[2]                # terts: a note the chord shares with the one before

NAMES = ('C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B')
USE_NAMES = True               # True: C, C#, ...  False: 0..11 (the menu can change this)

# grid geometry: 12 cells of 25 px + 1 px gaps = 311 px, centred in 320
CELL_PX = 25
GAP = 1
GRID_X = (W - (12 * CELL_PX + 11 * GAP)) // 2
GRID_Y = 6
TOP_H = GRID_Y + 12 * (CELL_PX + GAP) + 4         # height of the top area
STATUS_Y = TOP_H + 10                             # text area under it
LINE_H = 24
STATUS_LINES = (H - STATUS_Y) // LINE_H           # 6


def label(pc):
    return NAMES[pc % 12] if USE_NAMES else str(pc % 12)


# ------------------------------------------------------------------ driver
class ST7796:
    def __init__(self, spi, cs, dc, rst):
        self.spi, self.cs, self.dc, self.rst = spi, cs, dc, rst
        cs.init(Pin.OUT, value=1)
        dc.init(Pin.OUT, value=0)
        rst.init(Pin.OUT, value=1)
        self.reset()
        self.init_panel()

    def cmd(self, c, data=None):
        self.cs(0)
        self.dc(0)
        self.spi.write(bytes([c]))
        if data:
            self.dc(1)
            self.spi.write(bytes(data))
        self.cs(1)

    def reset(self):
        self.rst(0); time.sleep_ms(20)
        self.rst(1); time.sleep_ms(150)

    def init_panel(self):
        self.cmd(0x01); time.sleep_ms(150)          # software reset
        self.cmd(0x11); time.sleep_ms(150)          # sleep out
        self.cmd(0xF0, [0xC3])                      # unlock extended commands
        self.cmd(0xF0, [0x96])
        self.cmd(0x36, [0x48])                      # MADCTL: portrait, BGR
        self.cmd(0x3A, [0x55])                      # 16 bits per pixel
        self.cmd(0xB4, [0x01])                      # 1-dot inversion
        self.cmd(0xB6, [0x80, 0x02, 0x3B])
        self.cmd(0xE8, [0x40, 0x8A, 0x00, 0x00, 0x29, 0x19, 0xA5, 0x33])
        self.cmd(0xC1, [0x06])
        self.cmd(0xC2, [0xA7])
        self.cmd(0xC5, [0x18])
        self.cmd(0xE0, [0xF0, 0x09, 0x0B, 0x06, 0x04, 0x15, 0x2F,
                        0x54, 0x42, 0x3C, 0x17, 0x14, 0x18, 0x1B])
        self.cmd(0xE1, [0xE0, 0x09, 0x0B, 0x06, 0x04, 0x03, 0x2B,
                        0x43, 0x42, 0x3B, 0x16, 0x14, 0x17, 0x1B])
        self.cmd(0xF0, [0x3C])                      # lock again
        self.cmd(0xF0, [0x69])
        if config.LCD_INVERT:
            self.cmd(0x21)                          # inversion on (see config.py)
        self.cmd(0x29); time.sleep_ms(50)           # display on

    def window(self, x0, y0, x1, y1):
        self.cmd(0x2A, [x0 >> 8, x0 & 0xFF, x1 >> 8, x1 & 0xFF])
        self.cmd(0x2B, [y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF])
        self.cs(0); self.dc(0)
        self.spi.write(b'\x2c')                     # memory write
        self.dc(1)                                  # data follows, CS stays low

    def blit(self, buf, x, y, w, h):
        self.window(x, y, x + w - 1, y + h - 1)
        self.spi.write(buf)
        self.cs(1)

    def fill_rect(self, x, y, w, h, color):
        if w <= 0 or h <= 0:
            return
        line = bytearray(w * 2)
        fb = framebuf.FrameBuffer(line, w, 1, framebuf.RGB565)
        fb.fill(color)
        self.window(x, y, x + w - 1, y + h - 1)
        for _ in range(h):
            self.spi.write(line)
        self.cs(1)


def big_text(s, fg, bg, scale=2, xscale=None):
    """Render text with the built-in 8x8 font, scaled. Returns (fb, buf, w, h).
    xscale may be a fraction (1.5) to fit two characters in a narrow cell."""
    xs = xscale or scale
    w = max(1, len(s)) * 8
    src = bytearray(((w + 7) // 8) * 8)
    sfb = framebuf.FrameBuffer(src, w, 8, framebuf.MONO_HLSB)
    sfb.fill(0)
    sfb.text(s, 0, 0, 1)
    ow, oh = int(w * xs), 8 * scale
    out = bytearray(ow * oh * 2)
    ofb = framebuf.FrameBuffer(out, ow, oh, framebuf.RGB565)
    ofb.fill(bg)
    for x in range(w):
        x0 = int(x * xs)
        x1 = int((x + 1) * xs)
        for y in range(8):
            if sfb.pixel(x, y):
                ofb.fill_rect(x0, y * scale, x1 - x0, scale, fg)
    return ofb, out, ow, oh


# ------------------------------------------------------------------ screen
class Screen:
    """Owns the LCD. Holds the top views and the text area."""

    def __init__(self, lcd):
        self.lcd = lcd
        lcd.fill_rect(0, 0, W, H, BG)
        self.matrix = MatrixView(lcd)
        self.clock = ClockView(lcd)
        self.terts = TertsView(lcd)
        self.picker = ModePicker(lcd)

    def clear_top(self):
        self.lcd.fill_rect(0, 0, W, TOP_H, BG)

    def text(self, x, y, s, fg=TXT, bg=BG, scale=2):
        _, buf, w, h = big_text(s, fg, bg, scale)
        self.lcd.blit(buf, x, y, w, h)
        return w

    def line(self, n, s, fg=TXT, bg=BG):
        """Write status/menu line n (0..5), full width, old text cleared."""
        self.parts(n, ((s, fg),), bg)

    def parts(self, n, parts, bg=BG):
        """Like line(), from pieces of text in their own colours: ((s, fg), ...)."""
        y = STATUS_Y + n * LINE_H
        self.lcd.fill_rect(0, y - 4, W, LINE_H, bg)
        x, room = 8, 19
        for s, fg in parts:
            s = s[:room]
            if not s:
                break
            x += self.text(x, y, s, fg, bg)
            room -= len(s)

    def clear_text(self):
        self.lcd.fill_rect(0, TOP_H, W, H - TOP_H, BG)


# ------------------------------------------------------------------ matrix view
class MatrixView:
    """The 12x12 square: the row and column being played, and the 4 notes
    sounding now in the voice colours. Draws as little as possible."""

    STYLES = {'normal': (TXT, CELL), 'line': (TXT, LINE_BG),
              'now0': (NOW_TXT, VOICE[0]), 'now1': (NOW_TXT, VOICE[1]),
              'now2': (NOW_TXT, VOICE[2]), 'now3': (NOW_TXT, VOICE[3])}

    def __init__(self, lcd):
        self.lcd = lcd
        self.m = None
        self.cache = {}            # (label, style) -> ready-made cell buffer
        self.lines = []            # [('row' | 'col', index), ...]
        self.now = ()              # (r, c) per voice

    def _cell_buf(self, pc, style):
        lab = label(pc)
        key = (lab, style)
        if key not in self.cache:
            fg, bg = self.STYLES[style]
            buf = bytearray(CELL_PX * CELL_PX * 2)
            cfb = framebuf.FrameBuffer(buf, CELL_PX, CELL_PX, framebuf.RGB565)
            cfb.fill(bg)
            tfb, _, tw, th = big_text(lab, fg, bg, 2, 1.5 if len(lab) > 1 else 2)
            cfb.blit(tfb, (CELL_PX - tw) // 2, (CELL_PX - th) // 2 + 1)
            self.cache[key] = buf
        return self.cache[key]

    def _draw_cell(self, cell):
        r, c = cell
        x = GRID_X + c * (CELL_PX + GAP)
        y = GRID_Y + r * (CELL_PX + GAP)
        self.lcd.blit(self._cell_buf(self.m[r][c], self._style(cell)), x, y, CELL_PX, CELL_PX)

    def _style(self, cell):
        if cell in self.now:
            return 'now%d' % self.now.index(cell)       # lowest voice wins
        for kind, i in self.lines:
            if cell[0 if kind == 'row' else 1] == i:
                return 'line'
        return 'normal'

    def _line_cells(self):
        out = []
        for kind, i in self.lines:
            out += [(i, k) for k in range(12)] if kind == 'row' else [(k, i) for k in range(12)]
        return out

    def show(self, m):
        """Draw a whole matrix (about half a second)."""
        self.m, self.lines, self.now = m, [], ()
        self.lcd.fill_rect(0, 0, W, TOP_H, BG)
        for r in range(12):
            for c in range(12):
                self._draw_cell((r, c))

    def set_lines(self, lines):
        if self.lines == lines:
            return
        old = self._line_cells()
        self.lines, self.now = lines, ()
        for cell in set(old + self._line_cells()):
            self._draw_cell(cell)

    def set_now(self, cells):
        old, self.now = self.now, tuple(cells)
        for cell in set(old) | set(self.now):
            self._draw_cell(cell)

    def flush_cache(self):
        self.cache = {}


# ------------------------------------------------------------------ tone clock view
CX, CY, RAD, DOT = W // 2, TOP_H // 2, 128, 15
ROMAN = ('I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X', 'XI', 'XII')


def _pos(pc, cx=CX, cy=CY, rad=RAD):
    a = math.radians(pc * 30)               # C on top, clockwise
    return int(cx + rad * math.sin(a)), int(cy - rad * math.cos(a))


def _disc(lcd, x, y, r, color):
    for dy in range(-r, r + 1):
        dx = int(math.sqrt(r * r - dy * dy))
        lcd.fill_rect(x - dx, y + dy, 2 * dx + 1, 1, color)


def _line(lcd, p0, p1, color):
    (x0, y0), (x1, y1) = p0, p1
    n = max(abs(x1 - x0), abs(y1 - y0), 1)
    for i in range(0, n + 1, 2):            # every 2nd pixel, 3x3 blocks
        x = x0 + (x1 - x0) * i // n
        y = y0 + (y1 - y0) * i // n
        lcd.fill_rect(x - 1, y - 1, 3, 3, color)


def _note_dot(lcd, pc, col, fg):
    x, y = _pos(pc)
    _disc(lcd, x, y, DOT, col)
    lab = label(pc)
    _, buf, w, h = big_text(lab, fg, col, 2, 1.5 if len(lab) > 1 else 2)
    lcd.blit(buf, x - w // 2, y - h // 2 + 1, w, h)


def _polygon(lcd, pcs, color):
    pts = [_pos(pc) for pc in pcs]
    for i in range(len(pts)):
        _line(lcd, pts[i], pts[(i + 1) % len(pts)], color)


class ClockView:
    """A circle of 12 notes; each trichord drawn as a coloured triangle."""

    def __init__(self, lcd):
        self.lcd = lcd
        self.groups = []
        self.group_of = {}
        self.now = ()

    def _dot(self, pc):
        g = self.group_of.get(pc)
        if pc in self.now:
            col, fg = NOW_BG, NOW_TXT
        elif g is None:
            col, fg = CELL, DIM
        else:
            col, fg = GROUP[g % 4], NOW_TXT
        _note_dot(self.lcd, pc, col, fg)

    def show(self, groups, hour, sub=''):
        """groups: list of note-lists (trichords). hour: 1..12."""
        self.groups, self.now = groups, ()
        self.group_of = {}
        for gi, g in enumerate(groups):
            for pc in g:
                self.group_of[pc] = gi
        self.lcd.fill_rect(0, 0, W, TOP_H, BG)
        for gi, g in enumerate(groups):
            _polygon(self.lcd, g, GROUP[gi % 4])
        for pc in range(12):
            self._dot(pc)
        # hour in the middle
        txt = ROMAN[hour - 1]
        _, buf, w, h = big_text(txt, TXT, BG, 4)
        self.lcd.blit(buf, CX - w // 2, CY - h // 2 - 8, w, h)
        if sub:
            _, buf, w, h = big_text(sub, DIM, BG, 1)
            self.lcd.blit(buf, CX - w // 2, CY + 20, w, h)

    def set_now(self, pcs):
        """The notes sounding now, one per voice."""
        old, self.now = self.now, tuple(pcs)
        for pc in set(old) | set(self.now):
            self._dot(pc)


# ------------------------------------------------------------------ terts view
class TertsView:
    """Tertsverwanten: the chord now playing as a triangle on the circle of
    12 notes, the chord before it as a faint one. Notes the two share are
    green, new notes orange. The chord name and the move in the middle."""

    def __init__(self, lcd):
        self.lcd = lcd
        self.cur = ()               # pitch classes of the chord now
        self.prev = ()              # ... and of the chord before
        self.rects = []             # text drawn in the middle, to clear
        self.filt = ''

    def _dot(self, pc):
        if pc in self.cur:
            col, fg = (HELD if pc in self.prev else NOW_BG), NOW_TXT
        else:
            col, fg = CELL, DIM
        _note_dot(self.lcd, pc, col, fg)

    def _text(self, s, y, fg, scale):
        _, buf, w, h = big_text(s, fg, BG, scale)
        x = CX - w // 2
        self.lcd.blit(buf, x, y, w, h)
        self.rects.append((x, y, w, h))

    def _filter(self):
        _, buf, w, h = big_text('shared: %-3s' % self.filt, DIM, BG, 1)
        self.lcd.blit(buf, CX - w // 2, CY + 44, w, h)

    def _draw(self, title, sub):
        if self.prev:
            _polygon(self.lcd, self.prev, BORDER)
        if self.cur:
            _polygon(self.lcd, self.cur, NOW_BG)
        for pc in range(12):
            self._dot(pc)
        self.rects = []
        self._text(title, CY - 34, TXT, 4)
        self._text(sub, CY + 8, DIM, 1)
        self._filter()

    def show(self, cur, prev, title, sub, filt):
        """Draw the whole view. cur, prev: pitch classes; filt: groups label."""
        self.cur, self.prev, self.filt = tuple(cur), tuple(prev), filt
        self.lcd.fill_rect(0, 0, W, TOP_H, BG)
        self._draw(title, sub)

    def set_chord(self, cur, prev, title, sub):
        """Move on to the next chord: erase the old triangles and text, draw anew."""
        for pcs in (self.prev, self.cur):
            if pcs:
                _polygon(self.lcd, pcs, BG)
        for x, y, w, h in self.rects:
            self.lcd.fill_rect(x, y, w, h, BG)
        self.cur, self.prev = tuple(cur), tuple(prev)
        self._draw(title, sub)

    def set_filter(self, filt):
        self.filt = filt
        self._filter()


# ------------------------------------------------------------------ mode picker
MODES = (('matrix', 'Matrix'), ('clock', 'Tone clock'), ('terts', 'Tertsverwanten'))
PK_X, PK_Y, PK_W, PK_H = 12, 56, W - 24, 368      # panel
CARD_X, CARD_W, CARD_H, CARD_GAP = PK_X + 12, PK_W - 24, 80, 12
CARD_Y = tuple(PK_Y + 56 + i * (CARD_H + CARD_GAP) for i in range(len(MODES)))
ICON = 56                                          # icon box, px


class ModePicker:
    """Full-screen modal to choose the mode. The views under it are not
    drawn while it is open; redraw them when it closes."""

    def __init__(self, lcd):
        self.lcd = lcd
        self.sel = 0
        self.current = 0

    def _text(self, s, x, y, fg, bg, scale=2, xscale=None):
        _, buf, w, h = big_text(s, fg, bg, scale, xscale)
        self.lcd.blit(buf, x, y, w, h)

    def _centred(self, s, y, fg, bg, scale):
        self._text(s, (W - len(s) * 8 * scale) // 2, y, fg, bg, scale)

    def _icon_matrix(self, x, y):
        step = (ICON - 2) // 4                     # 4x4 cells, 2 px gaps
        for r in range(4):
            for c in range(4):
                col = NOW_BG if (r, c) == (0, 1) else DIM
                self.lcd.fill_rect(x + c * step, y + r * step, step - 2, step - 2, col)

    def _icon_clock(self, x, y):
        cx, cy = x + ICON // 2, y + ICON // 2
        for pc in range(12):
            px, py = _pos(pc, cx, cy, ICON // 2 - 5)
            _disc(self.lcd, px, py, 4, NOW_BG if pc == 0 else GROUP[(pc // 3) % 4])

    def _icon_terts(self, x, y):
        cx, cy, rad = x + ICON // 2, y + ICON // 2, ICON // 2 - 5
        chord = (0, 4, 7)
        pts = [_pos(pc, cx, cy, rad) for pc in chord]
        for i in range(3):
            _line(self.lcd, pts[i], pts[(i + 1) % 3], NOW_BG)
        for pc in range(12):
            px, py = _pos(pc, cx, cy, rad)
            _disc(self.lcd, px, py, 4 if pc in chord else 2, NOW_BG if pc in chord else DIM)

    def _card(self, i):
        x, y = CARD_X, CARD_Y[i]
        on = i == self.sel
        bg = SEL_BG if on else CELL
        if on:
            self.lcd.fill_rect(x, y, CARD_W, CARD_H, NOW_BG)        # 3 px edge
            self.lcd.fill_rect(x + 3, y + 3, CARD_W - 6, CARD_H - 6, bg)
        else:
            self.lcd.fill_rect(x, y, CARD_W, CARD_H, bg)
        ix, iy = x + 12, y + (CARD_H - ICON) // 2
        (self._icon_matrix, self._icon_clock, self._icon_terts)[i](ix, iy)
        tx, mid = ix + ICON + 12, y + CARD_H // 2
        fg = TXT if on else DIM
        if i == self.current:
            self._text(MODES[i][1], tx, mid - 14, fg, bg, 2, 1.5)
            self._text('current', tx, mid + 8, fg, bg, 1)
        else:
            self._text(MODES[i][1], tx, mid - 8, fg, bg, 2, 1.5)

    def show(self, sel, current):
        """Draw the whole modal. sel, current: index into MODES."""
        self.sel, self.current = sel, current
        lcd = self.lcd
        lcd.fill_rect(0, 0, W, H, BG)
        lcd.fill_rect(PK_X, PK_Y, PK_W, PK_H, BORDER)               # 1 px edge
        lcd.fill_rect(PK_X + 1, PK_Y + 1, PK_W - 2, PK_H - 2, PANEL)
        self._centred('MODE', PK_Y + 22, DIM, PANEL, 2)
        for i in range(len(MODES)):
            self._card(i)
        self._centred('Turn: choose   Click: OK', PK_Y + PK_H - 24, DIM, PANEL, 1)

    def select(self, sel):
        if sel == self.sel:
            return
        old, self.sel = self.sel, sel
        self._card(old)
        self._card(sel)


def init():
    spi = SPI(0, baudrate=40_000_000, polarity=0, phase=0,
              sck=Pin(18), mosi=Pin(19))
    lcd = ST7796(spi, cs=Pin(17), dc=Pin(20), rst=Pin(21))
    return Screen(lcd)

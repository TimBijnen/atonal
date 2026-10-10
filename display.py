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

from machine import Pin, SPI
import framebuf
import time
import math

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
# one colour per trichord on the tone clock
GROUP = (rgb(80, 160, 255), rgb(255, 110, 110), rgb(110, 220, 130), rgb(220, 130, 255))

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
        # self.cmd(0x21)                            # uncomment if colours are inverted
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
    """Owns the LCD. Holds the two top views and the text area."""

    def __init__(self, lcd):
        self.lcd = lcd
        lcd.fill_rect(0, 0, W, H, BG)
        self.matrix = MatrixView(lcd)
        self.clock = ClockView(lcd)

    def clear_top(self):
        self.lcd.fill_rect(0, 0, W, TOP_H, BG)

    def text(self, x, y, s, fg=TXT, bg=BG, scale=2):
        _, buf, w, h = big_text(s, fg, bg, scale)
        self.lcd.blit(buf, x, y, w, h)
        return w

    def line(self, n, s, fg=TXT, bg=BG):
        """Write status/menu line n (0..5), full width, old text cleared."""
        y = STATUS_Y + n * LINE_H
        self.lcd.fill_rect(0, y - 4, W, LINE_H, bg)
        self.text(8, y, s[:19], fg, bg)

    def clear_text(self):
        self.lcd.fill_rect(0, TOP_H, W, H - TOP_H, BG)


# ------------------------------------------------------------------ matrix view
class MatrixView:
    """The 12x12 square. Moves the highlight with as little drawing as possible."""

    STYLES = {'normal': (TXT, CELL), 'line': (TXT, LINE_BG), 'now': (NOW_TXT, NOW_BG)}

    def __init__(self, lcd):
        self.lcd = lcd
        self.m = None
        self.cache = {}            # (label, style) -> ready-made cell buffer
        self.line = None           # ('row' | 'col', index)
        self.now = None            # (r, c) of the highlighted note

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

    def _draw_cell(self, r, c, style):
        x = GRID_X + c * (CELL_PX + GAP)
        y = GRID_Y + r * (CELL_PX + GAP)
        self.lcd.blit(self._cell_buf(self.m[r][c], style), x, y, CELL_PX, CELL_PX)

    def _style(self, r, c):
        if self.now == (r, c):
            return 'now'
        if self.line:
            kind, i = self.line
            if (kind == 'row' and r == i) or (kind == 'col' and c == i):
                return 'line'
        return 'normal'

    def _line_cells(self):
        if not self.line:
            return []
        kind, i = self.line
        return [(i, k) for k in range(12)] if kind == 'row' else [(k, i) for k in range(12)]

    def show(self, m):
        """Draw a whole matrix (about half a second)."""
        self.m, self.line, self.now = m, None, None
        for r in range(12):
            for c in range(12):
                self._draw_cell(r, c, 'normal')

    def set_line(self, kind, index):
        if self.line == (kind, index):
            return
        old = self._line_cells()
        self.line, self.now = (kind, index), None
        for r, c in old + self._line_cells():
            self._draw_cell(r, c, self._style(r, c))

    def set_now(self, cell):
        old, self.now = self.now, cell
        if old:
            self._draw_cell(old[0], old[1], self._style(*old))
        if cell:
            self._draw_cell(cell[0], cell[1], 'now')

    def flush_cache(self):
        self.cache = {}


# ------------------------------------------------------------------ tone clock view
CX, CY, RAD, DOT = W // 2, TOP_H // 2, 128, 15
ROMAN = ('I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X', 'XI', 'XII')


def _pos(pc):
    a = math.radians(pc * 30)               # C on top, clockwise
    return int(CX + RAD * math.sin(a)), int(CY - RAD * math.cos(a))


class ClockView:
    """A circle of 12 notes; each trichord drawn as a coloured triangle."""

    def __init__(self, lcd):
        self.lcd = lcd
        self.groups = []
        self.group_of = {}
        self.now = None

    def _disc(self, x, y, r, color):
        for dy in range(-r, r + 1):
            dx = int(math.sqrt(r * r - dy * dy))
            self.lcd.fill_rect(x - dx, y + dy, 2 * dx + 1, 1, color)

    def _line(self, p0, p1, color):
        (x0, y0), (x1, y1) = p0, p1
        n = max(abs(x1 - x0), abs(y1 - y0))
        for i in range(0, n + 1, 2):            # every 2nd pixel, 3x3 blocks
            x = x0 + (x1 - x0) * i // n
            y = y0 + (y1 - y0) * i // n
            self.lcd.fill_rect(x - 1, y - 1, 3, 3, color)

    def _dot(self, pc, style):
        x, y = _pos(pc)
        g = self.group_of.get(pc)
        if style == 'now':
            col, fg = NOW_BG, NOW_TXT
        elif g is None:
            col, fg = CELL, DIM
        else:
            col, fg = GROUP[g % 4], NOW_TXT
        self._disc(x, y, DOT, col)
        lab = label(pc)
        _, buf, w, h = big_text(lab, fg, col, 2, 1.5 if len(lab) > 1 else 2)
        self.lcd.blit(buf, x - w // 2, y - h // 2 + 1, w, h)

    def show(self, groups, hour, sub=''):
        """groups: list of note-lists (trichords). hour: 1..12."""
        self.groups, self.now = groups, None
        self.group_of = {}
        for gi, g in enumerate(groups):
            for pc in g:
                self.group_of[pc] = gi
        self.lcd.fill_rect(0, 0, W, TOP_H, BG)
        for gi, g in enumerate(groups):
            pts = [_pos(pc) for pc in g]
            for i in range(len(pts)):
                self._line(pts[i], pts[(i + 1) % len(pts)], GROUP[gi % 4])
        for pc in range(12):
            self._dot(pc, 'normal')
        # hour in the middle
        txt = ROMAN[hour - 1]
        _, buf, w, h = big_text(txt, TXT, BG, 4)
        self.lcd.blit(buf, CX - w // 2, CY - h // 2 - 8, w, h)
        if sub:
            _, buf, w, h = big_text(sub, DIM, BG, 1)
            self.lcd.blit(buf, CX - w // 2, CY + 20, w, h)

    def set_now(self, pc):
        old, self.now = self.now, pc
        if old is not None:
            self._dot(old, 'normal')
        if pc is not None:
            self._dot(pc, 'now')


def init():
    spi = SPI(0, baudrate=40_000_000, polarity=0, phase=0,
              sck=Pin(18), mosi=Pin(19))
    lcd = ST7796(spi, cs=Pin(17), dc=Pin(20), rst=Pin(21))
    return Screen(lcd)

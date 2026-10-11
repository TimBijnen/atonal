# framebuf.py - minimal pure-Python stand-in for MicroPython's framebuf,
# just enough for display.py (RGB565 + MONO_HLSB, fill/fill_rect/text/pixel/blit).
from _font import FONT  # 8x8, ASCII 0x20..0x7F, bit (1<<col), LSB = leftmost

# format constants (values only need to be self-consistent)
MONO_VLSB = 0
MONO_HLSB = 3
MONO_HMSB = 4
RGB565 = 1
GS2_HMSB = 5
GS4_HMSB = 2
GS8 = 6


class FrameBuffer:
    def __init__(self, buf, w, h, fmt, stride=None):
        self.buf = buf
        self.w = w
        self.h = h
        self.fmt = fmt
        self.stride = stride if stride is not None else w

    # ---- pixel access ----
    def _get(self, x, y):
        if self.fmt == RGB565:
            i = (y * self.stride + x) * 2
            return self.buf[i] | (self.buf[i + 1] << 8)
        else:  # MONO_HLSB
            bpr = (self.stride + 7) // 8
            i = y * bpr + (x >> 3)
            return (self.buf[i] >> (7 - (x & 7))) & 1

    def _set(self, x, y, c):
        if x < 0 or y < 0 or x >= self.w or y >= self.h:
            return
        if self.fmt == RGB565:
            i = (y * self.stride + x) * 2
            self.buf[i] = c & 0xFF
            self.buf[i + 1] = (c >> 8) & 0xFF
        else:  # MONO_HLSB
            bpr = (self.stride + 7) // 8
            i = y * bpr + (x >> 3)
            bit = 7 - (x & 7)
            if c:
                self.buf[i] |= (1 << bit)
            else:
                self.buf[i] &= ~(1 << bit)

    def pixel(self, x, y, c=None):
        if c is None:
            return self._get(x, y)
        self._set(x, y, c)

    def fill(self, c):
        for y in range(self.h):
            for x in range(self.w):
                self._set(x, y, c)

    def fill_rect(self, x, y, w, h, c):
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self._set(xx, yy, c)

    def rect(self, x, y, w, h, c, fill=False):
        if fill:
            self.fill_rect(x, y, w, h, c)
            return
        for xx in range(x, x + w):
            self._set(xx, y, c)
            self._set(xx, y + h - 1, c)
        for yy in range(y, y + h):
            self._set(x, yy, c)
            self._set(x + w - 1, yy, c)

    def hline(self, x, y, w, c):
        for xx in range(x, x + w):
            self._set(xx, y, c)

    def vline(self, x, y, h, c):
        for yy in range(y, y + h):
            self._set(x, yy, c)

    def text(self, s, x, y, c=1):
        for ch in s:
            o = ord(ch)
            glyph = FONT[o - 0x20] if 0x20 <= o < 0x80 else FONT[0]
            for row in range(8):
                bits = glyph[row]
                for col in range(8):
                    if (bits >> col) & 1:
                        self._set(x + col, y + row, c)
            x += 8

    def blit(self, src, x, y, key=-1, palette=None):
        for sy in range(src.h):
            for sx in range(src.w):
                v = src._get(sx, sy)
                if key != -1 and v == key:
                    continue
                self._set(x + sx, y + sy, v)

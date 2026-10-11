# simdisplay.py - a fake LCD that paints the firmware's draw calls into an
# in-memory RGB framebuffer, plus a tiny dependency-free PNG writer.
#
# The firmware only ever calls lcd.fill_rect(...) and lcd.blit(...); both
# receive colours/pixels as the byte-swapped RGB565 values produced by
# display.rgb(). We undo that swap here to recover RGB888.
import threading
import struct
import zlib


def _unpack565(v):
    c = ((v & 0xFF) << 8) | (v >> 8)          # undo display.rgb()'s byte swap
    r = (c >> 8) & 0xF8
    g = (c >> 3) & 0xFC
    b = (c << 3) & 0xF8
    return r, g, b


class SimLCD:
    def __init__(self, w, h):
        self.w = w
        self.h = h
        self.buf = bytearray(w * h * 3)        # RGB888, row-major
        self.lock = threading.Lock()
        self.dirty = True

    def fill_rect(self, x, y, w, h, color):
        if w <= 0 or h <= 0:
            return
        r, g, b = _unpack565(color)
        x0 = max(0, x); y0 = max(0, y)
        x1 = min(self.w, x + w); y1 = min(self.h, y + h)
        if x1 <= x0 or y1 <= y0:
            return
        row = bytes((r, g, b)) * (x1 - x0)
        W = self.w
        with self.lock:
            buf = self.buf
            for yy in range(y0, y1):
                o = (yy * W + x0) * 3
                buf[o:o + len(row)] = row
            self.dirty = True

    def blit(self, data, x, y, w, h):
        # data: RGB565 little-endian, w*h pixels
        W = self.w
        with self.lock:
            buf = self.buf
            for yy in range(h):
                ty = y + yy
                if ty < 0 or ty >= self.h:
                    continue
                si = yy * w * 2
                base = (ty * W) * 3
                for xx in range(w):
                    tx = x + xx
                    if tx < 0 or tx >= W:
                        continue
                    v = data[si] | (data[si + 1] << 8)
                    si += 2
                    r, g, b = _unpack565(v)
                    o = base + tx * 3
                    buf[o] = r; buf[o + 1] = g; buf[o + 2] = b
            self.dirty = True

    def snapshot(self):
        with self.lock:
            return bytes(self.buf)

    def write_png(self, path):
        data = self.snapshot()
        W, H = self.w, self.h
        raw = bytearray()
        for y in range(H):
            raw.append(0)                       # filter type 0
            raw.extend(data[y * W * 3:(y + 1) * W * 3])

        def chunk(tag, payload):
            c = struct.pack(">I", len(payload)) + tag + payload
            c += struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
            return c

        hdr = struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0)  # 8-bit RGB
        png = (b"\x89PNG\r\n\x1a\n"
               + chunk(b"IHDR", hdr)
               + chunk(b"IDAT", zlib.compress(bytes(raw), 6))
               + chunk(b"IEND", b""))
        with open(path, "wb") as f:
            f.write(png)

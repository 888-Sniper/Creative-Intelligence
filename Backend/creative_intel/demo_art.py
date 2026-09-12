"""Deterministic demo artwork for the ten synthetic demo creatives.

Renders small portrait PNGs with the standard library only (zlib +
struct), so demo seeding gains real per-creative image assets without
new dependencies. Each scene is an abstract product-ad composition in
the creative's own palette — a genuine uploaded-media row that the
thumbnail endpoint prefers over the generated SVG fallback.
"""

import struct
import zlib

W, H = 320, 400


def _chunk(typ, data):
    return (struct.pack(">I", len(data)) + typ + data
            + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF))


def encode_png(w, h, rows):
    """Encode 8-bit truecolour rows (each exactly 3*w bytes) as PNG."""
    raw = b"".join(b"\x00" + bytes(r) for r in rows)
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr)
            + _chunk(b"IDAT", zlib.compress(raw, 9))
            + _chunk(b"IEND", b""))


def _lerp(a, b, t):
    return tuple(int(x + (y - x) * t) for x, y in zip(a, b))


class Canvas:
    def __init__(self, w=W, h=H):
        self.w, self.h = w, h
        self.px = [bytearray(w * 3) for _ in range(h)]

    def gradient(self, top, bottom):
        for y in range(self.h):
            c = _lerp(top, bottom, y / max(1, self.h - 1))
            row = self.px[y]
            for x in range(self.w):
                o = x * 3
                row[o], row[o + 1], row[o + 2] = c

    def rect(self, x0, y0, x1, y1, color):
        for y in range(max(0, y0), min(self.h, y1)):
            row = self.px[y]
            for x in range(max(0, x0), min(self.w, x1)):
                o = x * 3
                row[o], row[o + 1], row[o + 2] = color

    def circle(self, cx, cy, r, color):
        for y in range(max(0, cy - r), min(self.h, cy + r + 1)):
            row = self.px[y]
            for x in range(max(0, cx - r), min(self.w, cx + r + 1)):
                if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                    o = x * 3
                    row[o], row[o + 1], row[o + 2] = color

    def triangle(self, x0, y_base, x1, y_apex, color):
        # Isoceles peak at ((x0+x1)/2, y_apex), base on y_base.
        mid = (x0 + x1) / 2.0
        half = (x1 - x0) / 2.0 or 1.0
        for y in range(max(0, y_apex), min(self.h, y_base)):
            t = (y - y_apex) / max(1, y_base - y_apex)
            hw = half * t
            for x in range(max(0, int(mid - hw)), min(self.w, int(mid + hw) + 1)):
                o = x * 3
                row = self.px[y]
                row[o], row[o + 1], row[o + 2] = color

    def band(self, y0, y1, color):
        self.rect(0, y0, self.w, y1, color)

    def png(self):
        return encode_png(self.w, self.h, self.px)


def _scene(palette, paint):
    top, bottom = palette
    c = Canvas()
    c.gradient(top, bottom)
    paint(c)
    return c.png()


def _glowskin(c):
    c.circle(160, 130, 62, (255, 236, 220))
    c.circle(160, 130, 46, (255, 214, 190))
    c.band(300, 400, (122, 62, 72))
    c.rect(138, 218, 182, 320, (250, 244, 236))
    c.rect(138, 218, 182, 232, (196, 120, 132))
    c.rect(150, 198, 170, 218, (90, 50, 58))


def _reallife(c):
    c.rect(36, 90, 150, 230, (255, 244, 214))
    c.rect(36, 90, 150, 104, (122, 84, 52))
    c.rect(186, 130, 284, 300, (176, 128, 88))
    c.rect(200, 150, 270, 220, (240, 220, 190))
    c.band(300, 400, (94, 64, 44))
    c.circle(160, 330, 60, (150, 110, 74))


def _energy(c):
    c.circle(160, 150, 70, (255, 244, 200))
    c.circle(160, 150, 52, (255, 214, 130))
    c.triangle(-20, 400, 180, 210, (64, 128, 96))
    c.triangle(140, 400, 340, 250, (44, 100, 78))
    c.band(360, 400, (30, 70, 58))


def _trail(c):
    c.circle(232, 84, 34, (240, 244, 250))
    c.triangle(-40, 400, 200, 150, (52, 74, 104))
    c.triangle(120, 400, 360, 190, (36, 54, 82))
    c.triangle(70, 235, 130, 150, (235, 240, 248))
    for x in (60, 110, 250, 292):
        c.triangle(x - 22, 400, x + 22, 300, (24, 60, 52))


def _routine(c):
    for i, x in enumerate((66, 138, 210)):
        h = 150 - i * 18
        c.rect(x, 300 - h, x + 44, 300, (244, 238, 228))
        c.rect(x, 300 - h, x + 44, 300 - h + 16, (139, 168, 136))
        c.rect(x + 14, 300 - h - 18, x + 30, 300 - h, (110, 130, 120))
    c.band(300, 400, (84, 106, 100))
    c.circle(160, 120, 56, (232, 240, 228))


def _coffee(c):
    c.rect(96, 190, 224, 300, (176, 116, 72))
    c.rect(96, 190, 224, 208, (120, 70, 40))
    c.rect(224, 214, 244, 262, (150, 96, 58))
    for x in (130, 160, 190):
        c.circle(x, 165, 12, (235, 225, 210))
        c.circle(x, 140, 9, (235, 225, 210))
    c.band(300, 400, (96, 62, 40))
    c.rect(60, 318, 260, 330, (70, 44, 28))


def _move(c):
    for y in range(c.h):
        for x in range(c.w):
            if x > y * c.w // c.h:
                row = c.px[y]
                row[x * 3:x * 3 + 3] = bytes((24, 24, 28))
    c.circle(110, 140, 58, (255, 92, 92))
    c.circle(110, 140, 40, (255, 214, 200))
    c.circle(225, 260, 44, (255, 214, 200))
    c.circle(225, 260, 28, (255, 92, 92))
    c.band(356, 400, (255, 92, 92))


def _nook(c):
    c.rect(90, 190, 230, 300, (214, 188, 150))
    c.triangle(70, 196, 250, 110, (150, 60, 70))
    c.rect(145, 240, 175, 300, (60, 40, 52))
    c.rect(105, 215, 135, 245, (255, 236, 180))
    c.rect(185, 215, 215, 245, (255, 236, 180))
    for x in (60, 120, 200, 260):
        c.circle(x, 340, 10, (255, 214, 130))


def _thread(c):
    for gy in range(60, 360, 44):
        for gx in range(30, 320, 44):
            c.circle(gx, gy, 5, (255, 255, 255))
    c.circle(160, 110, 34, (250, 250, 252))
    c.rect(110, 150, 210, 320, (186, 84, 104))
    c.rect(110, 150, 210, 170, (150, 60, 80))
    c.rect(150, 96, 170, 130, (120, 90, 100))
    c.band(340, 400, (122, 44, 62))


def _wander(c):
    c.circle(104, 110, 44, (255, 240, 200))
    for i in range(5):
        y = 210 + i * 36
        c.band(y, y + 16, (36 + i * 8, 120 + i * 10, 150 + i * 8))
    c.triangle(190, 250, 280, 150, (245, 245, 248))
    c.rect(232, 250, 238, 300, (245, 245, 248))


SCENES = {
    # key: (palette_top, palette_bottom, painter)
    "demo-glowskin-01": ((252, 222, 210), (196, 130, 140), _glowskin),
    "demo-reallife-01": ((246, 232, 204), (150, 108, 72), _reallife),
    "demo-energy-01": ((255, 238, 200), (120, 180, 150), _energy),
    "demo-trail-01": ((150, 190, 225), (40, 60, 92), _trail),
    "demo-routine-01": ((228, 238, 230), (120, 150, 140), _routine),
    "demo-coffee-01": ((245, 230, 205), (140, 96, 62), _coffee),
    "demo-move-01": ((255, 200, 190), (70, 60, 70), _move),
    "demo-nook-01": ((60, 70, 110), (22, 26, 48), _nook),
    "demo-thread-01": ((250, 214, 222), (170, 90, 110), _thread),
    "demo-wander-01": ((120, 200, 220), (24, 80, 110), _wander),
}


def art_for_key(key):
    """PNG bytes for a demo creative key (ValueError for unknown keys)."""
    try:
        top, bottom, paint = SCENES[key]
    except KeyError:
        raise ValueError("no demo artwork for %r" % (key,))
    return _scene((top, bottom), paint)


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


# Presentation-pack subjects reuse the proven painters; each variant
# shifts the palette so the thirty pack thumbnails are distinct.
SUBJECT_SCENES = {
    "skincare": ((252, 222, 210), (196, 130, 140), _glowskin),
    "coffee": ((245, 230, 205), (140, 96, 62), _coffee),
    "home": ((246, 232, 204), (150, 108, 72), _reallife),
    "fitness": ((255, 200, 190), (70, 60, 70), _move),
    "headphones": ((60, 70, 110), (22, 26, 48), _nook),
}


def art_for_subject(subject, variant=0):
    """PNG bytes for a pack subject (ValueError for unknown subjects)."""
    try:
        top, bottom, paint = SUBJECT_SCENES[subject]
    except KeyError:
        raise ValueError("no sample artwork for %r" % (subject,))
    shift = (int(variant) % 3) * 14
    top = tuple(min(255, c + shift) for c in top)
    bottom = tuple(max(0, c - shift) for c in bottom)
    return _scene((top, bottom), paint)


# --- v2 presentation pack: fifteen genuinely distinct compositions ---
#
# Unlike art_for_subject (one painter per subject plus a palette
# shift), every v2 creative has its OWN painter, canvas size and
# palette, so no two thumbnails share a scene. Sizes follow the
# creative's format label: 1:1 -> 1080x1080, 4:5 -> 960x1200,
# 9:16 -> 720x1280, 16:9 -> 1280x720.

def _scene_wh(w, h, palette, paint):
    top, bottom = palette
    c = Canvas(w, h)
    c.gradient(top, bottom)
    paint(c)
    return c.png()


def _v_mirror(c):
    w, h = c.w, c.h
    c.circle(w // 2, h // 4, w // 5, (255, 236, 220))
    c.circle(w // 2, h // 4, w // 7, (255, 214, 190))
    c.rect(w // 2 - 14, h // 2, w // 2 + 14, h * 3 // 4, (250, 244, 236))
    c.rect(w // 2 - 14, h // 2, w // 2 + 14, h // 2 + 16, (196, 120, 132))
    c.band(h * 3 // 4, h, (122, 62, 72))
    for i in range(3):
        c.circle(w // 4 + i * w // 4, h * 7 // 8, 10, (255, 214, 190))


def _v_steps(c):
    w, h = c.w, c.h
    for i, x in enumerate((w // 5, w * 2 // 5, w * 3 // 5)):
        top_y = h // 3 + i * h // 12
        c.rect(x, top_y, x + w // 8, h * 2 // 3, (244, 238, 228))
        c.rect(x, top_y, x + w // 8, top_y + 18, (139, 168, 136))
    c.band(h * 2 // 3, h, (84, 106, 100))
    c.circle(w // 2, h // 6, w // 9, (255, 240, 220))


def _v_texture(c):
    w, h = c.w, c.h
    for i in range(6):
        y = h // 8 + i * h // 8
        c.band(y, y + h // 24, (255 - i * 8, 228 - i * 6, 210 - i * 4))
    c.circle(w * 3 // 4, h // 3, w // 8, (196, 120, 132))
    c.circle(w // 4, h * 2 // 3, w // 10, (122, 62, 72))


def _v_meeting(c):
    w, h = c.w, c.h
    c.rect(w // 6, h // 3, w * 5 // 6, h * 2 // 3, (60, 44, 34))
    c.rect(w // 6, h // 3, w * 5 // 6, h // 3 + 14, (120, 70, 40))
    c.circle(w // 2, h // 2, w // 10, (176, 116, 72))
    for x in (w // 3, w // 2, w * 2 // 3):
        c.circle(x, h // 4, 11, (235, 225, 210))
    c.band(h * 3 // 4, h, (96, 62, 40))


def _v_desk(c):
    w, h = c.w, c.h
    c.rect(w // 8, h // 4, w * 7 // 8, h * 3 // 4, (150, 96, 58))
    c.rect(w // 4, h // 2, w * 3 // 4, h * 3 // 4 - 20, (240, 220, 190))
    c.circle(w // 3, h // 3, w // 12, (235, 225, 210))
    c.band(h * 3 // 4, h, (70, 44, 28))
    c.rect(w // 5, h * 5 // 6, w * 4 // 5, h * 5 // 6 + 12, (120, 70, 40))


def _v_thirty(c):
    w, h = c.w, c.h
    c.circle(w // 2, h // 2, w // 4, (255, 244, 214))
    c.circle(w // 2, h // 2, w // 6, (122, 84, 52))
    for i in range(12):
        c.rect(w // 2 - 6, 20 + i * (h - 40) // 12,
               w // 2 + 6, 34 + i * (h - 40) // 12, (150, 96, 58))
    c.band(0, h // 10, (96, 62, 40))
    c.band(h * 9 // 10, h, (96, 62, 40))


def _v_drawer(c):
    w, h = c.w, c.h
    c.rect(w // 6, h // 4, w * 5 // 6, h * 3 // 4, (214, 188, 150))
    for i in range(3):
        y = h // 4 + 12 + i * h // 6
        c.rect(w // 6 + 14, y, w * 5 // 6 - 14, y + h // 8, (240, 228, 200))
        c.circle(w // 2, y + h // 16, 7, (150, 60, 70))
    c.band(h * 3 // 4, h, (94, 64, 44))


def _v_shelf(c):
    w, h = c.w, c.h
    for i, y in enumerate((h // 4, h // 2, h * 3 // 4 - 20)):
        c.rect(w // 8, y, w * 7 // 8, y + 12, (150, 108, 72))
        c.rect(w // 5 + i * 12, y - h // 8, w // 5 + i * 12 + w // 10,
               y, (255 - i * 10, 236 - i * 8, 180))
        c.circle(w * 3 // 5, y - h // 12, 14, (150, 60, 70))
    c.band(h * 3 // 4 + 20, h, (60, 40, 52))


def _v_start(c):
    w, h = c.w, c.h
    c.triangle(w // 8, h * 3 // 4, w * 7 // 8, h // 5, (255, 236, 180))
    c.circle(w // 2, h // 2, w // 9, (60, 40, 52))
    for x in (w // 5, w * 2 // 5, w * 3 // 5, w * 4 // 5):
        c.circle(x, h * 5 // 6, 9, (255, 214, 130))
    c.band(h * 3 // 4, h, (22, 26, 48))


def _v_alarm(c):
    w, h = c.w, c.h
    c.circle(w // 2, h // 3, w // 5, (255, 240, 235))
    c.circle(w // 2, h // 3, w // 8, (255, 92, 92))
    c.rect(w // 2 - 5, h // 3 - w // 5, w // 2 + 5, h // 3, (24, 24, 28))
    for y in (h // 2, h * 3 // 5, h * 7 // 10):
        c.band(y, y + 10, (255, 92, 92))
    c.band(h * 4 // 5, h, (24, 24, 28))


def _v_ten(c):
    w, h = c.w, c.h
    for i in range(10):
        x = w // 10 + i * w * 4 // 45
        bar_h = h // 6 + (i % 4) * h // 16
        c.rect(x, h * 2 // 3 - bar_h, x + w // 18, h * 2 // 3,
               (44, 100, 78) if i % 2 else (64, 128, 96))
    c.band(h * 2 // 3, h, (30, 70, 58))
    c.circle(w // 2, h // 5, w // 10, (255, 244, 200))


def _v_pace(c):
    w, h = c.w, c.h
    c.triangle(0, h, w // 2, h // 4, (52, 74, 104))
    c.triangle(w // 3, h, w, h // 3, (36, 54, 82))
    c.circle(w * 3 // 4, h // 5, w // 12, (240, 244, 250))
    for x in (w // 4, w // 2, w * 3 // 4):
        c.triangle(x - 20, h, x + 20, h * 2 // 3, (24, 60, 52))


def _v_silence(c):
    w, h = c.w, c.h
    c.rect(w // 4, h // 4, w * 3 // 4, h * 3 // 4, (40, 48, 70))
    c.rect(w // 4, h // 4, w * 3 // 4, h // 4 + 16, (90, 100, 140))
    c.circle(w // 3, h // 2, h // 12, (245, 245, 248))
    c.circle(w * 2 // 3, h // 2, h // 12, (245, 245, 248))
    c.rect(w // 3, h // 2 - h // 40, w * 2 // 3, h // 2 + h // 40,
           (40, 48, 70))
    for i in range(4):
        c.band(h // 6 + i * 12, h // 6 + i * 12 + 5,
               (120 + i * 20, 140 + i * 15, 180))


def _v_session(c):
    w, h = c.w, c.h
    c.rect(w // 6, h // 5, w * 5 // 6, h * 4 // 5, (250, 250, 252))
    for i in range(5):
        y = h // 5 + 24 + i * h // 8
        c.rect(w // 6 + 20, y, w // 6 + 20 + (w // 2 - i * w // 14), y + 14,
               (36 + i * 8, 120 + i * 10, 150 + i * 8))
    c.circle(w * 4 // 5, h // 4, 20, (250, 214, 222))
    c.band(h * 4 // 5, h, (24, 80, 110))


def _v_button(c):
    w, h = c.w, c.h
    c.circle(w // 2, h // 2, w // 6, (120, 200, 220))
    c.circle(w // 2, h // 2, w // 9, (24, 80, 110))
    c.circle(w // 2, h // 2, w // 18, (245, 245, 248))
    for gy in range(h // 8, h * 7 // 8, h // 8):
        for gx in range(w // 8, w * 7 // 8, w // 8):
            if (gx - w // 2) ** 2 + (gy - h // 2) ** 2 > (w // 5) ** 2:
                c.circle(gx, gy, 4, (255, 255, 255))


# v2 creative slug -> (painter, width, height, aspect label, blurb).
# Sizes follow the creative's format label exactly.
V2_ART = {
    "mirror-test": (_v_mirror, 720, 1280, "9:16", "skincare mirror portrait"),
    "three-steps": (_v_steps, 720, 1280, "9:16", "skincare routine steps"),
    "texture": (_v_texture, 1080, 1080, "1:1", "skincare texture bands"),
    "first-meeting": (_v_meeting, 720, 1280, "9:16", "coffee meeting table"),
    "desk-brew": (_v_desk, 720, 1280, "9:16", "coffee desk brewer"),
    "thirty-seconds": (_v_thirty, 1080, 1080, "1:1", "coffee timer rings"),
    "drawer-reset": (_v_drawer, 720, 1280, "9:16", "home drawer reset"),
    "one-shelf": (_v_shelf, 1080, 1080, "1:1", "home shelf styling"),
    "cleaner-start": (_v_start, 960, 1200, "4:5", "home fresh start"),
    "alarm": (_v_alarm, 720, 1280, "9:16", "fitness alarm clock"),
    "ten-minutes": (_v_ten, 720, 1280, "9:16", "fitness effort bars"),
    "your-pace": (_v_pace, 960, 1200, "4:5", "fitness trail peaks"),
    "desk-noise": (_v_silence, 1280, 720, "16:9", "headphones silence"),
    "focus-session": (_v_session, 1080, 1080, "1:1", "focus session board"),
    "one-button": (_v_button, 720, 1280, "9:16", "headphone button"),
}

V2_PALETTES = {
    "mirror-test": ((252, 222, 210), (196, 130, 140)),
    "three-steps": ((228, 238, 230), (120, 150, 140)),
    "texture": ((250, 214, 222), (170, 90, 110)),
    "first-meeting": ((245, 230, 205), (140, 96, 62)),
    "desk-brew": ((246, 232, 204), (150, 108, 72)),
    "thirty-seconds": ((255, 238, 200), (120, 180, 150)),
    "drawer-reset": ((240, 228, 200), (94, 64, 44)),
    "one-shelf": ((246, 232, 204), (150, 108, 72)),
    "cleaner-start": ((60, 70, 110), (22, 26, 48)),
    "alarm": ((255, 200, 190), (70, 60, 70)),
    "ten-minutes": ((255, 238, 200), (120, 180, 150)),
    "your-pace": ((150, 190, 225), (40, 60, 92)),
    "desk-noise": ((60, 70, 110), (22, 26, 48)),
    "focus-session": ((120, 200, 220), (24, 80, 110)),
    "one-button": ((120, 200, 220), (24, 80, 110)),
}


def v2_art_for_creative(slug):
    """(png bytes, width, height, aspect) for a v2 creative slug."""
    try:
        paint, w, h, aspect, _blurb = V2_ART[slug]
        top, bottom = V2_PALETTES[slug]
    except KeyError:
        raise ValueError("no v2 artwork for %r" % (slug,))
    return _scene_wh(w, h, (top, bottom), paint), w, h, aspect


def v2_art_manifest():
    """Provenance manifest for handover: slug, size, aspect, painter."""
    return [{"slug": slug, "width": spec[1], "height": spec[2],
             "aspect": spec[3], "scene": spec[4],
             "painter": spec[0].__name__, "provenance": "generated-stdlib"}
            for slug, spec in V2_ART.items()]


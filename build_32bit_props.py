#!/usr/bin/env python3
"""
Generates 13 crisp 32-bit arcade pixel-art prop sprites with hue-shifted shading,
Bayer dithering, specular highlights, tinted outlines, and grounded drop shadows.
Saves PNGs to sprites/props32/ and a 3x QA contact sheet to /tmp/props32_sheet.png.
"""
import os, io, base64, math
from PIL import Image, ImageDraw

OUT_DIR = "/home/antigravity/cetis69-defenders/sprites/props32"
os.makedirs(OUT_DIR, exist_ok=True)

OUTLINE = (22, 16, 28, 255)
BAYER2 = ((0, 2), (3, 1))

def rgba(hex_col, a=255):
    h = hex_col.lstrip('#')
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a)

def lerp_col(c1, c2, t):
    t = max(0.0, min(1.0, t))
    return tuple(int(round(c1[i] + (c2[i] - c1[i]) * t)) for i in range(4))

def put(px, w, h, x, y, col):
    x, y = int(round(x)), int(round(y))
    if 0 <= x < w and 0 <= y < h:
        if col[3] == 255:
            px[x, y] = col
        elif col[3] > 0:
            bg = px[x, y]
            a = col[3] / 255.0
            ia = 1.0 - a
            out_a = a + (bg[3] / 255.0) * ia
            if out_a <= 0:
                return
            r = int((col[0] * a + bg[0] * (bg[3] / 255.0) * ia) / out_a)
            g = int((col[1] * a + bg[1] * (bg[3] / 255.0) * ia) / out_a)
            b = int((col[2] * a + bg[2] * (bg[3] / 255.0) * ia) / out_a)
            px[x, y] = (r, g, b, int(out_a * 255))

def draw_shadow(img, cx, cy, rx, ry, alpha_core=118, alpha_edge=54):
    """Grounded soft-stepped 32-bit elliptical drop shadow."""
    w, h = img.size
    px = img.load()
    for y in range(max(0, int(cy - ry - 1)), min(h, int(cy + ry + 2))):
        for x in range(max(0, int(cx - rx - 1)), min(w, int(cx + rx + 2))):
            d = ((x - cx) / max(1, rx)) ** 2 + ((y - cy) / max(1, ry)) ** 2
            if d <= 0.58:
                put(px, w, h, x, y, (14, 10, 22, alpha_core))
            elif d <= 1.0:
                # 2x2 Bayer dithered edge for soft 32-bit shadow transition
                if d <= 0.82 or BAYER2[y & 1][x & 1] < 2:
                    put(px, w, h, x, y, (14, 10, 22, alpha_edge))

def add_outline(img, col=OUTLINE):
    """Adds 1px tinted dark pixel-art outline around opaque silhouette (skipping low-alpha shadows)."""
    w, h = img.size
    src = img.copy().load()
    dst = img.load()
    for y in range(h):
        for x in range(w):
            if src[x, y][3] >= 180:
                continue
            near = False
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h and src[nx, ny][3] >= 200:
                    near = True
                    break
            if near:
                dst[x, y] = col

def shaded_blob(img, cx, cy, rx, ry, ramp, light=(-0.45, -0.55), noise_fn=None):
    """Draws a 32-bit shaded rounded volume with Bayer dithering along a multi-stop hue-shifted ramp."""
    w, h = img.size
    px = img.load()
    n = len(ramp) - 1
    for y in range(max(0, int(cy - ry - 2)), min(h, int(cy + ry + 3))):
        for x in range(max(0, int(cx - rx - 2)), min(w, int(cx + rx + 3))):
            nx = (x - cx) / max(1.0, rx)
            ny = (y - cy) / max(1.0, ry)
            r2 = nx * nx + ny * ny
            if noise_fn:
                r2 += noise_fn(nx, ny)
            if r2 > 1.0:
                continue
            nz = math.sqrt(max(0.0, 1.0 - min(0.99, r2)))
            ndotl = max(0.0, min(1.0, (nx * light[0] + ny * light[1] + nz * 0.72 + 0.35) / 1.15))
            # Quantize to ramp with 2x2 Bayer dithering
            pos = ndotl * n
            idx = int(pos)
            frac = pos - idx
            if idx < n and frac > (BAYER2[y & 1][x & 1] + 0.5) / 4.0:
                idx += 1
            put(px, w, h, x, y, ramp[min(n, max(0, idx))])

def shaded_rect(img, x0, y0, rw, rh, ramp, vertical=True, border=OUTLINE):
    """32-bit beveled pixel box with top-left highlight, shaded body, and dark bottom-right edge."""
    w, h = img.size
    px = img.load()
    n = len(ramp) - 1
    for y in range(y0, y0 + rh):
        for x in range(x0, x0 + rw):
            if border and (x == x0 or x == x0 + rw - 1 or y == y0 or y == y0 + rh - 1):
                put(px, w, h, x, y, border)
                continue
            t = 1.0 - ((y - y0) / max(1, rh - 1) if vertical else (x - x0) / max(1, rw - 1))
            # Top-left bevel highlight
            if x == x0 + 1 or y == y0 + 1:
                t = min(1.0, t + 0.25)
            elif x == x0 + rw - 2 or y == y0 + rh - 2:
                t = max(0.0, t - 0.28)
            pos = t * n
            idx = int(pos)
            if idx < n and (pos - idx) > (BAYER2[y & 1][x & 1] + 0.5) / 4.0:
                idx += 1
            put(px, w, h, x, y, ramp[min(n, max(0, idx))])

# ---------------- 1. TRASH_DIRTY (64x48) ----------------
def make_trash_dirty():
    img = Image.new("RGBA", (64, 48), (0, 0, 0, 0))
    px = img.load()
    # Back olive-gray leaning bag
    olive = [rgba("#1e2420"), rgba("#2f3932"), rgba("#47554a"), rgba("#647568"), rgba("#8fa194")]
    shaded_blob(img, 42, 27, 13, 12, olive, noise_fn=lambda nx, ny: 0.14 * math.sin(nx * 4.5 + ny * 2.2))
    # Main big glossy dark-charcoal bulging plastic trash bag
    bag = [rgba("#141522"), rgba("#222638"), rgba("#333b54"), rgba("#4b5878"), rgba("#7c8db5"), rgba("#b7c7e8")]
    shaded_blob(img, 24, 29, 15, 13, bag, noise_fn=lambda nx, ny: 0.12 * math.cos(nx * 5.0 - ny * 3.0) + (0.18 if ny < -0.5 else 0))
    # Tied plastic bag neck & bunny-ear knot
    shaded_blob(img, 24, 15, 5, 4, bag)
    shaded_blob(img, 20, 11, 4, 3, bag)
    shaded_blob(img, 28, 12, 4, 3, bag)
    # Red tie string
    for x in range(20, 29):
        put(px, 64, 48, x, 16, rgba("#dc2626"))
        put(px, 64, 48, x, 17, rgba("#991b1b"))
    # Plastic specular fold creases on main bag
    for dx, dy in [(-7,-5),(-6,-6),(-5,-6),(-7,-4),(-6,-3),(-5,-2),(3,-3),(4,-2),(5,-1)]:
        put(px, 64, 48, 24 + dx, 29 + dy, rgba("#9fb4db"))
    # Crushed red/silver soda can in front-right
    shaded_rect(img, 41, 34, 12, 8, [rgba("#7f1d1d"), rgba("#b91c1c"), rgba("#ef4444"), rgba("#fca5a5")], vertical=True)
    for y in range(35, 41):
        put(px, 64, 48, 42, y, rgba("#cbd5e1"))
        put(px, 64, 48, 51, y, rgba("#94a3b8"))
    # Translucent cyan PET bottle front-left
    shaded_rect(img, 7, 34, 13, 7, [rgba("#0369a1"), rgba("#0ea5e9"), rgba("#7dd3fc"), rgba("#e0f2fe")], vertical=True)
    shaded_rect(img, 5, 36, 3, 3, [rgba("#cbd5e1"), rgba("#ffffff")], vertical=True)
    # Crumpled yellow notebook paper
    shaded_blob(img, 36, 39, 5, 4, [rgba("#a16207"), rgba("#eab308"), rgba("#fef08a"), rgba("#ffffff")])
    add_outline(img)
    # Put soft grounded shadow underneath
    final = Image.new("RGBA", (64, 48), (0, 0, 0, 0))
    draw_shadow(final, 32, 42, 26, 5)
    final.alpha_composite(img)
    # Tiny pixel stink flies above bag
    fpx = final.load()
    for fx, fy in [(14, 7), (35, 9), (46, 13)]:
        put(fpx, 64, 48, fx, fy, rgba("#18181b"))
        put(fpx, 64, 48, fx + 1, fy - 1, rgba("#d4d4d8", 180))
    return final

# ---------------- 2. RUBBLE (68x44) ----------------
def make_rubble():
    img = Image.new("RGBA", (68, 44), (0, 0, 0, 0))
    px = img.load()
    dust = [rgba("#44403c"), rgba("#57534e"), rgba("#78716c"), rgba("#a8a29e"), rgba("#d6d3d1")]
    conc = [rgba("#334155"), rgba("#475569"), rgba("#64748b"), rgba("#94a3b8"), rgba("#cbd5e1")]
    brick = [rgba("#5c1d0c"), rgba("#8c2d14"), rgba("#b8431e"), rgba("#d96534"), rgba("#f29668")]
    # Dusty mound base
    shaded_blob(img, 34, 31, 24, 9, dust, noise_fn=lambda nx, ny: 0.16 * math.sin(nx * 6))
    # Broken concrete slabs
    shaded_rect(img, 14, 21, 20, 12, conc, vertical=True)
    shaded_rect(img, 28, 17, 19, 13, conc, vertical=True)
    # Bent rusty rebar sticking out of concrete!
    for i in range(10):
        put(px, 68, 44, 45 + i, 19 - i // 2, rgba("#7c2d12"))
        put(px, 68, 44, 45 + i, 18 - i // 2, rgba("#c2410c"))
    for i in range(8):
        put(px, 68, 44, 15 - i, 22 - i // 2, rgba("#7c2d12"))
    # Scattered terracotta red bricks (32-bit shaded)
    shaded_rect(img, 20, 28, 14, 8, brick, vertical=True)
    shaded_rect(img, 36, 26, 15, 8, brick, vertical=True)
    shaded_rect(img, 29, 22, 13, 7, brick, vertical=True)
    shaded_rect(img, 46, 30, 13, 7, brick, vertical=True)
    # Wild 3-tone weed tufts sprouting through cracks!
    weeds = [(11, 31), (13, 27), (15, 32), (52, 26), (55, 29), (58, 25), (34, 15)]
    for wx, wy in weeds:
        for h in range(7):
            col = rgba("#365314") if h < 2 else (rgba("#4d7c0f") if h < 5 else rgba("#84cc16"))
            put(px, 68, 44, wx + (h % 2) - 1, wy - h, col)
            put(px, 68, 44, wx + 1, wy - h + 1, col)
    add_outline(img)
    final = Image.new("RGBA", (68, 44), (0, 0, 0, 0))
    draw_shadow(final, 34, 38, 28, 5)
    final.alpha_composite(img)
    return final

# ---------------- 3 & 4. BOOKS (MESSY & NEAT) ----------------
def draw_32bit_book(img, x0, y0, bw, bh, cover_ramp, tilt=0):
    px = img.load()
    w, h = img.size
    # Pages block (warm cream with horizontal page lines)
    for dy in range(bh):
        ox = int(round(dy * tilt))
        for dx in range(bw):
            x, y = x0 + dx + ox, y0 + dy
            if dy < 3 or dy >= bh - 3 or dx < 3:
                # Cover & spine
                t = 1.0 - (dy / max(1, bh - 1)) * 0.65 - (dx / max(1, bw - 1)) * 0.35
                idx = min(len(cover_ramp) - 1, max(0, int(t * len(cover_ramp))))
                put(px, w, h, x, y, cover_ramp[idx])
            else:
                # Cream page block with subtle ruling lines
                col = rgba("#e7dec8") if (dy % 2 == 0) else rgba("#fef9e7")
                if dx > bw - 3:
                    col = rgba("#cbbda0")
                put(px, w, h, x, y, col)
    # Gold spine accent
    for dy in range(2, bh - 2, 3):
        put(px, w, h, x0 + 1 + int(round(dy * tilt)), y0 + dy, rgba("#f5b700"))

def make_books(neat=False):
    w, h = (54, 46) if neat else (62, 44)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    px = img.load()
    blue   = [rgba("#172554"), rgba("#1d4ed8"), rgba("#3b82f6"), rgba("#93c5fd")]
    guinda = [rgba("#4c0d1f"), rgba("#7a1c33"), rgba("#9c2645"), rgba("#e11d48")]
    gold   = [rgba("#78350f"), rgba("#b45309"), rgba("#f59e0b"), rgba("#fde047")]
    if not neat:
        # Messy spilled Technical English textbooks + loose flying page!
        draw_32bit_book(img, 7, 25, 26, 11, blue, tilt=0.25)
        draw_32bit_book(img, 24, 21, 26, 11, guinda, tilt=-0.2)
        draw_32bit_book(img, 18, 12, 24, 10, gold, tilt=0.15)
        # Loose paper sheet on floor
        shaded_rect(img, 42, 32, 13, 7, [rgba("#cbd5e1"), rgba("#f1f5f9"), rgba("#ffffff")], vertical=True)
        for lx in range(44, 52):
            put(px, w, h, lx, 34, rgba("#64748b"))
            put(px, w, h, lx, 36, rgba("#64748b"))
    else:
        # Crisp neat stack of 3 gleaming hardcover books + red ribbon bookmark!
        draw_32bit_book(img, 11, 28, 32, 11, blue, tilt=0.0)
        draw_32bit_book(img, 12, 18, 30, 11, guinda, tilt=0.0)
        draw_32bit_book(img, 13, 9,  28, 10, gold, tilt=0.0)
        # Silk red bookmark ribbon hanging from top book
        for ry in range(16, 26):
            put(px, w, h, 35, ry, rgba("#ef4444"))
            put(px, w, h, 36, ry, rgba("#b91c1c"))
        # Golden sparkle gleam on top corner
        for sx, sy in [(42,6),(41,7),(42,7),(43,7),(42,8)]:
            put(px, w, h, sx, sy, rgba("#fef9c3"))
    add_outline(img)
    final = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw_shadow(final, w // 2, h - 5, w // 2 - 6, 4)
    final.alpha_composite(img)
    return final

# ---------------- 5 & 6. BENCH (DIRTY & CLEAN) ----------------
def make_bench(clean=True):
    w, h = 76, 48
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    px = img.load()
    iron = [rgba("#111827"), rgba("#1f2937"), rgba("#475569"), rgba("#94a3b8")]
    slat_back = [rgba("#4c0d1f"), rgba("#7a1c33"), rgba("#9c2645"), rgba("#d9466a")] if clean else [rgba("#3f3f46"), rgba("#52525b"), rgba("#71717a"), rgba("#a1a1aa")]
    slat_seat = [rgba("#78350f"), rgba("#b45309"), rgba("#d97706"), rgba("#f5b700"), rgba("#fde047")] if clean else [rgba("#27272a"), rgba("#44403c"), rgba("#57534e"), rgba("#78716c")]

    # Back cast-iron supports
    shaded_rect(img, 12, 11, 5, 29, iron, vertical=False)
    shaded_rect(img, 59, 11, 5, 29, iron, vertical=False)
    # 3 wooden backrest slats
    shaded_rect(img, 8, 12, 60, 6, slat_back, vertical=True)
    shaded_rect(img, 8, 19, 60, 6, slat_back, vertical=True)
    # Seat planks (slightly wider for 2.5D depth)
    shaded_rect(img, 6, 27, 64, 7, slat_seat, vertical=True)
    # Front iron legs + curved armrests
    shaded_rect(img, 8, 24, 5, 18, iron, vertical=False)
    shaded_rect(img, 63, 24, 5, 18, iron, vertical=False)
    shaded_rect(img, 7, 23, 8, 4, iron, vertical=True)
    shaded_rect(img, 61, 23, 8, 4, iron, vertical=True)
    # Metallic bolts
    for bx in (14, 61):
        for by in (15, 22, 30):
            put(px, w, h, bx, by, rgba("#fde047") if clean else rgba("#94a3b8"))
    if clean:
        # Gold "69" center emblem plaque on backrest
        shaded_rect(img, 33, 14, 10, 8, [rgba("#b45309"), rgba("#f5b700"), rgba("#fef08a")], vertical=True)
    else:
        # Vandal graffiti splatters & chipped wood notch
        for gx, gy in [(22,14),(23,14),(24,15),(25,15),(26,14),(24,16),(25,17),(23,20),(24,20),(25,21)]:
            put(px, w, h, gx, gy, rgba("#ec4899"))
        for gx, gy in [(42,15),(43,15),(44,16),(45,16),(46,15),(44,21),(45,21),(46,20)]:
            put(px, w, h, gx, gy, rgba("#a855f7"))
        for rx, ry in [(10,36),(64,37),(65,35)]:
            put(px, w, h, rx, ry, rgba("#9a3412"))

    add_outline(img)
    final = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw_shadow(final, 38, 42, 32, 4)
    final.alpha_composite(img)
    return final

# ---------------- 7 & 8. FOUNTAIN / WATER PIPE (LEAK & FIXED) ----------------
def make_fountain(fixed=False):
    w, h = 64, 60
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    px = img.load()
    conc = [rgba("#334155"), rgba("#475569"), rgba("#64748b"), rgba("#94a3b8"), rgba("#cbd5e1")]
    pipe = [rgba("#1e293b"), rgba("#334155"), rgba("#64748b"), rgba("#94a3b8"), rgba("#e2e8f0")]
    valve = [rgba("#14532d"), rgba("#16a34a"), rgba("#4ade80"), rgba("#bbf7d0")] if fixed else [rgba("#7f1d1d"), rgba("#b91c1c"), rgba("#ef4444"), rgba("#fca5a5")]

    # Concrete mounting collar
    shaded_rect(img, 18, 44, 28, 10, conc, vertical=True)
    # Cylindrical vertical iron pipe (horizontal shading!)
    shaded_rect(img, 24, 24, 16, 22, pipe, vertical=False)
    # Pipe flange ring
    shaded_rect(img, 21, 30, 22, 5, pipe, vertical=True)
    # Valve top cap + spoked wheel handle
    shaded_rect(img, 27, 19, 10, 6, valve, vertical=True)
    shaded_rect(img, 20, 15, 24, 5, valve, vertical=True)
    # Brass gauge dial on side
    shaded_blob(img, 42, 34, 4, 4, [rgba("#78350f"), rgba("#f59e0b"), rgba("#fef08a")])
    put(px, w, h, 42, 34, rgba("#ffffff"))
    add_outline(img)

    final = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw_shadow(final, 32, 54, 22, 4)
    if not fixed:
        # Shimmering 32-bit multi-tone water puddle around pipe base!
        puddle = [rgba("#0369a1"), rgba("#0ea5e9"), rgba("#38bdf8"), rgba("#bae6fd")]
        shaded_blob(final, 32, 52, 27, 6, puddle)
        fpx = final.load()
        for rx in range(14, 50, 7):
            put(fpx, w, h, rx, 51, rgba("#ffffff", 200))
            put(fpx, w, h, rx + 1, 51, rgba("#e0f2fe", 180))
    final.alpha_composite(img)
    return final

# ---------------- 9 & 10. LAMP (BROKEN & LIT) ----------------
def make_lamp(lit=True):
    w, h = 56, 84
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    px = img.load()
    conc = [rgba("#334155"), rgba("#475569"), rgba("#64748b"), rgba("#94a3b8"), rgba("#cbd5e1")]
    steel = [rgba("#1e293b"), rgba("#334155"), rgba("#64748b"), rgba("#94a3b8"), rgba("#e2e8f0")]
    solar = [rgba("#0f172a"), rgba("#1e3a8a"), rgba("#2563eb"), rgba("#38bdf8")]

    # Concrete octagonal pedestal base
    shaded_rect(img, 19, 68, 18, 10, conc, vertical=True)
    shaded_rect(img, 22, 62, 12, 7, conc, vertical=True)
    # Fluted steel pole (horizontal metallic cylinder shading)
    shaded_rect(img, 25, 18, 6, 46, steel, vertical=False)
    # Solar panel angled on top
    shaded_rect(img, 18, 7, 20, 6, solar, vertical=True)
    for sx in range(21, 36, 4):
        put(px, w, h, sx, 9, rgba("#93c5fd"))
        put(px, w, h, sx, 11, rgba("#93c5fd"))
    # Cobra LED lamp arm & head
    shaded_rect(img, 15, 14, 26, 7, steel, vertical=True)
    if lit:
        shaded_rect(img, 17, 19, 22, 5, [rgba("#f59e0b"), rgba("#fde047"), rgba("#fef9c3"), rgba("#ffffff")], vertical=True)
    else:
        shaded_rect(img, 17, 19, 22, 5, [rgba("#18181b"), rgba("#27272a"), rgba("#3f3f46")], vertical=True)
        # Dangling broken copper wire
        for wy in range(24, 34):
            put(px, w, h, 18 + (wy % 2), wy, rgba("#ea580c"))
    add_outline(img)

    final = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw_shadow(final, 28, 78, 14, 4)
    if lit:
        # 32-bit stepped Bayer-dithered golden pixel bloom (NO blurry gradient!)
        fpx = final.load()
        for y in range(14, 58):
            for x in range(6, 50):
                d = math.hypot((x - 28) / 21.0, (y - 26) / 26.0)
                if d < 1.0 and (d < 0.55 or BAYER2[y & 1][x & 1] < 2):
                    a = int((1.0 - d) * 95)
                    put(fpx, w, h, x, y, (254, 240, 138, a))
    final.alpha_composite(img)
    return final

# ---------------- 11. RECYCLE_STATION (72x48) ----------------
def make_recycle_station():
    w, h = 72, 48
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    px = img.load()
    steel = [rgba("#1e293b"), rgba("#334155"), rgba("#64748b"), rgba("#94a3b8")]
    bins = [
        (7,  [rgba("#14532d"), rgba("#15803d"), rgba("#22c55e"), rgba("#86efac")]),
        (27, [rgba("#1e3a8a"), rgba("#1d4ed8"), rgba("#3b82f6"), rgba("#93c5fd")]),
        (47, [rgba("#78350f"), rgba("#b45309"), rgba("#eab308"), rgba("#fef08a")]),
    ]
    # Steel mounting base rail
    shaded_rect(img, 5, 39, 62, 5, steel, vertical=True)
    for bx, ramp in bins:
        # Hooded lid
        shaded_rect(img, bx + 1, 9, 16, 8, ramp, vertical=True)
        # Dark trash slot opening
        shaded_rect(img, bx + 4, 12, 10, 4, [rgba("#09090b"), rgba("#18181b")], vertical=True)
        # Main body with cylinder horizontal shading
        shaded_rect(img, bx, 16, 18, 25, ramp, vertical=False)
        # White recycle triangle emblem
        for ex, ey in [(bx+8,24),(bx+9,24),(bx+7,26),(bx+10,26),(bx+6,28),(bx+7,28),(bx+8,28),(bx+9,28),(bx+10,28),(bx+11,28)]:
            put(px, w, h, ex, ey, rgba("#ffffff"))
    add_outline(img)
    final = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw_shadow(final, 36, 44, 32, 4)
    final.alpha_composite(img)
    return final

# ---------------- 12. SPRAY_CANS (40x32) ----------------
def make_spray_cans():
    w, h = 40, 32
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    mag = [rgba("#701a75"), rgba("#a21caf"), rgba("#e879f9"), rgba("#f5d0fe")]
    cyn = [rgba("#164e63"), rgba("#0891b2"), rgba("#22d3ee"), rgba("#cffafe")]
    cap = [rgba("#cbd5e1"), rgba("#f1f5f9"), rgba("#ffffff")]
    # Standing magenta spray can
    shaded_rect(img, 8, 10, 10, 16, mag, vertical=False)
    shaded_rect(img, 10, 6, 6, 5, cap, vertical=False)
    shaded_rect(img, 12, 4, 2, 3, [rgba("#18181b"), rgba("#f8fafc")], vertical=True)
    # Tilted / second cyan spray can
    shaded_rect(img, 21, 13, 10, 14, cyn, vertical=False)
    shaded_rect(img, 23, 9, 6, 5, cap, vertical=False)
    add_outline(img)
    final = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw_shadow(final, 20, 27, 15, 3)
    final.alpha_composite(img)
    return final

# ---------------- 13. PLANTER_BRICK (72x26) ----------------
def make_planter_brick():
    w, h = 72, 26
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    px = img.load()
    brick = [rgba("#5c1d0c"), rgba("#8c2d14"), rgba("#b8431e"), rgba("#d96534")]
    rim   = [rgba("#64748b"), rgba("#94a3b8"), rgba("#cbd5e1"), rgba("#f1f5f9")]
    soil  = [rgba("#291a12"), rgba("#452b1d"), rgba("#63412c")]
    # Soil top surface
    shaded_rect(img, 6, 4, 60, 7, soil, vertical=True)
    # Beveled stone rim
    shaded_rect(img, 4, 8, 64, 5, rim, vertical=True)
    # Brick front wall with mortar joints
    shaded_rect(img, 6, 12, 60, 10, brick, vertical=True)
    for row, y in enumerate([16]):
        for x in range(7, 65):
            put(px, w, h, x, y, rgba("#442014"))
    for x in range(14, 62, 10):
        for y in range(13, 16): put(px, w, h, x, y, rgba("#442014"))
    for x in range(19, 62, 10):
        for y in range(17, 21): put(px, w, h, x, y, rgba("#442014"))
    add_outline(img)
    final = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw_shadow(final, 36, 22, 33, 3)
    final.alpha_composite(img)
    return final

SPRITES = {
    "trash_dirty": make_trash_dirty,
    "rubble": make_rubble,
    "books_messy": lambda: make_books(False),
    "books_neat": lambda: make_books(True),
    "bench_dirty": lambda: make_bench(False),
    "bench_clean": lambda: make_bench(True),
    "fountain_leak": lambda: make_fountain(False),
    "fountain_fixed": lambda: make_fountain(True),
    "lamp_broken": lambda: make_lamp(False),
    "lamp_lit": lambda: make_lamp(True),
    "recycle_station": make_recycle_station,
    "spray_cans": make_spray_cans,
    "planter_brick": make_planter_brick,
}

out_json = {}
imgs = []
for name, fn in SPRITES.items():
    im = fn()
    path = os.path.join(OUT_DIR, f"{name}.png")
    im.save(path, "PNG", optimize=True)
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    b64 = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    out_json[name] = b64
    imgs.append((name, im, len(buf.getvalue())))

total_bytes = sum(b for _, _, b in imgs)
print(f"Generated {len(imgs)} 32-bit pixel-art sprites, total PNG size = {total_bytes/1024:.1f} KB")
for name, im, b in imgs:
    print(f"  {name:16s} {im.size[0]}x{im.size[1]}  {b:4d} B")

# Render a 3x zoomed QA contact sheet on sidewalk-gray background
cols = 5
rows = math.ceil(len(imgs) / cols)
cell_w, cell_h = 250, 270
sheet = Image.new("RGBA", (cols * cell_w, rows * cell_h), rgba("#8c96a3"))
dr = ImageDraw.Draw(sheet)
for idx, (name, im, _) in enumerate(imgs):
    r, c = divmod(idx, cols)
    x0, y0 = c * cell_w, r * cell_h
    dr.rectangle([x0 + 4, y0 + 4, x0 + cell_w - 4, y0 + cell_h - 4], outline=rgba("#334155"))
    scaled = im.resize((im.size[0] * 3, im.size[1] * 3), Image.NEAREST)
    sheet.alpha_composite(scaled, (x0 + (cell_w - scaled.size[0]) // 2, y0 + (cell_h - 24 - scaled.size[1]) // 2))
    dr.text((x0 + 12, y0 + cell_h - 22), name, fill=rgba("#0f172a"))
sheet.save("/tmp/props32_sheet.png")
print("Contact sheet saved to /tmp/props32_sheet.png")

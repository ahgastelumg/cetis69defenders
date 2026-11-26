#!/usr/bin/env python3
"""
Builds a single seamless, organic 2400x450 32-bit pixel-art street panorama for
CETis 69 Defenders Explore Mode (Col. Benito Juárez, Cd. Obregón) with ZERO
vertical seams at x=800 and x=1600, then slices it into 3 memory-friendly
800x450 JPEG tiles (explore, explore2, explore3).
"""
import os, io, re, json, math, base64
from PIL import Image, ImageDraw

INDEX = "/home/antigravity/cetis69-defenders/index.html"
OUT_DIR = "/home/antigravity/cetis69-defenders/sprites/explore_v2"
os.makedirs(OUT_DIR, exist_ok=True)

BAYER2 = ((0, 2), (3, 1))
OUTLINE = (22, 16, 28)

def rgb(h):
    h = h.lstrip('#')
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))

def lerp(c1, c2, t):
    t = max(0.0, min(1.0, t))
    return (
        int(round(c1[0] + (c2[0] - c1[0]) * t)),
        int(round(c1[1] + (c2[1] - c1[1]) * t)),
        int(round(c1[2] + (c2[2] - c1[2]) * t)),
    )

def mix_alpha(base, col, a):
    return lerp(base, col, a)

def draw_dither_rect(px, W, H, x0, y0, rw, rh, c_top, c_bot, vertical=True, border=None):
    for y in range(max(0, y0), min(H, y0 + rh)):
        for x in range(max(0, x0), min(W, x0 + rw)):
            if border and (x == x0 or x == x0 + rw - 1 or y == y0 or y == y0 + rh - 1):
                px[x, y] = border
                continue
            t = (y - y0) / max(1, rh - 1) if vertical else (x - x0) / max(1, rw - 1)
            # Quantize to 5 crisp 32-bit steps with 2x2 Bayer dithering
            steps = 5
            pos = t * steps
            idx = int(pos)
            if idx < steps and (pos - idx) > (BAYER2[y & 1][x & 1] + 0.5) / 4.0:
                idx += 1
            px[x, y] = lerp(c_top, c_bot, idx / steps)

def px_box(px, W, H, x0, y0, rw, rh, ramp, vertical=True, border=OUTLINE):
    n = len(ramp) - 1
    for y in range(max(0, y0), min(H, y0 + rh)):
        for x in range(max(0, x0), min(W, x0 + rw)):
            if border and (x == x0 or x == x0 + rw - 1 or y == y0 or y == y0 + rh - 1):
                px[x, y] = border
                continue
            t = 1.0 - ((y - y0) / max(1, rh - 1) if vertical else (x - x0) / max(1, rw - 1))
            if x == x0 + 1 or y == y0 + 1:
                t = min(1.0, t + 0.22)
            elif x == x0 + rw - 2 or y == y0 + rh - 2:
                t = max(0.0, t - 0.25)
            pos = t * n
            idx = int(pos)
            if idx < n and (pos - idx) > (BAYER2[y & 1][x & 1] + 0.5) / 4.0:
                idx += 1
            px[x, y] = ramp[min(n, max(0, idx))]

def draw_palm(px, W, H, bx, by, h_trunk=105, lean=10, tint_warm=0.0):
    trunk_c = [rgb("#452616"), rgb("#6b3c22"), rgb("#8f5534"), rgb("#b8744a")]
    leaf_c  = [rgb("#14532d"), rgb("#15803d"), rgb("#22c55e"), rgb("#4ade80")]
    if tint_warm > 0:
        leaf_c = [lerp(c, rgb("#d97706"), tint_warm * 0.35) for c in leaf_c]
    # Curved segmented trunk
    for i in range(h_trunk):
        t = i / max(1, h_trunk)
        cx = int(bx + math.sin(t * 1.4) * lean)
        cy = by - i
        tw = max(4, int(9 - t * 4))
        seg = (i // 6) % 2
        for dx in range(-tw // 2, tw // 2 + 1):
            x = cx + dx
            if 0 <= x < W and 0 <= cy < H:
                if dx == -tw // 2 or dx == tw // 2:
                    px[x, cy] = OUTLINE
                else:
                    lt = 1.0 - (dx + tw // 2) / max(1, tw)
                    idx = min(3, max(0, int((lt + seg * 0.18) * 3)))
                    px[x, cy] = trunk_c[idx]
    top_x = int(bx + math.sin(1.4) * lean)
    top_y = by - h_trunk
    # 7 arching pixel palm fronds
    fronds = [(-38, -6, 12), (-32, -20, 8), (-16, -28, 6), (0, -24, 5), (18, -27, 6), (34, -18, 9), (40, -4, 13)]
    for fx, fy, droop in fronds:
        steps = 22
        for s in range(steps):
            t = s / steps
            x = int(top_x + fx * t)
            y = int(top_y + fy * t + droop * (t * t))
            thick = max(2, int(6 * (1 - t * 0.65)))
            for dy in range(-1, thick):
                yy = y + dy
                if 0 <= x < W and 0 <= yy < H:
                    col = leaf_c[3] if dy <= 0 else (leaf_c[2] if dy == 1 else (leaf_c[1] if dy < thick - 1 else leaf_c[0]))
                    px[x, yy] = col
                    if x + 1 < W:
                        px[x + 1, yy] = col

def draw_shade_tree(px, W, H, cx, cy, r=28):
    # Trunk
    px_box(px, W, H, cx - 5, cy - 28, 10, 28, [rgb("#3f2113"), rgb("#6b3c22"), rgb("#925634")], vertical=False)
    # Multi-cluster 32-bit foliage
    ramp = [rgb("#0f3d21"), rgb("#14532d"), rgb("#15803d"), rgb("#22c55e"), rgb("#4ade80")]
    clusters = [(cx - r // 2, cy - 34, r * 0.65), (cx + r // 2, cy - 32, r * 0.62), (cx, cy - 44, r * 0.78)]
    for kx, ky, kr in clusters:
        for y in range(max(0, int(ky - kr - 1)), min(H, int(ky + kr + 2))):
            for x in range(max(0, int(kx - kr - 1)), min(W, int(kx + kr + 2))):
                nx = (x - kx) / kr
                ny = (y - ky) / kr
                d = nx * nx + ny * ny + 0.12 * math.sin(nx * 5 + ny * 4)
                if d > 1.0:
                    continue
                if d > 0.88:
                    px[x, y] = OUTLINE
                    continue
                nd = max(0.0, min(1.0, (-nx * 0.45 - ny * 0.55 + math.sqrt(max(0, 1 - d)) * 0.65 + 0.3)))
                pos = nd * 4
                idx = int(pos)
                if idx < 4 and (pos - idx) > (BAYER2[y & 1][x & 1] + 0.5) / 4.0:
                    idx += 1
                px[x, y] = ramp[min(4, max(0, idx))]

# 1. Load original Zone 1 artwork (`benito_juarez_bridge_bg` or existing `explore` in index.html)
s = open(INDEX, encoding="utf-8").read()
m = re.search(r'const GAME_ASSETS = (\{.*?\});', s)
assets = json.loads(m.group(1))
z1_orig = Image.open(io.BytesIO(base64.b64decode(assets["bgs"]["explore"].split(",")[1]))).convert("RGB")
z1 = z1_orig.resize((800, 450), Image.NEAREST)

# Create single continuous 2400x450 canvas!
W, H = 2400, 450
pano = Image.new("RGB", (W, H), rgb("#4a90e2"))
pano.paste(z1, (0, 0))
px = pano.load()

# Inspect exact road/sidewalk/curb bands from Zone 1 around x=380 (sunlit street reference!)
# Curb back sidewalk: y=282..297, curb edge y=298..302, road asphalt y=303..411, front curb y=412..417, front sidewalk y=418..449
ref_sidewalk_y = [z1.getpixel((380, y)) for y in range(282, 450)]
ref_sky_z1 = [z1.getpixel((380, y)) for y in range(0, 220)]

# Clean Sonora afternoon day sky ramp sampled from Zone 1's pure sky band (y=0..115, zero building/wire artifacts!)
sky_top_z1 = z1.getpixel((380, 10))
sky_mid_z1 = z1.getpixel((380, 75))
sky_hor_z1 = rgb("#b8dff5")

# 2. CONTINUOUS SKY across x=800..2400 (smooth Bayer-dithered transition: Obregón afternoon blue -> warm Sonora sunset!)
for x in range(800, W):
    tw = max(0.0, min(1.0, (x - 1150) / 620.0))
    for y in range(0, 284):
        ty = y / 284.0
        # Clean stepped 32-bit day sky matching Zone 1's exact blue!
        if ty < 0.45:
            day_c = lerp(sky_top_z1, sky_mid_z1, ty / 0.45)
        else:
            day_c = lerp(sky_mid_z1, sky_hor_z1, (ty - 0.45) / 0.55)
        # Warm Sonora sunset sky (deep indigo top -> magenta-coral -> golden amber horizon)
        if ty < 0.35:
            sun_c = lerp(rgb("#2b234d"), rgb("#73345e"), ty / 0.35)
        elif ty < 0.72:
            sun_c = lerp(rgb("#73345e"), rgb("#d96b43"), (ty - 0.35) / 0.37)
        else:
            sun_c = lerp(rgb("#d96b43"), rgb("#f6c26b"), (ty - 0.72) / 0.28)
        steps = 8
        pos = tw * steps
        idx = int(pos)
        if idx < steps and (pos - idx) > (BAYER2[y & 1][x & 1] + 0.5) / 4.0:
            idx += 1
        px[x, y] = lerp(day_c, sun_c, idx / steps)

# Distant stepped Sonora Sierra mountains & sunset clouds (x=860..2400)
for mx, mw, mh in [(960, 180, 48), (1180, 220, 62), (1440, 200, 52), (1760, 240, 64), (2060, 210, 56), (2300, 190, 50)]:
    tw = max(0.0, min(1.0, (mx - 1150) / 620.0))
    mc = lerp(rgb("#7c9bc0"), rgb("#4a3357"), tw)
    mhi = lerp(rgb("#99b6d6"), rgb("#6e4369"), tw)
    for step in range(0, mh, 4):
        w_s = max(16, int(mw * (1 - step / mh)))
        yy = 236 - step
        for x in range(max(800, mx - w_s // 2), min(W, mx + w_s // 2)):
            for dy in range(4):
                if 0 <= yy + dy < 284:
                    px[x, yy + dy] = mhi if x < mx - w_s // 6 else mc

# Distant continuous Obregón neighborhood skyline (low-rise stucco homes & water tanks behind park/bridge!)
skyline_buildings = [
    (915, 192, 68, 92, "#c8a98a", "#8f6e52"),
    (988, 206, 58, 78, "#b7c4cf", "#6b7c8c"),
    (1055, 198, 64, 86, "#d9c2a3", "#967a5c"),
    (1130, 210, 62, 74, "#c4b6a6", "#7a6e60"),
    (1200, 196, 72, 88, "#d6b892", "#8a6d4b"),
    (1280, 208, 60, 76, "#b8c0c8", "#6c7680"),
    (1555, 194, 70, 90, "#b8907a", "#6e4e44"),
    (1632, 206, 62, 78, "#948494", "#54485c"),
    (1730, 198, 74, 86, "#6a5473", "#3d2f4a"),
    (1910, 192, 86, 92, "#5b4866", "#352840"),
    (2160, 196, 82, 88, "#564361", "#31243b"),
]
for bx, by, bw, bh, c_wall, c_shade in skyline_buildings:
    tw = max(0.0, min(1.0, (bx - 1200) / 600.0))
    wcol = lerp(rgb(c_wall), rgb("#533d5c"), tw * 0.55)
    scol = lerp(rgb(c_shade), rgb("#2f213b"), tw * 0.55)
    px_box(px, W, H, bx, by, bw, bh, [scol, lerp(scol, wcol, 0.5), wcol], vertical=False, border=lerp(OUTLINE, scol, 0.35))
    px_box(px, W, H, bx - 2, by - 4, bw + 4, 5, [scol, wcol], vertical=True, border=OUTLINE)
    if (bx % 3) == 0:
        px_box(px, W, H, bx + 12, by - 16, 14, 13, [rgb("#1e293b"), rgb("#334155"), rgb("#475569")], vertical=False)
    for wx in range(bx + 10, bx + bw - 14, 18):
        px_box(px, W, H, wx, by + 16, 10, 14, [rgb("#1e293b"), rgb("#3b4f6b"), lerp(rgb("#7dd3fc"), rgb("#f59e0b"), tw)], vertical=True)

# 3. CONTINUOUS SIDEWALK, CURB, ASPHALT ROAD & FOREGROUND SIDEWALK (x=780..2400 — ZERO SEAM!)
#    Smoothly cross-fade x=772..804 with Zone 1 so there is NEVER a vertical jump at x=800!
for x in range(772, W):
    tw = max(0.0, min(1.0, (x - 1450) / 380.0))
    blend_z1 = max(0.0, min(1.0, (x - 772) / 28.0))
    for y in range(282, 450):
        base = ref_sidewalk_y[y - 282]
        col = lerp(base, lerp(base, rgb("#3b354d"), 0.34), tw)
        if 303 <= y <= 411 and ((x * 7 + y * 13) % 29 == 0):
            col = lerp(col, (20, 18, 28), 0.14)
        elif (282 <= y <= 297 or y >= 418) and ((x * 11 + y * 5) % 37 == 0):
            col = lerp(col, (240, 240, 248), 0.10)
        if x < 800:
            # Cross-fade cleanly into Zone 1's actual pixels
            px[x, y] = lerp(z1.getpixel((x, y)), col, blend_z1)
        else:
            px[x, y] = col

# Continuous concrete sidewalk expansion joints (exact cadence matching Zone 1!)
for sx in range(820, W, 68):
    for y in range(282, 299):
        px[sx, y] = lerp(px[sx, y], OUTLINE, 0.55)
        if sx + 1 < W:
            px[sx + 1, y] = lerp(px[sx + 1, y], (235, 235, 245), 0.25)
    for dy in range(0, 32):
        jx = sx - int(dy * 0.45)
        if 800 <= jx < W:
            px[jx, 418 + dy] = lerp(px[jx, 418 + dy], OUTLINE, 0.65)
            if jx + 1 < W:
                px[jx + 1, 418 + dy] = lerp(px[jx + 1, 418 + dy], (235, 235, 245), 0.28)

# Continuous crisp road lane dashes (exact y=343..346 match to Zone 1's white lane stripe!)
for lx in range(835, W - 40, 96):
    tw = max(0.0, min(1.0, (lx - 1450) / 380.0))
    lc = lerp(rgb("#b8bcc4"), rgb("#9a92a3"), tw * 0.4)
    for x in range(lx, min(W, lx + 48)):
        for y in range(343, 347):
            px[x, y] = lc

# 4. ORGANIC SEAM 1 (x = 776 .. 940): NATURAL EXIT OF THE ZONE 1 OVERPASS BRIDGE INTO SUNLIGHT!
#    Back retaining wall under exit arch (blended seamlessly from Zone 1's right arch at x=778!)
px_box(px, W, H, 778, 178, 66, 106, [rgb("#383a47"), rgb("#4f5261"), rgb("#6a6e80")], vertical=True, border=OUTLINE)
# Horizontal concrete crossbeam continuing Zone 1's exact beam (y=154..180) directly onto the exit pier!
px_box(px, W, H, 778, 154, 92, 26, [rgb("#1f212e"), rgb("#35394a"), rgb("#4f5469")], vertical=True, border=OUTLINE)
# Shaded concrete bridge exit pier (x=822..868, sitting cleanly UNDER the crossbeam y=178..285!)
px_box(px, W, H, 822, 178, 46, 107, [rgb("#343845"), rgb("#525869"), rgb("#767e91"), rgb("#9da6b8")], vertical=False, border=OUTLINE)
px_box(px, W, H, 818, 174, 54, 10, [rgb("#414757"), rgb("#6b7385"), rgb("#949db0")], vertical=True, border=OUTLINE)

# Angled Concrete Overpass Deck & Underside Ribs (matching Zone 1's deep #0c0b12 underside -> exiting upward organically!)
for x in range(778, 918):
    deck_bot = int(154 - (x - 778) * 1.18)
    fascia_bot = int(184 - (x - 778) * 1.18)
    for y in range(0, max(0, fascia_bot)):
        if y < deck_bot:
            rib = ((x + y) // 16) % 2
            px[x, y] = rgb("#0d0c14") if rib else rgb("#171624")
        elif y == deck_bot or y == fascia_bot - 1:
            px[x, y] = OUTLINE
        else:
            t = (y - deck_bot) / max(1, fascia_bot - deck_bot)
            px[x, y] = lerp(rgb("#b4bcc9"), rgb("#687180"), t)

# Concrete planter & Sonora cactus beside bridge exit (x=874..936)
px_box(px, W, H, 878, 258, 54, 26, [rgb("#6b3222"), rgb("#9a4a32"), rgb("#c26444")], vertical=True, border=OUTLINE)
px_box(px, W, H, 876, 253, 58, 6, [rgb("#78716c"), rgb("#a8a29e"), rgb("#d6d3d1")], vertical=True, border=OUTLINE)
px_box(px, W, H, 900, 214, 12, 40, [rgb("#14532d"), rgb("#15803d"), rgb("#22c55e"), rgb("#4ade80")], vertical=False)
px_box(px, W, H, 890, 226, 12, 8,  [rgb("#14532d"), rgb("#22c55e")], vertical=True)
px_box(px, W, H, 890, 218, 7,  12, [rgb("#14532d"), rgb("#22c55e"), rgb("#4ade80")], vertical=False)
px_box(px, W, H, 910, 230, 11, 7,  [rgb("#14532d"), rgb("#22c55e")], vertical=True)
px_box(px, W, H, 915, 222, 7,  12, [rgb("#14532d"), rgb("#22c55e"), rgb("#4ade80")], vertical=False)

# ORGANIC DIAGONAL BRIDGE SHADOW across the street at Seam 1 (matching Zone 1's exact shadow luminance!)
# In Zone 1, the shadow starts under the bridge and fills x=760..800 at dark intensity ~0.44, then slopes down-right out to x=965!
for y in range(282, 450):
    sh_end = int(858 + (y - 282) * 0.54)
    for x in range(772, min(W, sh_end + 14)):
        # Do NOT double-darken x<800 where Zone 1 already has its shadow; smoothly bring shadow strength up from x=772..800!
        fade_in = max(0.0, min(1.0, (x - 772) / 28.0))
        if x < sh_end:
            a = 0.44 * fade_in
        else:
            t = 1.0 - (x - sh_end) / 14.0
            a = (0.44 * fade_in * t) if (t > (BAYER2[y & 1][x & 1] + 0.5) / 4.0) else 0.0
        if a > 0:
            px[x, y] = lerp(px[x, y], rgb("#1e2130"), a)

# 5. ZONE 2 (x = 942 .. 1575): PARQUE BENITO JUÁREZ + ABARROTES PANTERA (32-BIT PIXEL ART!)
# 5a. Parque Benito Juárez lush grass terrace & brick-and-iron fence (x=944..1310)
px_box(px, W, H, 944, 248, 366, 36, [rgb("#14532d"), rgb("#166534"), rgb("#22c55e"), rgb("#4ade80")], vertical=True, border=OUTLINE)
# Low terracotta brick park wall + stone coping + wrought iron fence bars
px_box(px, W, H, 944, 260, 366, 24, [rgb("#6b2b1a"), rgb("#9a4228"), rgb("#c25b3a")], vertical=True, border=OUTLINE)
px_box(px, W, H, 942, 256, 370, 6, [rgb("#78716c"), rgb("#a8a29e"), rgb("#e7e5e4")], vertical=True, border=OUTLINE)
for fx in range(954, 1304, 12):
    for y in range(214, 256):
        px[fx, y] = rgb("#1e293b")
        px[fx + 1, y] = rgb("#475569")
    px[fx, 212] = rgb("#f5b700"); px[fx + 1, 212] = rgb("#f5b700")
px_box(px, W, H, 944, 218, 366, 4, [rgb("#1e293b"), rgb("#475569")], vertical=True, border=OUTLINE)
# Brick park gate pillars
for gx in (944, 1118, 1296):
    px_box(px, W, H, gx, 206, 16, 78, [rgb("#5c2416"), rgb("#8c3923"), rgb("#b85234")], vertical=False, border=OUTLINE)
    px_box(px, W, H, gx - 2, 202, 20, 6, [rgb("#94a3b8"), rgb("#e2e8f0")], vertical=True, border=OUTLINE)

# Shaded CETis/Benito Juárez Park Kiosk / Pergola (x=1150..1280)
px_box(px, W, H, 1152, 244, 126, 14, [rgb("#57534e"), rgb("#a8a29e"), rgb("#e7e5e4")], vertical=True)
for kx in (1162, 1208, 1258):
    px_box(px, W, H, kx, 174, 12, 72, [rgb("#a89a82"), rgb("#d6c7ad"), rgb("#f5ead6")], vertical=False)
# Guinda & gold pitched pagoda roof
px_box(px, W, H, 1144, 160, 142, 18, [rgb("#4c0d1f"), rgb("#7a1c33"), rgb("#9c2645")], vertical=True)
px_box(px, W, H, 1156, 148, 118, 14, [rgb("#5c1126"), rgb("#8a203c"), rgb("#b02d4f")], vertical=True)
px_box(px, W, H, 1144, 174, 142, 4, [rgb("#b45309"), rgb("#f5b700"), rgb("#fef08a")], vertical=True, border=None)

# Lush 32-bit palms & shade trees inside Parque Benito Juárez!
draw_palm(px, W, H, 992, 256, 124, lean=-14)
draw_shade_tree(px, W, H, 1068, 256, r=30)
draw_palm(px, W, H, 1278, 256, 116, lean=12)

# 5b. ABARROTES PANTERA — Rich 32-Bit Mexican Corner Store (x=1326..1566, matches gr3 at x=1460!)
# Warm cream stucco wall with shaded right edge & teal dado
px_box(px, W, H, 1326, 134, 240, 150, [rgb("#c9ae7d"), rgb("#e2ca9b"), rgb("#f4e2bc")], vertical=False, border=OUTLINE)
# Guinda cornice parapet + gold molding
px_box(px, W, H, 1322, 122, 248, 16, [rgb("#4c0d1f"), rgb("#7a1c33"), rgb("#9c2645")], vertical=True, border=OUTLINE)
px_box(px, W, H, 1326, 137, 240, 4, [rgb("#b45309"), rgb("#f5b700"), rgb("#fef08a")], vertical=True, border=None)
# Teal painted bottom wall stripe (classic Sonora abarrotes!)
px_box(px, W, H, 1328, 232, 236, 51, [rgb("#0e4f5c"), rgb("#156d7d"), rgb("#1d8ca0")], vertical=True, border=None)
# Store Signboard ("ABARROTES PANTERA" plaque)
px_box(px, W, H, 1346, 146, 198, 26, [rgb("#4c0d1f"), rgb("#7a1c33"), rgb("#9c2645")], vertical=True, border=rgb("#f5b700"))
# Striped Red & Cream Scalloped Cloth Awning casting a real drop shadow!
for i in range(10):
    ax = 1336 + i * 22
    aw_ramp = [rgb("#991b1b"), rgb("#dc2626"), rgb("#ef4444")] if i % 2 == 0 else [rgb("#cbd5e1"), rgb("#f1f5f9"), rgb("#ffffff")]
    px_box(px, W, H, ax, 178, 23, 20, aw_ramp, vertical=True, border=OUTLINE)
# Drop shadow cast under awning
for y in range(198, 208):
    for x in range(1338, 1554):
        px[x, y] = lerp(px[x, y], OUTLINE, 0.35)
# Ribbed Metallic Rolling Door Shutter (left side of store)
px_box(px, W, H, 1344, 206, 56, 78, [rgb("#334155"), rgb("#475569"), rgb("#64748b")], vertical=False, border=OUTLINE)
for ry in range(214, 280, 7):
    for x in range(1346, 1398):
        px[x, ry] = rgb("#1e293b")
        px[x, ry + 1] = rgb("#94a3b8")
# Glowing Glass Shop Window with pixel snack shelves inside!
px_box(px, W, H, 1412, 208, 66, 46, [rgb("#0369a1"), rgb("#0ea5e9"), rgb("#7dd3fc"), rgb("#bae6fd")], vertical=True, border=OUTLINE)
# Shelves & colorful pixel products inside window
for sy, cols in [(226, ["#ef4444","#facc15","#22c55e","#3b82f6"]), (240, ["#f97316","#ec4899","#eab308","#38bdf8"])]:
    for x in range(1415, 1475): px[x, sy] = rgb("#1e3a8a")
    for idx, sc in enumerate(cols):
        px_box(px, W, H, 1418 + idx * 14, sy - 9, 10, 9, [lerp(rgb(sc), OUTLINE, 0.3), rgb(sc)], vertical=True, border=OUTLINE)
# Diagonal glass reflection streak
for i in range(18):
    px[1420 + i, 212 + i] = rgb("#ffffff")
    px[1421 + i, 212 + i] = rgb("#e0f2fe")
# Clean plaster side wall on right of store (x=1484..1560 -> where gr3 graffiti sits!)
px_box(px, W, H, 1492, 208, 56, 20, [rgb("#b45309"), rgb("#f59e0b"), rgb("#fde047")], vertical=True, border=OUTLINE)

# Wooden Utility Pole at x=1380 (matches exact collision box x1=1374..1392 in getStageConfig!)
px_box(px, W, H, 1378, 86, 12, 198, [rgb("#3b2314"), rgb("#613c24"), rgb("#855638"), rgb("#a6704e")], vertical=False, border=OUTLINE)
px_box(px, W, H, 1362, 102, 44, 7, [rgb("#3b2314"), rgb("#784c30")], vertical=True, border=OUTLINE)
# Transformer drum on pole
px_box(px, W, H, 1388, 114, 14, 20, [rgb("#334155"), rgb("#64748b"), rgb("#94a3b8")], vertical=False, border=OUTLINE)

# 6. ORGANIC SEAM 2 (x = 1566 .. 1765): ALLEY WALL + SLOPED OVERPASS APPROACH INTO ZONE 3 SUNSET!
#    NO hard vertical wall at x=1600!
#    Weathered Sonora cinderblock wall (x=1566..1690) with sunset glow above + palm silhouette + rusted fence!
px_box(px, W, H, 1566, 204, 132, 80, [rgb("#5c4a54"), rgb("#7d646b"), rgb("#a38382")], vertical=True, border=OUTLINE)
# Brick course lines & top coping
for by in range(218, 280, 12):
    for x in range(1568, 1696): px[x, by] = rgb("#423540")
px_box(px, W, H, 1564, 198, 136, 7, [rgb("#4a3c47"), rgb("#8c7378"), rgb("#c4a7a3")], vertical=True, border=OUTLINE)
# Warm sunset palm behind alley wall
draw_palm(px, W, H, 1624, 202, 84, lean=-10, tint_warm=0.85)

# Angled Concrete Overpass Approach Entrance (slopes smoothly down-left to x=1655, full deck starts x=1735..2400!)
for x in range(1640, W):
    if x < 1740:
        t = (x - 1640) / 100.0
        deck_top = int(0)
        deck_bot = int(112 * t)
        fascia_h = 26
    else:
        deck_top = 0
        deck_bot = 112
        fascia_h = 28
    # Upper concrete bridge fascia (warm sunset lit on left face!)
    for y in range(deck_top, min(H, deck_bot)):
        if y == deck_bot - 1 or (x == 1640):
            px[x, y] = OUTLINE
        elif y < deck_bot - fascia_h:
            # Concrete roadway side wall with sunset purple-amber tint
            ty = y / max(1, deck_bot - fascia_h)
            px[x, y] = lerp(rgb("#5e4a69"), rgb("#3c304a"), ty)
        else:
            # Beveled underside girder shadow + recessed rib beams every 44px!
            rib = (x % 44) < 8
            ty = (y - (deck_bot - fascia_h)) / max(1, fascia_h)
            c_rib = rgb("#211a2e") if rib else rgb("#302642")
            px[x, y] = lerp(c_rib, rgb("#181224"), ty)

# 7. ZONE 3 (x = 1720 .. 2400): GUARIDA BAJO EL PUENTE — SUNSET BOSS ARENA!
# Back shaded retaining wall beneath the bridge (leaves open sunset sky arches between y=112..172!)
px_box(px, W, H, 1694, 184, 706, 100, [rgb("#30283d"), rgb("#453a54"), rgb("#5c4e6b")], vertical=True, border=OUTLINE)
# Retaining wall vertical expansion joints
for rx in range(1740, 2390, 64):
    for y in range(186, 282):
        px[rx, y] = rgb("#241d30")
        px[rx + 1, y] = rgb("#6c5d7d")

# Concrete Arches connecting the 3 collision pillars (x=1836, 2076, 2344) cleanly to the overpass deck!
pillar_xs = [1836, 2076, 2344]
for cx_p in pillar_xs:
    # Massive 32-bit shaded concrete pillar (width 46px, exact match to collision boxes!)
    px_box(px, W, H, cx_p - 2, 110, 46, 175, [rgb("#262033"), rgb("#413852"), rgb("#635678"), rgb("#917f9e"), rgb("#d19a7e")], vertical=False, border=OUTLINE)
    # Pillar capital & base plinth
    px_box(px, W, H, cx_p - 8, 104, 58, 14, [rgb("#2a2238"), rgb("#544866"), rgb("#877594")], vertical=True, border=OUTLINE)
    px_box(px, W, H, cx_p - 5, 268, 52, 17, [rgb("#221c2e"), rgb("#483e59"), rgb("#6f6282")], vertical=True, border=OUTLINE)

# Authentic 32-bit Pixel Graffiti Mural on Zone 3 retaining wall (left bay x=1895..2050)
px_box(px, W, H, 1906, 204, 134, 58, [rgb("#3b1d5e"), rgb("#6d28d9"), rgb("#9333ea")], vertical=True, border=OUTLINE)
px_box(px, W, H, 1916, 214, 56, 26, [rgb("#be185d"), rgb("#ec4899"), rgb("#f472b6")], vertical=True, border=OUTLINE)
px_box(px, W, H, 1978, 218, 52, 28, [rgb("#0e7490"), rgb("#06b6d4"), rgb("#67e8f9")], vertical=True, border=OUTLINE)
px_box(px, W, H, 1940, 236, 68, 20, [rgb("#b45309"), rgb("#f59e0b"), rgb("#fde047")], vertical=True, border=OUTLINE)

# Glowing 32-Bit Rusted Oil-Drum Fire Barrel beside pillar 2 (x=2025, y=282) casting warm firelight!
fx_b, fy_b = 2026, 244
# Warm Bayer-dithered orange firelight bloom on surrounding wall & pillar!
for y in range(192, 315):
    for x in range(1970, 2090):
        d = math.hypot((x - (fx_b + 12)) / 56.0, (y - (fy_b - 6)) / 58.0)
        if d < 1.0 and (d < 0.45 or BAYER2[y & 1][x & 1] < 2):
            px[x, y] = lerp(px[x, y], rgb("#fb923c"), (1.0 - d) * 0.34)
# Shaded steel barrel with horizontal ribs
px_box(px, W, H, fx_b, fy_b, 26, 39, [rgb("#3b1a14"), rgb("#6e2c1b"), rgb("#9a3d22"), rgb("#c25b32")], vertical=False, border=OUTLINE)
for ry in (fy_b + 12, fy_b + 26):
    px_box(px, W, H, fx_b - 1, ry, 28, 3, [rgb("#27120e"), rgb("#7c2d12")], vertical=True, border=None)
# Pixel flames dancing above barrel
for dx, fh, col in [(4, 16, "#ea580c"), (8, 24, "#f97316"), (12, 28, "#facc15"), (16, 22, "#f97316"), (19, 14, "#ea580c")]:
    px_box(px, W, H, fx_b + dx, fy_b - fh + 2, 5, fh, [rgb(col), rgb("#fef08a")], vertical=True, border=None)

# ORGANIC DIAGONAL SHADOW ENTRY into Zone 3 Underpass (x=1610..1770) — zero hard vertical seam!
for y in range(282, 450):
    sh_start = int(1660 - (y - 282) * 0.32)
    for x in range(max(1580, sh_start - 20), W):
        if x >= sh_start + 16:
            a = 0.24
        elif x >= sh_start:
            t = (x - sh_start) / 16.0
            a = 0.24 * t if (t > (BAYER2[y & 1][x & 1] + 0.5) / 4.0) else 0.0
        else:
            a = 0.0
        if a > 0:
            px[x, y] = lerp(px[x, y], rgb("#161126"), a)

# 8. CONTINUOUS OVERHEAD POWER LINES spanning Zone 1 -> Zone 2 -> Zone 3 seamlessly!
wire_anchors = [(825, 84), (1382, 102), (1685, 76)]
for w_idx in range(len(wire_anchors) - 1):
    x1, y1 = wire_anchors[w_idx]
    x2, y2 = wire_anchors[w_idx + 1]
    for offset_y in (0, 8):
        for x in range(x1, x2 + 1):
            t = (x - x1) / max(1, x2 - x1)
            sag = math.sin(t * math.pi) * 20
            yy = int(y1 + (y2 - y1) * t + sag + offset_y)
            if 0 <= x < W and 0 <= yy < H:
                px[x, yy] = (24, 20, 32)
                if yy + 1 < H:
                    px[x, yy + 1] = lerp(px[x, yy + 1], (24, 20, 32), 0.45)

# Crisp pixel text signs using ImageDraw (ABARROTES PANTERA)
dr = ImageDraw.Draw(pano)
dr.text((1378, 154), "ABARROTES PANTERA", fill=rgb("#fde047"))

# Save full QA preview + zoomed seams + 3 sliced 800x450 JPEG tiles!
pano.resize((1500, 281), Image.NEAREST).save("/tmp/pano_v2_full.png")
pano.crop((600, 0, 1000, 450)).save("/tmp/seam1_v2.png")
pano.crop((1400, 0, 1800, 450)).save("/tmp/seam2_v2.png")

tiles = {}
for idx, key in enumerate(("explore", "explore2", "explore3")):
    tile = pano.crop((idx * 800, 0, (idx + 1) * 800, 450))
    out_path = os.path.join(OUT_DIR, f"{key}.jpg")
    tile.save(out_path, "JPEG", quality=86, optimize=True)
    buf = io.BytesIO()
    tile.save(buf, "JPEG", quality=86, optimize=True)
    tiles[key] = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    print(f"  {key:10s}: {len(buf.getvalue())/1024:.1f} KB")

# Save JSON bundle for embedding
open(os.path.join(OUT_DIR, "explore_tiles.json"), "w").write(json.dumps(tiles))
print("Seamless 2400x450 32-bit panorama generated cleanly!")

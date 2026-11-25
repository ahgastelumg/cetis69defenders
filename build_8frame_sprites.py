import os, json, math, base64, io
from collections import deque
from PIL import Image, ImageDraw, ImageEnhance

ART_DIR = '/home/antigravity/.gemini/jetski/brain/v1/default/jetski_remote_agents_3p_devbox/3371c7b6-b155-400e-8450-f6de6eda02e9'
SPR_DIR = '/home/antigravity/cetis69-defenders/sprites'
OUTLINE = (21, 20, 28, 255)


def flood_remove_bg(img, tol=36, clear_enclosed_bg=True, crop_bbox=False):
    """Flood-fill remove studio background + soft ground shadow + enclosed leg-gap bg."""
    rgba = img.convert('RGBA')
    w, h = rgba.size
    px = rgba.load()
    corners = [px[2, 2], px[w-3, 2], px[2, h-3], px[w-3, h-3]]
    bg_r = sum(c[0] for c in corners) // 4
    bg_g = sum(c[1] for c in corners) // 4
    bg_b = sum(c[2] for c in corners) // 4

    visited = [[False]*w for _ in range(h)]
    q = deque()
    for x in range(w):
        q.append((x, 0)); q.append((x, h-1))
    for y in range(h):
        q.append((0, y)); q.append((w-1, y))

    def is_bg(r, g, b):
        return abs(r - bg_r) <= tol and abs(g - bg_g) <= tol and abs(b - bg_b) <= tol

    while q:
        x, y = q.popleft()
        if x < 0 or x >= w or y < 0 or y >= h or visited[y][x]:
            continue
        r, g, b, a = px[x, y]
        if is_bg(r, g, b):
            visited[y][x] = True
            px[x, y] = (0, 0, 0, 0)
            q.append((x+1, y)); q.append((x-1, y)); q.append((x, y+1)); q.append((x, y-1))

    # Detect ground shadow baseline before stripping it (useful for uniform ground alignment)
    shadow_start = int(h * 0.76)
    shadow_ys = []
    for y in range(shadow_start, h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a == 0:
                continue
            sat = max(r, g, b) - min(r, g, b)
            lum = (r + g + b) / 3
            if 95 <= lum <= 174 and sat <= 32 and b >= r - 6:
                shadow_ys.append(y)
                px[x, y] = (0, 0, 0, 0)

    if clear_enclosed_bg:
        q2 = deque()
        vis2 = [[False]*w for _ in range(h)]
        for y in range(h):
            for x in range(w):
                if px[x, y][3] == 0:
                    vis2[y][x] = True
                    for nx, ny in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
                        if 0 <= nx < w and 0 <= ny < h and px[nx, ny][3] > 0:
                            q2.append((nx, ny))
        while q2:
            x, y = q2.popleft()
            if vis2[y][x]:
                continue
            r, g, b, a = px[x, y]
            if is_bg(r, g, b):
                vis2[y][x] = True
                px[x, y] = (0, 0, 0, 0)
                for nx, ny in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
                    if 0 <= nx < w and 0 <= ny < h and not vis2[ny][nx]:
                        q2.append((nx, ny))

    for y in range(1, h-1):
        for x in range(1, w-1):
            r, g, b, a = px[x, y]
            if a > 0 and is_bg(r, g, b):
                if (px[x-1, y][3] == 0 or px[x+1, y][3] == 0 or
                    px[x, y-1][3] == 0 or px[x, y+1][3] == 0):
                    px[x, y] = (0, 0, 0, 0)

    if crop_bbox:
        bb = rgba.getbbox()
        if bb:
            rgba = rgba.crop(bb)
    return rgba, (sum(shadow_ys)/len(shadow_ys) if shadow_ys else None)


def row_center_x(img, y_start, y_end):
    w, h = img.size
    px = img.load()
    xs = []
    for y in range(max(0, y_start), min(h, y_end)):
        for x in range(w):
            if px[x, y][3] > 128:
                xs.append(x)
    return (sum(xs) / len(xs)) if xs else (w / 2.0)


def resize_to_height(img, target_h=88):
    w, h = img.size
    if h == 0:
        return img
    new_w = max(1, round(w * (target_h / h)))
    return img.resize((new_w, target_h), Image.NEAREST)


def scale_nearest(im, sx, sy):
    return im.resize((max(4, round(im.size[0] * sx)), max(4, round(im.size[1] * sy))), Image.NEAREST)


def shear_x_nearest(img, factor):
    w, h = img.size
    pad = int(abs(factor) * h) + 6
    src = Image.new('RGBA', (w + pad*2, h), (0, 0, 0, 0))
    src.paste(img, (pad, 0), img)
    sw, sh = src.size
    shift = -factor * (sh / 2.0)
    return src.transform((sw, sh), Image.Transform.AFFINE, (1, factor, shift, 0, 1, 0), resample=Image.NEAREST)


def to_b64_png(img, colors=48):
    rgba = img.convert('RGBA')
    q = rgba.quantize(colors=colors, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE)
    buf = io.BytesIO()
    q.save(buf, format='PNG', optimize=True)
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')


def extract_uniform_8sheet(sheet_path, target_ref_h=86, canvas_w=92, canvas_h=96, preserve_air_lift=False):
    """
    Extract a 4x2 sprite sheet with ONE UNIFORM SCALE across all 8 frames!
    - Preserves exact head & body proportions (zero head inflating/shrinking!).
    - Locks horizontal alignment to head/upper-torso center X (zero horizontal jitter!).
    - Preserves natural vertical bob relative to the row's ground baseline.
    """
    sheet = Image.open(sheet_path)
    sw, sh = sheet.size
    cw, ch = sw // 4, sh // 2
    raw = []
    for row in range(2):
        for col in range(4):
            pad = 8
            cell = sheet.crop((col*cw + pad, row*ch + pad, (col+1)*cw - pad, (row+1)*ch - pad))
            clean, shadow_y = flood_remove_bg(cell, tol=36, clear_enclosed_bg=True, crop_bbox=False)
            bb = clean.getbbox()
            raw.append((clean, bb, shadow_y))

    # Uniform scale computed from median character height across all 8 cells
    heights = sorted((bb[3] - bb[1]) for _, bb, _ in raw if bb)
    ref_h = heights[len(heights) // 2]
    scale = target_ref_h / float(ref_h)

    # For walk cycles, compute ground baseline per row from the lowest foot Y (or shadow Y)
    frames = []
    center_x = canvas_w // 2
    foot_y = canvas_h - 3

    for idx, (clean, bb, shadow_y) in enumerate(raw):
        if not bb:
            frames.append(Image.new('RGBA', (canvas_w, canvas_h), (0, 0, 0, 0)))
            continue
        cropped = clean.crop(bb)
        nw = max(4, round(cropped.width * scale))
        nh = max(4, round(cropped.height * scale))
        scaled = cropped.resize((nw, nh), Image.NEAREST)

        # Lock horizontally to the HEAD/TORSO center (top 36% of character) so head stays rock-steady!
        head_cx = row_center_x(scaled, 0, max(12, int(nh * 0.36)))
        px = round(center_x - head_cx)

        if preserve_air_lift and shadow_y is not None:
            # Grounded on foot_y, preserving small natural lift relative to shadow
            lift = max(0, round((shadow_y - bb[3]) * scale))
            lift = min(lift, 12)
            py = foot_y - nh - lift
        else:
            # Subtle natural run bob: frames 1,5 (down) +2px, frames 2,6 (passing) -2px, frames 3,7 (push-off) -3px
            bob_map = [0, 2, -2, -3, 0, 2, -2, -3]
            py = foot_y - nh + bob_map[idx]

        # Clamp within canvas cleanly
        py = max(1, min(canvas_h - nh, py))
        px = max(1, min(canvas_w - nw - 1, px))
        c = Image.new('RGBA', (canvas_w, canvas_h), (0, 0, 0, 0))
        c.paste(scaled, (px, py), scaled)
        frames.append(c)
    return frames


def darken_sprite(im, factor=0.82):
    """Darken RGB channels while keeping alpha intact (classic 16-bit rear-leg depth shading)."""
    rgba = im.convert('RGBA')
    r, g, b, a = rgba.split()
    rgb = Image.merge('RGB', (r, g, b))
    rgb = ImageEnhance.Brightness(rgb).enhance(factor)
    r2, g2, b2 = rgb.split()
    return Image.merge('RGBA', (r2, g2, b2, a))


def rotate_about_pivot(im, angle_deg, pivot_x, pivot_y):
    """Rotate sprite around (pivot_x, pivot_y) using nearest-neighbor and return (rotated_img, new_pivot_x, new_pivot_y)."""
    w, h = im.size
    rad = math.radians(angle_deg)
    # Pad image generously so nothing clips
    pad = max(w, h) + 12
    big = Image.new('RGBA', (w + pad*2, h + pad*2), (0, 0, 0, 0))
    big.paste(im, (pad, pad), im)
    cx = pad + pivot_x
    cy = pad + pivot_y
    # PIL rotate rotates CCW around center; negate angle so +deg swings leg forward (right)
    rot = big.rotate(angle_deg, resample=Image.NEAREST, center=(cx, cy))
    bb = rot.getbbox()
    if not bb:
        return im, pivot_x, pivot_y
    cropped = rot.crop(bb)
    return cropped, cx - bb[0], cy - bb[1]


def build_jointed_leg(leg_im, hip_angle_deg, knee_bend_deg=0):
    """
    Two-segment articulated pixel-art leg:
      - Upper thigh rotates by hip_angle_deg around hip pivot (top center)
      - Lower shin+shoe rotates by hip_angle_deg + knee_bend_deg around the knee joint!
    Returns (leg_canvas, hip_px, hip_py, lowest_y).
    """
    w, h = leg_im.size
    knee_y = max(3, int(h * 0.48))
    thigh = leg_im.crop((0, 0, w, min(h, knee_y + 3)))
    shin  = leg_im.crop((0, max(0, knee_y - 1), w, h))

    t_piv_x = row_center_x(thigh, 0, min(6, thigh.height))
    t_piv_y = 2.0
    knee_cx = row_center_x(thigh, max(0, thigh.height - 5), thigh.height)
    knee_dy = knee_y - t_piv_y
    knee_dx = knee_cx - t_piv_x

    # Rotate thigh around hip
    r_thigh, r_hip_x, r_hip_y = rotate_about_pivot(thigh, hip_angle_deg, t_piv_x, t_piv_y)

    # Compute rotated knee position relative to hip
    rad = math.radians(hip_angle_deg)
    # Since +deg swings forward (+x for downward vector (0, +y)): x' = x*cos + y*sin, y' = -x*sin + y*cos
    rk_dx = knee_dx * math.cos(rad) + knee_dy * math.sin(rad)
    rk_dy = -knee_dx * math.sin(rad) + knee_dy * math.cos(rad)

    # Rotate shin around its top knee pivot
    s_piv_x = row_center_x(shin, 0, min(5, shin.height))
    s_piv_y = 2.0
    r_shin, rs_kx, rs_ky = rotate_about_pivot(shin, hip_angle_deg + knee_bend_deg, s_piv_x, s_piv_y)

    # Composite thigh + shin on a temporary canvas
    cw, ch = 96, 96
    c = Image.new('RGBA', (cw, ch), (0, 0, 0, 0))
    hx, hy = 48, 24
    # Paste shin first, then thigh slightly overlapping the knee joint
    sx = round(hx + rk_dx - rs_kx)
    sy = round(hy + rk_dy - rs_ky)
    c.paste(r_shin, (sx, sy), r_shin)
    tx = round(hx - r_hip_x)
    ty = round(hy - r_hip_y)
    c.paste(r_thigh, (tx, ty), r_thigh)

    bb = c.getbbox()
    if not bb:
        return leg_im, w/2, 2, h
    out = c.crop(bb)
    return out, hx - bb[0], hy - bb[1], out.height


def extract_clean_leg(im, hip_y, side='right', x_clip=None):
    """
    Extract ONE clean individual leg below hip_y from a character sprite.
    side='right' takes the front/right leg (facing right), side='left' takes the rear/left leg.
    """
    w, h = im.size
    x0, x1 = x_clip if x_clip else (0, w)
    lower = im.crop((x0, hip_y, x1, h))
    lw, lh = lower.size
    px = lower.load()

    # Find the horizontal split between the two legs in the bottom 55% (shoes/shins gap)
    col_counts = [sum(1 for y in range(int(lh*0.35), lh) if px[x, y][3] > 128) for x in range(lw)]
    opaque_cols = [x for x, c in enumerate(col_counts) if c > 0]
    if not opaque_cols:
        return lower
    min_x, max_x = opaque_cols[0], opaque_cols[-1]
    mid_start = min_x + int((max_x - min_x) * 0.28)
    mid_end   = min_x + int((max_x - min_x) * 0.72)
    split_x = min(range(mid_start, max(mid_start+1, mid_end)), key=lambda x: col_counts[x])

    leg = Image.new('RGBA', (lw, lh), (0, 0, 0, 0))
    lpx = leg.load()
    for y in range(lh):
        for x in range(lw):
            if px[x, y][3] <= 128:
                continue
            if side == 'right' and x >= split_x:
                lpx[x, y] = px[x, y]
            elif side == 'left' and x <= split_x:
                lpx[x, y] = px[x, y]

    # Straighten resting stance angle of the extracted leg so 0° is clean vertical!
    bb = leg.getbbox()
    if not bb:
        return lower
    leg = leg.crop(bb)
    top_cx = row_center_x(leg, 0, min(6, leg.height))
    # Exclude toe tip from bottom center by measuring ankle region (70%..88% height)
    bot_cx = row_center_x(leg, int(leg.height * 0.68), int(leg.height * 0.90))
    tilt_deg = math.degrees(math.atan2(bot_cx - top_cx, max(8, leg.height * 0.72)))
    if abs(tilt_deg) > 3:
        leg, _, _ = rotate_about_pivot(leg, -tilt_deg * 0.85, top_cx, 2)
    return leg


def build_pivoted_8frame_walk(upper_imgs, leg_src_img, hip_ratio=0.65, target_h=88,
                              canvas_w=92, canvas_h=96, stride_deg=26,
                              leg_side='right', x_clip=None, keep_chain_mask=False,
                              upper_hip_overlap=4, hip_spread=3):
    """
    Smooth, natural, arcade-grade 8-frame walk cycle with:
      - Rock-steady constant-size head & upper torso (zero pogo-stick shrinking!)
      - True 2-leg alternating hip + knee articulation (back leg darkened 16% for depth)
      - Subtle, natural 4px Animator's Survival Kit walk bob (+1, +2, 0, -2)
      - Gentle arm-swing alternation across upper_imgs
    """
    # Normalize upper source poses to exact same height
    u_scaled = [resize_to_height(u.convert('RGBA'), target_h) for u in upper_imgs]
    l_scaled = resize_to_height(leg_src_img.convert('RGBA'), target_h)

    hip_y = int(target_h * hip_ratio)

    # Extract upper bodies (keep chain below hip_y for Boss if keep_chain_mask=True!)
    uppers = []
    for im in u_scaled:
        w, h = im.size
        cut_y = min(h, hip_y + upper_hip_overlap)
        if keep_chain_mask and x_clip:
            # Keep everything ABOVE cut_y, PLUS anything outside x_clip (the boss's hanging chain!)
            u = im.copy()
            px = u.load()
            cx0, cx1 = x_clip
            for y in range(cut_y, h):
                for x in range(max(0, cx0), min(w, cx1)):
                    px[x, y] = (0, 0, 0, 0)
            uppers.append(u)
        else:
            uppers.append(im.crop((0, 0, w, cut_y)))

    # Extract ONE clean leg (front) and create depth-shaded back leg
    front_leg_base = extract_clean_leg(l_scaled, max(0, hip_y - 2), side=leg_side, x_clip=x_clip)
    back_leg_base  = darken_sprite(front_leg_base, 0.80)

    def clipped_waist_cx(im):
        w, h = im.size
        px = im.load()
        cx0, cx1 = x_clip if x_clip else (0, w)
        xs = []
        for y in range(max(0, hip_y - 10), min(h, hip_y + 2)):
            for x in range(max(0, cx0), min(w, cx1)):
                if px[x, y][3] > 128:
                    xs.append(x)
        return (sum(xs) / len(xs)) if xs else (w / 2.0)

    center_x = canvas_w // 2
    foot_y = canvas_h - 3
    leg_len = front_leg_base.height

    # Classic 8-phase walk cycle (Animator's Survival Kit):
    # +hip = leg swings forward, -hip = leg swings backward, -knee = shin bends naturally backward!
    # Also note: lean_deg < 0 tilts upper body slightly FORWARD (right) since PIL +deg is CCW (top goes left)!
    A = stride_deg
    phases = [
        ( +A*0.95,  -4,  -A*0.85, -14,  1, 0, -2.5),  # 0: Contact R forward, L back
        ( +A*0.50, -10,  -A*0.90, -24,  2, 0, -3.5),  # 1: Down / weight absorption
        (  0.0,      0,  +A*0.08, -36,  0, 1, -1.5),  # 2: Passing (R straight stance, L knee bent swinging forward!)
        ( -A*0.52,  -6,  +A*0.72, -18, -2, 1, -0.5),  # 3: Push-off R, L extending forward
        ( -A*0.85, -14,  +A*0.95,  -4,  1, 2, -2.5),  # 4: Contact L forward, R back
        ( -A*0.90, -24,  +A*0.50, -10,  2, 2, -3.5),  # 5: Down / weight absorption
        ( +A*0.08, -36,   0.0,      0,  0, 1, -1.5),  # 6: Passing (L straight stance, R knee bent swinging forward!)
        ( +A*0.72, -18,  -A*0.52,  -6, -2, 1, -0.5),  # 7: Push-off L, R extending forward
    ]

    frames = []
    hip_y_base = foot_y - leg_len + 3  # grounded hip socket height

    for f_ang, f_knee, b_ang, b_knee, bob_y, u_idx, lean_deg in phases:
        canvas = Image.new('RGBA', (canvas_w, canvas_h), (0, 0, 0, 0))
        hy = hip_y_base + bob_y

        # Build back leg & front leg around hip socket
        b_leg, bhx, bhy, _ = build_jointed_leg(back_leg_base, b_ang, b_knee)
        f_leg, fhx, fhy, _ = build_jointed_leg(front_leg_base, f_ang, f_knee)

        # Back hip sits slightly behind (-3px), front hip slightly forward (+2px)
        canvas.paste(b_leg, (round(center_x - hip_spread - bhx), round(hy - bhy)), b_leg)
        canvas.paste(f_leg, (round(center_x + hip_spread - fhx), round(hy - fhy)), f_leg)

        # Upper body with subtle natural forward walk lean & zero scale distortion
        u_im = uppers[u_idx % len(uppers)]
        u_piv_x = clipped_waist_cx(u_im)
        if abs(lean_deg) > 0.4:
            u_rot, urx, ury = rotate_about_pivot(u_im, lean_deg, u_piv_x, hip_y)
            ux = round(center_x - urx)
            uy = round(hy - ury + 2)
            canvas.paste(u_rot, (ux, uy), u_rot)
        else:
            ux = round(center_x - u_piv_x)
            uy = round(hy - hip_y + 2)
            canvas.paste(u_im, (ux, uy), u_im)

        frames.append(canvas)
    return frames


def draw_pixel_swoosh(canvas, x0, y0, radius_x, radius_y, color_main, color_hi, phase='peak', has_builtin_fx=False):
    d = ImageDraw.Draw(canvas)
    if phase == 'charge':
        for dx, dy in [(-4,0),(4,0),(0,-4),(0,4),(-2,-2),(2,2),(-2,2),(2,-2)]:
            d.rectangle([x0+dx-1, y0+dy-1, x0+dx+1, y0+dy+1], fill=color_hi)
        d.rectangle([x0-2, y0-2, x0+2, y0+2], fill=(255, 255, 255, 255))
    elif phase == 'start':
        for i in range(3):
            yy = y0 - 12 + i * 11
            d.rectangle([x0 - 16, yy, x0 + 4, yy + 2], fill=color_hi)
            d.rectangle([x0 - 10, yy + 2, x0 + 8, yy + 3], fill=color_main)
    elif phase == 'peak':
        if not has_builtin_fx:
            pts_o, pts_i = [], []
            for deg in range(-72, 76, 12):
                rad = math.radians(deg)
                pts_o.append((int(x0 + math.cos(rad)*radius_x), int(y0 + math.sin(rad)*radius_y)))
                pts_i.append((int(x0 + math.cos(rad)*(radius_x-9)), int(y0 + math.sin(rad)*(radius_y-6))))
            poly = pts_o + list(reversed(pts_i))
            if len(poly) >= 3:
                d.polygon(poly, fill=color_main, outline=OUTLINE)
            pts_ho, pts_hi = [], []
            for deg in range(-55, 58, 14):
                rad = math.radians(deg)
                pts_ho.append((int(x0 + math.cos(rad)*(radius_x-2)), int(y0 + math.sin(rad)*(radius_y-2))))
                pts_hi.append((int(x0 + math.cos(rad)*(radius_x-5)), int(y0 + math.sin(rad)*(radius_y-4))))
            poly2 = pts_ho + list(reversed(pts_hi))
            if len(poly2) >= 3:
                d.polygon(poly2, fill=color_hi)
        sx, sy = int(x0 + (radius_x if not has_builtin_fx else 14)), y0
        d.rectangle([sx-7, sy-1, sx+7, sy+1], fill=(255,255,255,255))
        d.rectangle([sx-1, sy-7, sx+1, sy+7], fill=(255,255,255,255))
        d.rectangle([sx-3, sy-3, sx+3, sy+3], fill=color_hi)
    elif phase == 'follow':
        for deg in range(-48, 72, 18):
            rad = math.radians(deg)
            px = int(x0 + math.cos(rad) * (radius_x + 2))
            py = int(y0 + math.sin(rad) * (radius_y + 2))
            d.rectangle([px-2, py-2, px+2, py+2], fill=color_main, outline=OUTLINE)
        for dx, dy in [(12,-14),(18,4),(8,16),(16,-6)]:
            d.rectangle([x0+dx-1, y0+dy-1, x0+dx+2, y0+dy+2], fill=color_hi)
    elif phase == 'recoil':
        for dx, dy in [(12,-10),(16,8),(8,14)]:
            d.rectangle([x0+dx, y0+dy, x0+dx+2, y0+dy+2], fill=color_hi)


def build_articulated_8frame_attack(idle_img, stride_img, atk_img, color_main, color_hi,
                                    canvas_w=146, canvas_h=102, target_h=88,
                                    atk_alt_img=None, has_builtin_fx=False, fx_tip_x=34):
    im_idle = resize_to_height(idle_img.convert('RGBA'), target_h)
    im_str  = resize_to_height(stride_img.convert('RGBA'), target_h)
    im_atk  = resize_to_height(atk_img.convert('RGBA'), target_h)
    im_alt  = resize_to_height(atk_alt_img.convert('RGBA'), target_h) if atk_alt_img else im_atk

    p0 = shear_x_nearest(scale_nearest(im_idle, 1.02, 0.96), -0.08)
    p1 = shear_x_nearest(scale_nearest(im_idle, 1.04, 0.92), -0.14)
    p2 = shear_x_nearest(scale_nearest(im_str,  1.04, 0.98),  0.12)
    p3 = shear_x_nearest(scale_nearest(im_atk,  0.98, 1.01),  0.07)
    p4 = scale_nearest(im_atk, 1.04, 1.01)
    p5 = shear_x_nearest(scale_nearest(im_alt,  1.02, 0.99),  0.10)
    p6 = shear_x_nearest(scale_nearest(im_str,  0.99, 0.99), -0.04)
    p7 = im_idle

    configs = [
        (p0, -8,  1, None,    0,  0),
        (p1, -12, 2, 'charge', -6, -48),
        (p2,   4, 0, None,    0,  0),
        (p3,   9, 0, 'start',  fx_tip_x - 10, -48),
        (p4,  14,-1, 'peak',   fx_tip_x,      -48),
        (p5,  11, 0, 'follow', fx_tip_x + 2,  -44),
        (p6,   2, 0, 'recoil', fx_tip_x - 8,  -44),
        (p7,  -1, 0, None,    0,  0),
    ]

    frames = []
    anchor_x = int(canvas_w * 0.36)
    foot_y = canvas_h - 4
    for pose, dx, dy, fx, fx_ox, fx_oy in configs:
        c = Image.new('RGBA', (canvas_w, canvas_h), (0, 0, 0, 0))
        crop = pose.crop(pose.getbbox()) if pose.getbbox() else pose
        pw, ph = crop.size
        left_anchor = 0.28 if (has_builtin_fx and pw > 110) else 0.42
        px = anchor_x - int(pw * left_anchor) + dx
        py = foot_y - ph + dy
        c.paste(crop, (px, py), crop)
        if fx:
            draw_pixel_swoosh(c, anchor_x + fx_ox, foot_y + fx_oy, 22, 26, color_main, color_hi,
                              phase=fx, has_builtin_fx=has_builtin_fx)
        frames.append(c)
    return frames



def make_clean_boss_body(boss_img):
    """Strip the frozen mid-swing yellow arcs & far chain tails from cholo_boss.png -> clean standing/walking Boss body."""
    im = boss_img.convert('RGBA')
    w, h = im.size
    # Body sits cleanly inside x=47..146; remove any stray yellow swoosh pixels near x>136 or x<52
    body = im.crop((47, 0, min(w, 146), h)).copy()
    bw, bh = body.size
    px = body.load()
    for y in range(bh):
        for x in range(bw):
            r, g, b, a = px[x, y]
            if a == 0:
                continue
            # Remove detached chain/swoosh artifacts at far upper-right edge (x > 90) or far lower-left (x < 6, y > 55)
            if x > 90 and y < 48:
                px[x, y] = (0, 0, 0, 0)
            elif x < 6 and y > 54:
                px[x, y] = (0, 0, 0, 0)
            elif x > 74 and y > 68 and r > 180 and g > 160 and b < 130:
                px[x, y] = (0, 0, 0, 0)
    return body


def draw_pixel_chain(canvas, pts, link_r=3):
    """Draw a crisp outlined steel pixel-art chain along a polyline of (x, y) points."""
    d = ImageDraw.Draw(canvas)
    for i in range(len(pts) - 1):
        x0, y0 = pts[i]
        x1, y1 = pts[i+1]
        steps = max(2, int(math.hypot(x1 - x0, y1 - y0) / 5))
        for k in range(steps + 1):
            t = k / steps
            cx = int(x0 + (x1 - x0) * t)
            cy = int(y0 + (y1 - y0) * t)
            d.ellipse([cx - link_r - 1, cy - link_r - 1, cx + link_r + 1, cy + link_r + 1], fill=OUTLINE)
            col = (148, 163, 184, 255) if (k % 2 == 0) else (100, 116, 139, 255)
            d.ellipse([cx - link_r, cy - link_r, cx + link_r, cy + link_r], fill=col)
            d.point((cx - 1, cy - 1), fill=(226, 232, 240, 255))


def build_boss_male_8frame_walk(boss_img):
    """Clean, menacing 8-frame Boss stomp walk with zero frozen attack sparks & gently swaying iron chain!"""
    body = make_clean_boss_body(boss_img)
    frames = build_pivoted_8frame_walk(
        [body, body, body], body,
        hip_ratio=0.63, target_h=104, canvas_w=132, canvas_h=118, stride_deg=20,
        leg_side='right', upper_hip_overlap=5, hip_spread=9
    )
    # Add gently swaying steel chain held in Boss's fists (no frozen yellow attack arcs!)
    out = []
    for i, fr in enumerate(frames):
        c = fr.copy()
        sway = int(math.sin(i * math.pi / 4) * 5)
        # Hanging chain loop from right-side fist (~x=94, y=54) swaying softly
        pts = [(94, 52), (102 + sway//2, 66), (105 + sway, 80), (99 + sway, 90)]
        draw_pixel_chain(c, pts, link_r=3)
        out.append(c)
    return out


def build_boss_male_8frame_attack(boss_img, walk_frames):
    """
    Distinct 8-frame Boss Chain-Whip Attack:
      0-1: Heavy windup pullback + steel chain raised behind with charge glint
      2: Explosive forward lunge step
      3-4-5: Full cholo_boss chain-whip unleashing forward with properly aligned body & yellow impact starbursts!
      6-7: Recoil & recovery back into clean Boss guard stance
    """
    body_s = resize_to_height(make_clean_boss_body(boss_img), 104)
    full_s = resize_to_height(boss_img.convert('RGBA'), 104)
    # In cholo_boss (204x114), body starts at x=47 (23% of width) and body center is at x=96 (47% of width)
    body_cx_in_full = int(full_s.width * (96.0 / 204.0))
    body_cx_in_clean = body_s.width // 2

    canvas_w, canvas_h = 220, 124
    anchor_x = 92  # Boss torso stays anchored cleanly at x=92 (~0.42 of 220)
    foot_y = canvas_h - 4

    frames = []
    for i in range(8):
        c = Image.new('RGBA', (canvas_w, canvas_h), (0, 0, 0, 0))
        if i == 0:
            im = shear_x_nearest(scale_nearest(body_s, 1.02, 0.96), -0.09)
            px = anchor_x - im.width // 2 - 6
            py = foot_y - im.height + 2
            c.paste(im, (px, py), im)
            draw_pixel_chain(c, [(px + 20, py + 44), (px - 2, py + 30), (px - 10, py + 16)], link_r=3)
        elif i == 1:
            im = shear_x_nearest(scale_nearest(body_s, 1.04, 0.93), -0.15)
            px = anchor_x - im.width // 2 - 10
            py = foot_y - im.height + 4
            c.paste(im, (px, py), im)
            draw_pixel_chain(c, [(px + 18, py + 42), (px - 8, py + 22), (px - 16, py + 8)], link_r=3)
            draw_pixel_swoosh(c, max(12, px - 14), max(12, py + 8), 16, 16, (245, 158, 11, 240), (254, 240, 138, 255), phase='charge')
        elif i == 2:
            im = shear_x_nearest(scale_nearest(body_s, 1.03, 0.98), 0.12)
            px = anchor_x - im.width // 2 + 5
            py = foot_y - im.height + 1
            c.paste(im, (px, py), im)
            draw_pixel_chain(c, [(px + im.width - 14, py + 44), (px + im.width + 12, py + 24), (px + im.width + 30, py + 16)], link_r=3)
            draw_pixel_swoosh(c, anchor_x + 56, foot_y - 60, 22, 22, (245, 158, 11, 235), (254, 240, 138, 255), phase='start')
        elif i in (3, 4, 5):
            # Full whipping chain strike! Align Boss torso to anchor_x so body never teleports!
            dx = {3: 8, 4: 15, 5: 11}[i]
            dy = {3: 0, 4: -2, 5: 1}[i]
            sc_x, sc_y = {3: (0.99, 1.01), 4: (1.03, 1.02), 5: (1.01, 0.99)}[i]
            im = scale_nearest(full_s, sc_x, sc_y)
            scaled_cx = int(body_cx_in_full * sc_x)
            px = anchor_x - scaled_cx + dx
            py = foot_y - im.height + dy
            c.paste(im, (px, py), im)
            if i == 4:
                # Bright impact starburst right at the front tip of the whipping chain (far right, NOT on belly!)
                tip_x = min(canvas_w - 14, px + im.width - 10)
                draw_pixel_swoosh(c, tip_x - 14, foot_y - 56, 20, 24, (245, 158, 11, 245), (255, 252, 210, 255), phase='peak', has_builtin_fx=True)
            elif i == 5:
                tip_x = min(canvas_w - 16, px + im.width - 14)
                draw_pixel_swoosh(c, tip_x - 18, foot_y - 52, 18, 20, (245, 158, 11, 230), (254, 240, 138, 255), phase='follow', has_builtin_fx=True)
        elif i == 6:
            im = shear_x_nearest(body_s, 0.05)
            px = anchor_x - im.width // 2 + 3
            py = foot_y - im.height + 1
            c.paste(im, (px, py), im)
            draw_pixel_chain(c, [(px + im.width - 16, py + 48), (px + im.width + 6, py + 66), (px + im.width + 2, py + 84)], link_r=3)
            draw_pixel_swoosh(c, anchor_x + 62, foot_y - 46, 18, 18, (245, 158, 11, 220), (254, 240, 138, 255), phase='recoil')
        else:
            im = body_s
            px = anchor_x - im.width // 2
            py = foot_y - im.height
            c.paste(im, (px, py), im)
            draw_pixel_chain(c, [(px + im.width - 16, py + 50), (px + im.width - 6, py + 68), (px + im.width - 10, py + 84)], link_r=3)
        frames.append(c)
    return frames


def bossify_chola_sprite(im):
    """
    Transform a Chola sprite into LA JEFA CHOLA (Female Boss):
      - Preserves her fierce, expressive pixel-art face & eyes 100% untouched!
      - Turns her red bandana into a gleaming royal gold-and-magenta Boss Bandana!
      - Turns her red plaid shirt into a sleek obsidian-black & gold Boss Leather Jacket!
      - Deepens her jeans to royal charcoal-indigo with gold belt buckle accents!
    """
    src = im.convert('RGBA')
    w, h = src.size
    out = src.copy()
    px = out.load()

    def is_skin(r, g, b):
        # Warm skin tones have r > g > b with moderate-high green (g >= 95) and low red-green gap (< 78)
        return r >= 150 and g >= 92 and b >= 58 and (r - g) < 78 and (g - b) < 70

    for y in range(h):
        yf = y / float(h)
        for x in range(w):
            r, g, b, a = px[x, y]
            if a < 128:
                continue
            if r < 34 and g < 34 and b < 42:
                continue
            if is_skin(r, g, b):
                continue
            # Bandana ONLY (strictly red pixels in top 20% — never touches face/skin!)
            if yf < 0.21 and r > 105 and (r - g) > 52 and b < 95:
                if r > 175:
                    px[x, y] = (245, 183, 0, a)   # gleaming gold boss bandana highlights!
                else:
                    px[x, y] = (185, 28, 92, a)   # royal magenta-crimson boss bandana
            # Upper jacket/shirt region (y 33%..57%): obsidian-black & gold leather boss jacket!
            elif 0.33 <= yf <= 0.58 and (r - g) > 16 and r > 48:
                lum = (r + g + b) / 3.0
                if lum > 108:
                    px[x, y] = (245, 183, 0, a)   # gold zipper / collar / sleeve trim!
                elif lum > 68:
                    px[x, y] = (74, 24, 58, a)    # deep boss magenta-plum leather highlight
                else:
                    px[x, y] = (32, 22, 38, a)    # obsidian-black leather jacket
            # Jeans (y > 58%): dark boss indigo-charcoal jeans
            elif yf > 0.58 and b > r + 6 and g > 42 and b < 165:
                px[x, y] = (max(24, int(r * 0.68)), max(22, int(g * 0.62)), max(46, int(b * 0.85)), a)
    return out


def draw_spiked_bat(canvas, x0, y0, angle_deg, length=38):
    """Draw a crisp pixel-art spiked steel baseball bat from grip (x0, y0) at angle_deg (0=right, -90=up)."""
    rad = math.radians(angle_deg)
    dx, dy = math.cos(rad), math.sin(rad)
    px_n, py_n = -dy, dx  # perpendicular
    d = ImageDraw.Draw(canvas)
    # Build bat silhouette from narrow handle to thick barrel
    steps = length
    for t in range(steps):
        frac = t / float(steps)
        bx = x0 + dx * t
        by = y0 + dy * t
        rad_w = 1.6 if frac < 0.32 else (1.6 + (frac - 0.32) * 3.8)
        p1 = (int(bx + px_n * (rad_w + 1)), int(by + py_n * (rad_w + 1)))
        p2 = (int(bx - px_n * (rad_w + 1)), int(by - py_n * (rad_w + 1)))
        d.line([p1, p2], fill=OUTLINE, width=2)
    for t in range(1, steps - 1):
        frac = t / float(steps)
        bx = x0 + dx * t
        by = y0 + dy * t
        rad_w = 1.1 if frac < 0.32 else (1.1 + (frac - 0.32) * 3.1)
        col = (190, 24, 93, 255) if frac < 0.28 else ((226, 232, 240, 255) if frac > 0.72 else (148, 163, 184, 255))
        p1 = (int(bx + px_n * rad_w), int(by + py_n * rad_w))
        p2 = (int(bx - px_n * rad_w), int(by - py_n * rad_w))
        d.line([p1, p2], fill=col, width=2)
    # Metallic gold spikes near barrel tip!
    for sf in (0.68, 0.84):
        bx = x0 + dx * (length * sf)
        by = y0 + dy * (length * sf)
        for sign in (-1, 1):
            tx = int(bx + px_n * sign * 8)
            ty = int(by + py_n * sign * 8)
            d.line([(int(bx), int(by)), (tx, ty)], fill=OUTLINE, width=3)
            d.line([(int(bx), int(by)), (tx, ty)], fill=(250, 204, 21, 255), width=1)


def build_boss_female_8frame_walk(chola_0, chola_1, chola_2):
    """Imposing 8-frame Female Boss (La Jefa Chola) walk with gold-black boss outfit & spiked bat over shoulder!"""
    b0 = bossify_chola_sprite(chola_0)
    b1 = bossify_chola_sprite(chola_1)
    b2 = bossify_chola_sprite(chola_2)
    frames = build_pivoted_8frame_walk(
        [b0, b1, b2], b1,
        hip_ratio=0.62, target_h=102, canvas_w=120, canvas_h=116, stride_deg=25,
        leg_side='right', upper_hip_overlap=5
    )
    out = []
    for i, fr in enumerate(frames):
        c = fr.copy()
        sway = math.sin(i * math.pi / 4) * 5.0
        # Resting spiked bat angled cleanly behind/over her shoulder
        draw_spiked_bat(c, 50, 58, -140 + sway, length=38)
        out.append(c)
    return out


def build_boss_female_8frame_attack(chola_0, chola_1, chola_kick):
    """Fierce 8-frame Female Boss spiked-bat home-run swing & boss high-kick combo!"""
    b_idle = resize_to_height(bossify_chola_sprite(chola_1), 102)
    b_str  = resize_to_height(bossify_chola_sprite(chola_0), 102)
    b_kick = resize_to_height(bossify_chola_sprite(chola_kick), 102)

    canvas_w, canvas_h = 176, 118
    anchor_x = 68  # ~0.38 of 176
    foot_y = canvas_h - 4
    frames = []
    bat_angles = [-155, -172, -100, -32, 8, 36, -65, -132]
    for i in range(8):
        c = Image.new('RGBA', (canvas_w, canvas_h), (0, 0, 0, 0))
        if i == 0:
            im = shear_x_nearest(scale_nearest(b_idle, 1.02, 0.96), -0.09); dx, dy = -6, 1
        elif i == 1:
            im = shear_x_nearest(scale_nearest(b_idle, 1.04, 0.92), -0.15); dx, dy = -10, 3
        elif i == 2:
            im = shear_x_nearest(scale_nearest(b_str,  1.03, 0.98),  0.12); dx, dy = 4, 0
        elif i == 3:
            im = shear_x_nearest(scale_nearest(b_kick, 0.98, 1.01),  0.07); dx, dy = 9, 0
        elif i == 4:
            im = scale_nearest(b_kick, 1.04, 1.01); dx, dy = 14, -1
        elif i == 5:
            im = shear_x_nearest(scale_nearest(b_kick, 1.02, 0.99),  0.10); dx, dy = 10, 0
        elif i == 6:
            im = shear_x_nearest(b_str, -0.04); dx, dy = 2, 0
        else:
            im = b_idle; dx, dy = 0, 0

        px = anchor_x - int(im.width * 0.42) + dx
        py = foot_y - im.height + dy
        # On windup frames draw bat behind her; on swing frames draw bat striking in front!
        grip_x = anchor_x + dx + (12 if i >= 2 and i <= 5 else -6)
        grip_y = foot_y - 56 + dy
        if i <= 1 or i >= 6:
            draw_spiked_bat(c, grip_x, grip_y, bat_angles[i], length=42)
            c.paste(im, (px, py), im)
        else:
            c.paste(im, (px, py), im)
            draw_spiked_bat(c, grip_x, grip_y, bat_angles[i], length=46)

        if i == 1:
            draw_pixel_swoosh(c, max(10, grip_x - 36), max(14, grip_y - 10), 16, 16, (236, 72, 153, 240), (254, 240, 138, 255), phase='charge')
        elif i == 3:
            draw_pixel_swoosh(c, anchor_x + 44, foot_y - 58, 26, 30, (236, 72, 153, 235), (254, 240, 138, 255), phase='start')
        elif i == 4:
            draw_pixel_swoosh(c, anchor_x + 56, foot_y - 54, 30, 34, (236, 72, 153, 245), (254, 240, 138, 255), phase='peak')
        elif i == 5:
            draw_pixel_swoosh(c, anchor_x + 58, foot_y - 50, 26, 28, (236, 72, 153, 230), (254, 240, 138, 255), phase='follow')
        elif i == 6:
            draw_pixel_swoosh(c, anchor_x + 48, foot_y - 48, 20, 22, (236, 72, 153, 210), (254, 240, 138, 255), phase='recoil')
        frames.append(c)
    return frames


def main():
    with open(os.path.join(SPR_DIR, 'all_assets.json')) as f:
        assets = json.load(f)

    # 1. Teacher Aldo Walk v2 & Jump (UNIFORM SCALE + HEAD-LOCKED X! Zero head inflation or jitter!)
    print('Extracting Aldo Walk v2 & Jump with uniform scale + head-center alignment...')
    aldo_walk = extract_uniform_8sheet(
        os.path.join(ART_DIR, 'aldo_walk_8frames_v2_1795578444919.jpg'),
        target_ref_h=86, canvas_w=92, canvas_h=96, preserve_air_lift=False
    )
    aldo_jump = extract_uniform_8sheet(
        os.path.join(ART_DIR, 'aldo_jump_8frames_1795577718348.jpg'),
        target_ref_h=84, canvas_w=96, canvas_h=98, preserve_air_lift=True
    )
    assets['aldoWalk'] = [to_b64_png(fr, 48) for fr in aldo_walk]
    assets['aldoJump'] = [to_b64_png(fr, 48) for fr in aldo_jump]
    for i, fr in enumerate(aldo_walk):
        fr.save(os.path.join(SPR_DIR, f'aldo_walk_{i}.png'))

    # Load clean base PNGs
    aldo_idle   = Image.open(os.path.join(SPR_DIR, 'aldo_idle.png'))
    aldo_marker = Image.open(os.path.join(SPR_DIR, 'marker_kunai.png'))
    aldo_slam   = Image.open(os.path.join(SPR_DIR, 'eraser_slam.png'))

    sofia_idle = Image.open(os.path.join(SPR_DIR, 'sofia_idle.png'))
    sofia_run  = Image.open(os.path.join(SPR_DIR, 'sofia_anim_0.png'))
    sofia_atk  = Image.open(os.path.join(SPR_DIR, 'sofia_attack.png'))
    sofia_kick = Image.open(os.path.join(SPR_DIR, 'sofia_anim_3.png'))

    mateo_idle = Image.open(os.path.join(SPR_DIR, 'mateo_idle.png'))
    mateo_run  = Image.open(os.path.join(SPR_DIR, 'mateo_anim_0.png'))
    mateo_atk  = Image.open(os.path.join(SPR_DIR, 'mateo_attack.png'))
    mateo_slam = Image.open(os.path.join(SPR_DIR, 'mateo_anim_3.png'))

    cholo_0     = Image.open(os.path.join(SPR_DIR, 'cholo_m_0.png'))
    cholo_1     = Image.open(os.path.join(SPR_DIR, 'cholo_m_1.png'))
    cholo_2     = Image.open(os.path.join(SPR_DIR, 'cholo_m_2.png'))
    cholo_punch = Image.open(os.path.join(SPR_DIR, 'cholo_m_3.png'))

    chola_0    = Image.open(os.path.join(SPR_DIR, 'chola_0.png'))
    chola_1    = Image.open(os.path.join(SPR_DIR, 'chola_1.png'))
    chola_2    = Image.open(os.path.join(SPR_DIR, 'chola_2.png'))
    chola_kick = Image.open(os.path.join(SPR_DIR, 'chola_3.png'))

    boss_img = Image.open(os.path.join(SPR_DIR, 'cholo_boss.png'))

    # 2. Build Smooth Two-Leg Jointed 8-Frame Walk Cycles (constant head size, natural stride!)
    print('Building smooth jointed 8-frame walk cycles...')
    sofia_walk = build_pivoted_8frame_walk(
        [sofia_idle, sofia_idle, sofia_idle], sofia_idle,
        hip_ratio=0.66, target_h=88, canvas_w=92, canvas_h=96, stride_deg=27, leg_side='right', upper_hip_overlap=6
    )
    mateo_walk = build_pivoted_8frame_walk(
        [mateo_idle, mateo_idle, mateo_idle], mateo_idle,
        hip_ratio=0.66, target_h=88, canvas_w=94, canvas_h=96, stride_deg=25, leg_side='right', upper_hip_overlap=5
    )
    cholo_walk = build_pivoted_8frame_walk(
        [cholo_0, cholo_1, cholo_2], cholo_1,
        hip_ratio=0.62, target_h=88, canvas_w=90, canvas_h=96, stride_deg=24, leg_side='right', upper_hip_overlap=5
    )
    chola_walk = build_pivoted_8frame_walk(
        [chola_0, chola_1, chola_2], chola_1,
        hip_ratio=0.62, target_h=88, canvas_w=90, canvas_h=96, stride_deg=25, leg_side='right', upper_hip_overlap=5
    )
    # Male Boss (clean body + swaying chain) & Female Boss (La Jefa Chola w/ spiked bat & boss leather!)
    boss_walk   = build_boss_male_8frame_walk(boss_img)
    boss_f_walk = build_boss_female_8frame_walk(chola_0, chola_1, chola_2)

    # 3. Build Polished 8-Frame Articulated Attack Cycles
    print('Building polished 8-frame attack cycles...')
    aldo_atk      = build_articulated_8frame_attack(aldo_idle, aldo_walk[0], aldo_marker, (245, 183, 0, 240), (255, 250, 200, 255),
                                                    canvas_w=156, canvas_h=104, target_h=90, atk_alt_img=aldo_slam, has_builtin_fx=True, fx_tip_x=52)
    sofia_atk_arr = build_articulated_8frame_attack(sofia_idle, sofia_run, sofia_atk, (56, 189, 248, 240), (224, 242, 254, 255),
                                                    canvas_w=160, canvas_h=102, target_h=88, atk_alt_img=sofia_kick, has_builtin_fx=True, fx_tip_x=56)
    mateo_atk_arr = build_articulated_8frame_attack(mateo_idle, mateo_run, mateo_atk, (251, 146, 60, 240), (254, 240, 138, 255),
                                                    canvas_w=162, canvas_h=104, target_h=90, atk_alt_img=mateo_slam, has_builtin_fx=True, fx_tip_x=56)
    cholo_atk_arr = build_articulated_8frame_attack(cholo_1, cholo_0, cholo_punch, (239, 68, 68, 235), (254, 202, 202, 255),
                                                    canvas_w=136, canvas_h=98, target_h=88, atk_alt_img=cholo_punch, has_builtin_fx=False, fx_tip_x=34)
    chola_atk_arr = build_articulated_8frame_attack(chola_1, chola_0, chola_kick, (236, 72, 153, 235), (251, 207, 232, 255),
                                                    canvas_w=136, canvas_h=98, target_h=88, atk_alt_img=chola_kick, has_builtin_fx=False, fx_tip_x=36)
    boss_atk_arr   = build_boss_male_8frame_attack(boss_img, boss_walk)
    boss_f_atk_arr = build_boss_female_8frame_attack(chola_0, chola_1, chola_kick)

    for key, arr, col_n in [
        ('sofiaWalk',   sofia_walk,    44),
        ('mateoWalk',   mateo_walk,    44),
        ('choloWalk',   cholo_walk,    40),
        ('cholaWalk',   chola_walk,    44),
        ('bossWalk',    boss_walk,     48),
        ('bossFWalk',   boss_f_walk,   48),
        ('aldoAttack',  aldo_atk,      48),
        ('sofiaAttack', sofia_atk_arr, 44),
        ('mateoAttack', mateo_atk_arr, 44),
        ('choloAttack', cholo_atk_arr, 40),
        ('cholaAttack', chola_atk_arr, 44),
        ('bossAttack',  boss_atk_arr,  48),
        ('bossFAttack', boss_f_atk_arr,48),
    ]:
        assets[key] = [to_b64_png(fr, col_n) for fr in arr]

    with open(os.path.join(SPR_DIR, 'all_assets.json'), 'w') as f:
        json.dump(assets, f, separators=(',', ':'))

    # Save visual contact sheet to /tmp for inspection!
    rows = [
        ('aldoWalk', aldo_walk), ('aldoJump', aldo_jump), ('sofiaWalk', sofia_walk),
        ('mateoWalk', mateo_walk), ('choloWalk', cholo_walk), ('cholaWalk', chola_walk), ('bossWalk', boss_walk)
    ]
    cell_w, cell_h = 128, 124
    sheet = Image.new('RGBA', (cell_w * 8 + 90, cell_h * len(rows)), (36, 34, 46, 255))
    d = ImageDraw.Draw(sheet)
    for r, (name, arr) in enumerate(rows):
        d.text((6, r * cell_h + 52), name, fill=(255, 230, 100, 255))
        for i, im in enumerate(arr):
            cx = 90 + i * cell_w + cell_w // 2
            by = (r + 1) * cell_h - 8
            d.line([(90 + i * cell_w, by), (90 + (i + 1) * cell_w - 4, by)], fill=(90, 90, 110, 255))
            d.line([(cx, r * cell_h + 8), (cx, by)], fill=(65, 65, 85, 255))
            sheet.paste(im, (cx - im.width // 2, by - im.height), im)
            d.text((90 + i * cell_w + 4, r * cell_h + 4), str(i), fill=(180, 180, 200, 255))
    sheet.save('/tmp/walk_contact_sheet_v2.png')
    b_rows = [('bossWalk', boss_walk), ('bossAttack', boss_atk_arr), ('bossFWalk', boss_f_walk), ('bossFAttack', boss_f_atk_arr)]
    bcw, bch = 186, 130
    bsheet = Image.new('RGBA', (bcw * 8 + 100, bch * len(b_rows)), (36, 34, 46, 255))
    bd = ImageDraw.Draw(bsheet)
    for r, (name, arr) in enumerate(b_rows):
        bd.text((6, r * bch + 55), name, fill=(255, 230, 100, 255))
        for i, im in enumerate(arr):
            cx = 100 + i * bcw + bcw // 2
            by = (r + 1) * bch - 6
            bd.line([(100 + i * bcw, by), (100 + (i + 1) * bcw - 4, by)], fill=(90, 90, 110, 255))
            bsheet.paste(im, (cx - im.width // 2, by - im.height), im)
            bd.text((100 + i * bcw + 4, r * bch + 4), str(i), fill=(180, 180, 200, 255))
    bsheet.save('/tmp/boss_v2.png')
    print('Done! Saved sprites/all_assets.json and /tmp/walk_contact_sheet_v2.png')

if __name__ == '__main__':
    main()

import os, json, base64, io
from PIL import Image, ImageDraw

ART_DIR = '/home/antigravity/.gemini/jetski/brain/v1/default/jetski_remote_agents_3p_devbox/3371c7b6-b155-400e-8450-f6de6eda02e9'
SPR_DIR = '/home/antigravity/cetis69-defenders/sprites'
OUTLINE = (21, 20, 28)

z1 = Image.open(os.path.join(ART_DIR, 'benito_juarez_bridge_bg_1795576110298.jpg')).convert('RGB').resize((800, 450), Image.NEAREST)
campus = Image.open(os.path.join(ART_DIR, 'cetis69_campus_bg_1795576082247.jpg')).convert('RGB').resize((800, 450), Image.NEAREST)


def px_rect(d, x, y, w, h, fill, outline=OUTLINE):
    d.rectangle([x - 1, y - 1, x + w, y + h], fill=outline)
    d.rectangle([x, y, x + w - 1, y + h - 1], fill=fill)


def paste_cutout_sky(dst, src, px0, py0):
    sw, sh = src.size
    for yy in range(sh):
        for xx in range(sw):
            r, g, b = src.getpixel((xx, yy))
            if (b > 170 and b > r + 40) or (r > 218 and g > 228 and b > 238):
                continue
            if 0 <= px0 + xx < 800 and 0 <= py0 + yy < 450:
                dst.putpixel((px0 + xx, py0 + yy), (r, g, b))


def draw_sky_gradient(im, top_l, bot_l, top_r, bot_r, y_end=286):
    """Crisp pixel-art banded sky gradient blending smoothly left-to-right across seams."""
    px = im.load()
    for y in range(y_end):
        ty = int((y / float(y_end)) * 12) / 12.0  # crisp retro pixel-art color bands!
        for x in range(800):
            tx = x / 799.0
            c_top = [top_l[i] * (1 - tx) + top_r[i] * tx for i in range(3)]
            c_bot = [bot_l[i] * (1 - tx) + bot_r[i] * tx for i in range(3)]
            px[x, y] = tuple(int(c_top[i] * (1 - ty) + c_bot[i] * ty) for i in range(3))


def build_zone2_park():
    im = Image.new('RGB', (800, 450))
    # Smooth sky from Zone 1 Sonora blue -> warm golden-afternoon blue on right edge
    draw_sky_gradient(im, (66, 152, 232), (168, 214, 244), (92, 146, 214), (232, 198, 162), y_end=288)

    # Exact matching sidewalk + asphalt street + foreground sidewalk from Zone 1
    road_tile = z1.crop((316, 286, 556, 450))
    for x in range(0, 800, road_tile.width):
        im.paste(road_tile, (x, 286))

    d = ImageDraw.Draw(im)

    # Seamless left seam continuation: concrete overpass exiting left edge
    bridge_exit = z1.crop((748, 0, 800, 290))
    im.paste(bridge_exit, (0, 0))
    d.polygon([(52, 0), (122, 0), (76, 178), (52, 178)], fill=(122, 128, 140), outline=OUTLINE)
    d.polygon([(52, 178), (76, 178), (76, 288), (52, 288)], fill=(144, 148, 156), outline=OUTLINE)
    # Soft fading shadow from the overpass onto the road
    for y in range(288, 415):
        for x in range(0, 85):
            r, g, b = im.getpixel((x, y))
            f = 0.60 + 0.40 * (x / 85.0)
            im.putpixel((x, y), (int(r * f), int(g * f), int(b * f)))

    # Neighborhood houses & cactus (strictly x=292..455 from z1 -> ZERO repeated school wall!)
    houses = z1.crop((292, 134, 452, 288))
    paste_cutout_sky(im, houses, 108, 134)

    # Sunny Community Park (Parque Benito Juárez) across x=275..592
    px_rect(d, 276, 250, 314, 38, (94, 158, 72))
    d.rectangle([276, 250, 590, 260], fill=(126, 192, 88))
    px_rect(d, 276, 274, 314, 14, (156, 86, 64))
    for bx in range(282, 588, 18):
        d.line([(bx, 274), (bx, 288)], fill=(112, 58, 44))
    for fx in range(282, 588, 16):
        d.rectangle([fx, 214, fx + 2, 250], fill=(48, 56, 68))
    d.rectangle([276, 222, 590, 225], fill=(48, 56, 68))
    d.rectangle([276, 242, 590, 245], fill=(48, 56, 68))

    # Real Nano Banana palm trees planted in the park
    palm_l = campus.crop((18, 36, 108, 270))
    paste_cutout_sky(im, palm_l.resize((72, 188), Image.NEAREST), 296, 74)
    palm_r = campus.crop((670, 110, 778, 268))
    paste_cutout_sky(im, palm_r.resize((88, 134), Image.NEAREST), 488, 128)

    # Park shaded pergola
    px_rect(d, 388, 178, 86, 16, (122, 28, 51))
    px_rect(d, 396, 194, 8, 56, (214, 196, 162))
    px_rect(d, 458, 194, 8, 56, (214, 196, 162))
    px_rect(d, 386, 174, 90, 6, (245, 183, 0))

    # Corner Tiendita ("ABARROTES PANTERA") on the right (x=598..798)
    px_rect(d, 598, 132, 202, 156, (238, 212, 156))
    px_rect(d, 598, 124, 202, 14, (122, 28, 51))
    px_rect(d, 598, 246, 202, 42, (14, 116, 144))
    for i in range(9):
        col = (220, 38, 38) if i % 2 == 0 else (248, 250, 252)
        px_rect(d, 606 + i * 20, 174, 20, 18, col)
    px_rect(d, 616, 144, 168, 24, (122, 28, 51), (245, 183, 0))
    d.text((634, 151), "ABARROTES PANTERA", fill=(254, 240, 138))
    px_rect(d, 622, 202, 54, 84, (71, 85, 105))
    for sy in range(210, 282, 8):
        d.line([(624, sy), (674, sy)], fill=(51, 65, 85))
    px_rect(d, 692, 202, 74, 42, (56, 189, 248))
    d.rectangle([698, 208, 706, 234], fill=(186, 230, 253))

    # Utility pole & continuous power lines to right edge
    px_rect(d, 578, 74, 10, 214, (124, 116, 108))
    px_rect(d, 562, 86, 42, 6, (104, 96, 90))
    d.line([(106, 76), (578, 92)], fill=OUTLINE, width=2)
    d.line([(106, 88), (578, 104)], fill=OUTLINE, width=2)
    d.line([(588, 92), (800, 84)], fill=OUTLINE, width=2)
    d.line([(588, 104), (800, 96)], fill=OUTLINE, width=2)

    for rx in range(44, 780, 78):
        d.rectangle([rx, 356, rx + 36, 360], fill=(202, 184, 128))
    return im


def build_zone3_lair():
    im = Image.new('RGB', (800, 450))
    # Seamless sky transition from Zone 2's right edge -> dramatic Sonoran sunset purple-gold!
    draw_sky_gradient(im, (92, 146, 214), (232, 198, 162), (76, 38, 98), (242, 152, 84), y_end=288)

    # Exact matching sidewalk & road height (smoothly transitioning into bridge shadow!)
    road_tile = z1.crop((316, 286, 556, 450))
    for x in range(0, 800, road_tile.width):
        im.paste(road_tile, (x, 286))

    d = ImageDraw.Draw(im)
    for rx in range(20, 220, 78):
        d.rectangle([rx, 356, rx + 36, 360], fill=(202, 184, 128))

    # Left seam continuation: side wall of Abarrotes Pantera cleanly ending at x=76
    px_rect(d, 0, 132, 76, 156, (226, 198, 144))
    px_rect(d, 0, 124, 78, 14, (122, 28, 51))
    px_rect(d, 0, 246, 76, 42, (14, 106, 132))
    d.line([(0, 84), (236, 98)], fill=OUTLINE, width=2)
    d.line([(0, 96), (236, 110)], fill=OUTLINE, width=2)

    # Chain-link fence between corner store & concrete overpass
    for cx in range(82, 228, 12):
        d.line([(cx, 196), (cx + 12, 286)], fill=(64, 68, 82))
        d.line([(cx + 12, 196), (cx, 286)], fill=(64, 68, 82))
    d.rectangle([78, 194, 232, 198], fill=(88, 94, 110))

    # Massive Concrete Overpass Bridge Structure across x=224..800 (Guarida Bajo el Puente!)
    px_rect(d, 218, 0, 582, 82, (82, 76, 94))
    px_rect(d, 218, 74, 582, 14, (52, 48, 64))
    px_rect(d, 250, 88, 550, 200, (98, 94, 110))
    for wx in range(290, 800, 64):
        d.line([(wx, 88), (wx, 288)], fill=(76, 72, 86), width=2)

    # Authentic Nano Banana "BAJO EL PUENTE" graffiti wall on right
    bajo_wall = z1.crop((535, 198, 765, 290))
    im.paste(bajo_wall, (545, 198))
    # Urban graffiti tag on left retaining wall
    px_rect(d, 286, 168, 134, 62, (108, 104, 120))
    d.rectangle([294, 178, 342, 212], fill=(236, 72, 153))
    d.rectangle([330, 184, 382, 218], fill=(34, 211, 238))
    d.rectangle([368, 176, 408, 210], fill=(250, 204, 21))
    d.text((302, 192), "BAJO EL PUENTE", fill=OUTLINE)

    # Concrete support pillars
    for px0 in (236, 476, 744):
        px_rect(d, px0, 82, 42, 208, (116, 112, 128))
        d.rectangle([px0 + 4, 86, px0 + 12, 286], fill=(138, 134, 150))
        d.rectangle([px0 + 30, 86, px0 + 38, 286], fill=(82, 78, 94))

    # Glowing fire barrel under the bridge!
    px_rect(d, 424, 236, 28, 50, (180, 83, 9))
    d.rectangle([424, 252, 452, 256], fill=(245, 158, 11))
    d.rectangle([424, 268, 452, 272], fill=(245, 158, 11))
    d.polygon([(428, 236), (434, 216), (440, 230), (446, 214), (450, 236)], fill=(251, 146, 60))
    d.polygon([(432, 236), (437, 224), (444, 236)], fill=(254, 240, 138))

    # Smooth atmospheric bridge shadow fading in from x=210..290 -> full shadow to x=800
    for y in range(288, 415):
        for x in range(210, 800):
            t = min(1.0, (x - 210) / 70.0)
            r, g, b = im.getpixel((x, y))
            f_r = 1.0 - 0.28 * t
            f_g = 1.0 - 0.30 * t
            f_b = 1.0 - 0.22 * t
            im.putpixel((x, y), (int(r * f_r), int(g * f_g), int(b * f_b)))
    return im


def to_b64_jpg(img, quality=76):
    buf = io.BytesIO()
    img.convert('RGB').save(buf, format='JPEG', quality=quality, optimize=True)
    return 'data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode('ascii'), len(buf.getvalue())


def main():
    z2 = build_zone2_park()
    z3 = build_zone3_lair()
    z2.save(os.path.join(SPR_DIR, 'explore_zone2.jpg'), quality=76, optimize=True)
    z3.save(os.path.join(SPR_DIR, 'explore_zone3.jpg'), quality=76, optimize=True)

    b2, sz2 = to_b64_jpg(z2, 76)
    b3, sz3 = to_b64_jpg(z3, 76)
    print(f"explore_zone2.jpg: {sz2/1024:.1f} KB | explore_zone3.jpg: {sz3/1024:.1f} KB")

    pano = Image.new('RGB', (2400, 450))
    pano.paste(z1, (0, 0))
    pano.paste(z2, (800, 0))
    pano.paste(z3, (1600, 0))
    pano.resize((1200, 225), Image.NEAREST).save('/tmp/explore_panorama_preview.png')

    with open(os.path.join(SPR_DIR, 'all_assets.json')) as f:
        assets = json.load(f)
    assets['bgs']['explore2'] = b2
    assets['bgs']['explore3'] = b3
    with open(os.path.join(SPR_DIR, 'all_assets.json'), 'w') as f:
        json.dump(assets, f, separators=(',', ':'))
    print("Updated sprites/all_assets.json!")

if __name__ == '__main__':
    main()

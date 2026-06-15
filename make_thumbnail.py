"""Generate a 1280x720 thumbnail for the World Cup Prediction Agent."""

import math
from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 720

NAVY  = (8, 15, 40)
GOLD  = (255, 200, 50)
WHITE = (255, 255, 255)
GREY  = (140, 155, 180)

FONT_BOLD  = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_PLAIN = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def load(path, size):
    return ImageFont.truetype(path, size)


def draw_soccer_ball(draw, cx, cy, r):
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=WHITE, outline=(200, 200, 200), width=2)
    n = 5
    pts = []
    for i in range(n):
        angle = math.radians(-90 + i * 72)
        pts.append((cx + r * 0.38 * math.cos(angle), cy + r * 0.38 * math.sin(angle)))
    draw.polygon(pts, fill=(30, 30, 30))
    outer_r = r * 0.72
    for i in range(n):
        angle = math.radians(-90 + i * 72)
        ox = cx + outer_r * math.cos(angle)
        oy = cy + outer_r * math.sin(angle)
        inner = r * 0.22
        pts2 = []
        for j in range(5):
            a2 = math.radians(angle * (180 / math.pi) + j * 72 + 36)
            pts2.append((ox + inner * math.cos(a2), oy + inner * math.sin(a2)))
        draw.polygon(pts2, fill=(30, 30, 30))
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(50, 50, 50), width=3)


def main():
    img = Image.new("RGB", (W, H), NAVY)
    draw = ImageDraw.Draw(img)

    # Subtle horizontal rule (field centre line feel)
    draw.line([(0, H // 2), (W, H // 2)], fill=(18, 30, 65), width=1)

    # Gold top bar
    draw.rectangle([0, 0, W, 5], fill=GOLD)

    # Ball — left-of-centre, vertically centred
    ball_cx, ball_cy, ball_r = 310, H // 2, 200
    draw_soccer_ball(draw, ball_cx, ball_cy, ball_r)

    # Right-side text
    tx = 570
    ty = 160

    f_small = load(FONT_BOLD, 22)
    f_title1 = load(FONT_BOLD, 100)
    f_title2 = load(FONT_BOLD, 100)
    f_tag   = load(FONT_PLAIN, 28)

    draw.text((tx, ty),        "WORLD CUP 2026",    font=f_small,  fill=GOLD)
    draw.text((tx, ty + 36),   "PREDICTION",        font=f_title1, fill=WHITE)
    draw.text((tx, ty + 148),  "AGENT",             font=f_title2, fill=GOLD)
    draw.text((tx, ty + 268),  "Self-improving AI · x402 payments", font=f_tag, fill=GREY)

    out_path = "thumbnail.png"
    img.save(out_path, quality=95)
    print(f"Saved {out_path}")


if __name__ == "__main__":
    main()

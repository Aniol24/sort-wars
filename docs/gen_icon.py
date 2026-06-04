"""Generates the 1024x1024 app icon for auto-tok."""
from PIL import Image, ImageDraw, ImageFont

SIZE = 1024
BG   = (4, 4, 12)
A    = (0, 255, 140)
B    = (255, 60, 90)

img  = Image.new("RGB", (SIZE, SIZE), BG)
draw = ImageDraw.Draw(img)

bars = [0.20, 0.45, 0.60, 0.30, 0.80, 0.50, 0.95, 0.70, 0.40, 0.85,
        0.55, 0.25, 0.65, 0.90, 0.35, 0.75]

n      = len(bars)
pad    = 80
bw     = (SIZE - pad * 2) // n
gap    = max(4, bw // 8)
max_h  = SIZE - pad * 2 - 100
base_y = SIZE - pad

for i, v in enumerate(bars):
    x1    = pad + i * bw + gap
    x2    = pad + (i + 1) * bw - gap
    bh    = int(max_h * v)
    color = A if i < n // 2 else B
    r     = max(4, (x2 - x1) // 4)
    draw.rounded_rectangle([(x1, base_y - bh), (x2, base_y)], radius=r, fill=color)

img.save("icon.png")
print("icon.png saved (1024x1024)")

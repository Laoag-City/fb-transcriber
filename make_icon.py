"""Generate icon.ico (speech bubble with sound-wave bars). Run: python make_icon.py"""
from PIL import Image, ImageDraw

S = 1024
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((0, 0, S - 1, S - 1), radius=230, fill=(24, 119, 242, 255))  # blue tile
# speech bubble
d.rounded_rectangle((150, 190, 874, 690), radius=140, fill="white")
d.polygon([(280, 660), (280, 860), (480, 680)], fill="white")
# sound-wave bars
heights = [140, 260, 380, 260, 330, 180, 100]
bar_w, gap = 62, 40
total = len(heights) * bar_w + (len(heights) - 1) * gap
x = (S - total) // 2
cy = 440
for h in heights:
    d.rounded_rectangle((x, cy - h // 2, x + bar_w, cy + h // 2), radius=bar_w // 2, fill=(24, 119, 242, 255))
    x += bar_w + gap
img.save("icon.ico", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])


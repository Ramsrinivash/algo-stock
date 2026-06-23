import os
from PIL import Image

src_path = r"C:\Users\dell\.gemini\antigravity-ide\brain\e2de3ab2-5c5b-4b80-ab25-0472c873a6fa\media__1782035562061.jpg"
dest_dir = r"r:\Ram\Algo stock\frontend"

img = Image.open(src_path)
width, height = img.size
print(f"Original image size: {width}x{height}")

# Let's inspect pixels to find a tighter bounding box
# Background is dark blue: e.g. R < 10, G < 10, B < 40
# We find any pixel where R > 15 or G > 15 or B > 45
left, top, right, bottom = width, height, 0, 0
pixels = img.load()
for y in range(height):
    for x in range(width):
        r, g, b = pixels[x, y]
        if r > 15 or g > 15 or b > 45:
            if x < left: left = x
            if x > right: right = x
            if y < top: top = y
            if y > bottom: bottom = y

print(f"Custom threshold bounding box: ({left}, {top}, {right}, {bottom})")

# Crop the logo with a margin
margin_x = 20
margin_y = 15
x0 = max(0, left - margin_x)
y0 = max(0, top - margin_y)
x1 = min(width, right + margin_x)
y1 = min(height, bottom + margin_y)

logo_img = img.crop((x0, y0, x1, y1))
logo_path = os.path.join(dest_dir, "logo.png")
logo_img.save(logo_path, "PNG")
print(f"Saved cropped logo to: {logo_path} (size: {logo_img.size})")

# Favicon: Crop just the symbol on the left
# The symbol is on the left. The text start is "FINRIO".
# Let's see: the symbol spans from left to roughly left + (right - left) * 0.43
symbol_w = int((right - left) * 0.43)
symbol_h = bottom - top
sz = max(symbol_w, symbol_h)

cx = left + symbol_w // 2
cy = top + symbol_h // 2

fx0 = max(0, cx - sz // 2 - 10)
fy0 = max(0, cy - sz // 2 - 10)
fx1 = min(width, cx + sz // 2 + 10)
fy1 = min(height, cy + sz // 2 + 10)

favicon_img = img.crop((fx0, fy0, fx1, fy1))
favicon_img = favicon_img.resize((128, 128), Image.Resampling.LANCZOS)
favicon_path = os.path.join(dest_dir, "favicon.png")
favicon_img.save(favicon_path, "PNG")
print(f"Saved favicon to: {favicon_path} (size: {favicon_img.size})")

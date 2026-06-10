"""
Create horizontal PTIA logos from the existing horizontal PNGs in LOGOS directory.
"""
import sys
from pathlib import Path
from PIL import Image
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
LOGOS_DIR = ROOT / "LOGOS"
ASSETS_DIR = ROOT / "site" / "assets"
DATA_DIR = ROOT / "data"

# Source: navy text on off-white background (horizontal)
src_navy = Image.open(LOGOS_DIR / "ChatGPT Image 15_05_2026, 11_26_28 (1).png").convert("RGBA")
# Source: cream text on black background (horizontal)
src_cream = Image.open(LOGOS_DIR / "ChatGPT Image 15_05_2026, 11_26_29 (2).png").convert("RGBA")

print(f"Source navy: {src_navy.size}")
print(f"Source cream: {src_cream.size}")

# ---- NAVY version: dark letters on light background ----
arr = np.array(src_navy).astype(float)
gray = np.mean(arr[:, :, :3], axis=2)

# Background is ~#f8f5ef (around 245), text is ~#001f43 (around 21)
# Stronger threshold: anything darker than 200 is text
bg_level = 240
text_level = 100

# Alpha: 0 for background, 255 for text, smooth transition
alpha = np.clip((bg_level - gray) / (bg_level - text_level) * 255, 0, 255).astype(np.uint8)

result_navy = np.zeros_like(np.array(src_navy))
result_navy[:, :, 0] = 0    # R for #001f43
result_navy[:, :, 1] = 31   # G
result_navy[:, :, 2] = 67   # B
result_navy[:, :, 3] = alpha

navy_img = Image.fromarray(result_navy, "RGBA")

# ---- CREAM version: light letters on dark background ----
arr2 = np.array(src_cream).astype(float)
gray2 = np.mean(arr2[:, :, :3], axis=2)

# Background is ~#0a0a0a (around 10), text is ~#f8f5ef (around 245)
bg_level2 = 20
text_level2 = 150

alpha2 = np.clip((gray2 - bg_level2) / (text_level2 - bg_level2) * 255, 0, 255).astype(np.uint8)

result_cream = np.zeros_like(np.array(src_cream))
result_cream[:, :, 0] = 248  # R for #f8f5ef
result_cream[:, :, 1] = 245  # G
result_cream[:, :, 2] = 239  # B
result_cream[:, :, 3] = alpha2

cream_img = Image.fromarray(result_cream, "RGBA")

# ---- Trim ----
def trim_transparent(img, padding=5):
    arr = np.array(img)
    alpha = arr[:, :, 3]
    rows = np.any(alpha > 30, axis=1)
    cols = np.any(alpha > 30, axis=0)
    if not rows.any() or not cols.any():
        return img
    rmin, rmax = np.where(rows)[0][[0, -1]]
    cmin, cmax = np.where(cols)[0][[0, -1]]
    rmin = max(0, rmin - padding)
    rmax = min(arr.shape[0] - 1, rmax + padding)
    cmin = max(0, cmin - padding)
    cmax = min(arr.shape[1] - 1, cmax + padding)
    return img.crop((cmin, rmin, cmax + 1, rmax + 1))

navy_trimmed = trim_transparent(navy_img)
cream_trimmed = trim_transparent(cream_img)

print(f"Navy trimmed: {navy_trimmed.size}")
print(f"Cream trimmed: {cream_trimmed.size}")

# Save site assets
navy_out = ASSETS_DIR / "ptia-wordmark-navy-transparent.png"
cream_out = ASSETS_DIR / "ptia-wordmark-cream-transparent.png"
navy_trimmed.save(navy_out, optimize=True)
cream_trimmed.save(cream_out, optimize=True)
print(f"Saved: {navy_out}")
print(f"Saved: {cream_out}")

# Dashboard version: cream on transparent
dashboard_out = DATA_DIR / "ptia-logo-cutout.png"
cream_trimmed.save(dashboard_out, optimize=True)
print(f"Saved dashboard: {dashboard_out}")

# Print info
for name, img in [("Navy", navy_trimmed), ("Cream", cream_trimmed)]:
    print(f"\n{name}: {img.size[0]}x{img.size[1]}, ratio={img.size[0]/img.size[1]:.2f}")

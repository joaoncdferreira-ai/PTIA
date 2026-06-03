from PIL import Image
import os
from pathlib import Path

ROOT = Path("c:/Users/joaon/ptia-content-engine")
logo_path = ROOT / "site" / "assets" / "ptia-logo-cutout.png"
site_dir = ROOT / "site"

print("=== FAVICON GENERATION SCRIPT ===")

if not logo_path.exists():
    print(f"Error: Base logo file not found at {logo_path}")
    # Try looking in root data dir just in case
    logo_path = ROOT / "data" / "ptia-logo-cutout.png"
    if not logo_path.exists():
        print(f"Error: Also not found at {logo_path}")
        sys.exit(1)

print(f"Loading base logo from: {logo_path}")
img = Image.open(logo_path)

# Ensure it is in RGBA mode for transparency
if img.mode != 'RGBA':
    img = img.convert('RGBA')

# 1. Generate favicon.ico (containing 16x16, 32x32, 48x48 sizes)
ico_sizes = [(16, 16), (32, 32), (48, 48)]
ico_images = [img.resize(size, Image.Resampling.LANCZOS) for size in ico_sizes]

ico_path = site_dir / "favicon.ico"
ico_images[0].save(ico_path, format="ICO", sizes=ico_sizes, append_images=ico_images[1:])
print(f"SUCCESS: Saved multi-resolution favicon.ico to {ico_path} (Size: {ico_path.stat().st_size / 1024:.2f} KB)")

# 2. Generate favicon.png (32x32 standard transparent PNG)
png_path = site_dir / "favicon.png"
favicon_png = img.resize((32, 32), Image.Resampling.LANCZOS)
favicon_png.save(png_path, format="PNG")
print(f"SUCCESS: Saved favicon.png to {png_path} (Size: {png_path.stat().st_size / 1024:.2f} KB)")

# 3. Generate apple-touch-icon.png (180x180 standard for iOS home screen bookmarks)
apple_path = site_dir / "apple-touch-icon.png"
apple_png = img.resize((180, 180), Image.Resampling.LANCZOS)
apple_png.save(apple_path, format="PNG")
print(f"SUCCESS: Saved apple-touch-icon.png to {apple_path} (Size: {apple_path.stat().st_size / 1024:.2f} KB)")

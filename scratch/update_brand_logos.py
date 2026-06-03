from PIL import Image, ImageOps
from pathlib import Path

# Paths
ROOT = Path("c:/Users/joaon/ptia-content-engine")
uploaded_logo = Path(r"C:\Users\joaon\.gemini\antigravity\brain\97b18b7a-bfe1-4412-bbd3-47410ebaa4bf\media__1780527456811.png")

print("=== UPDATE BRAND LOGOS ===")
print(f"Reading uploaded logo from: {uploaded_logo}")

# Load uploaded logo
img = Image.open(uploaded_logo).convert("RGBA")

# 1. Save cutout logos (the raw square logo)
cutout_path_site = ROOT / "site/assets/ptia-logo-cutout.png"
cutout_path_data = ROOT / "data/ptia-logo-cutout.png"
img.save(cutout_path_site)
img.save(cutout_path_data)
print(f"Saved logo cutout to {cutout_path_site} and {cutout_path_data}")

# 2. Generate favicons using the square logo
ico_sizes = [(16, 16), (32, 32), (48, 48)]
ico_images = [img.resize(size, Image.Resampling.LANCZOS) for size in ico_sizes]
ico_images[0].save(ROOT / "site/favicon.ico", format="ICO", sizes=ico_sizes, append_images=ico_images[1:])
img.resize((32, 32), Image.Resampling.LANCZOS).save(ROOT / "site/favicon.png", format="PNG")
img.resize((180, 180), Image.Resampling.LANCZOS).save(ROOT / "site/apple-touch-icon.png", format="PNG")
print("Generated favicon assets (favicon.ico, favicon.png, apple-touch-icon.png)")

# 3. Generate transparent monogram
# Extract white text as mask. The source is white text (255, 255, 255) on black background (0, 0, 0).
# We can use the red channel of the image as the alpha mask.
r, g, b, a = img.split()
alpha_mask = r.point(lambda p: p if p > 20 else 0)

# Get bounding box of the monogram to crop it tightly
bbox = alpha_mask.getbbox()
print(f"Monogram bounding box: {bbox}")

# Create Navy wordmark: letters are #051A3B (R=5, G=26, B=59)
navy_color = Image.new("RGBA", img.size, (5, 26, 59, 255))
navy_monogram = Image.composite(navy_color, Image.new("RGBA", img.size, (0, 0, 0, 0)), alpha_mask)

# Create Cream wordmark: letters are #FAF6EC (R=250, G=246, B=236)
cream_color = Image.new("RGBA", img.size, (250, 246, 236, 255))
cream_monogram = Image.composite(cream_color, Image.new("RGBA", img.size, (0, 0, 0, 0)), alpha_mask)

# Crop both to bounding box with padding
if bbox:
    # Adding a 20px padding around the content
    pad = 20
    cropped_bbox = (
        max(0, bbox[0] - pad),
        max(0, bbox[1] - pad),
        min(img.size[0], bbox[2] + pad),
        min(img.size[1], bbox[3] + pad)
    )
    navy_monogram = navy_monogram.crop(cropped_bbox)
    cream_monogram = cream_monogram.crop(cropped_bbox)
    print(f"Cropped monograms to padded bounding box: {cropped_bbox}")

# Save Navy wordmarks
navy_monogram.save(ROOT / "site/assets/ptia-wordmark-navy-transparent.png", format="PNG")
navy_monogram.save(ROOT / "data/ptia-wordmark-navy-transparent.png", format="PNG")

# Save Cream wordmarks
cream_monogram.save(ROOT / "site/assets/ptia-wordmark-cream-transparent.png", format="PNG")
cream_monogram.save(ROOT / "data/ptia-wordmark-cream-transparent.png", format="PNG")

print("Generated and saved transparent monogram assets in Navy and Cream colors.")
print("=== LOGO UPDATE COMPLETED SUCCESSFULLY ===")

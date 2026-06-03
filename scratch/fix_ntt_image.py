import json
import shutil
import sys
from pathlib import Path

ROOT = Path("c:/Users/joaon/ptia-content-engine")
sys.path.insert(0, str(ROOT / "src"))

from ptia_engine.dashboard import DashboardState, _sync_static_site_feed

db_path = ROOT / "data" / "final_posts.jsonl"
state = DashboardState(ROOT / "data")

print("=== FIXING NTT DATA SITE POST IMAGE ===")

# 1. Update database entry
with open(db_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

found = False
for idx, line in enumerate(lines):
    if not line.strip():
        continue
    post = json.loads(line)
    if post.get("post_id") == "post_d9cac2c3e400d579ee":
        post["image_path"] = "data\\final_assets\\post_85ef07c5efea6372b4_2d6c481b_ChatGPT-Image-2_06_2026-15_01_34.png"
        post["image_variants"] = {
            "instagram": "data\\final_assets\\post_15331982b1d6e29fa5_instagram_ptia_v7_1080x1080.jpg",
            "x": "data\\final_assets\\post_15331982b1d6e29fa5_x_ptia_v7_1080x1080.jpg",
            "linkedin": "data\\final_assets\\post_15331982b1d6e29fa5_linkedin_ptia_v7_1200x627.jpg",
            "site": "data\\final_assets\\post_15331982b1d6e29fa5_site_1600x900.jpg"
        }
        lines[idx] = json.dumps(post, ensure_ascii=False) + "\n"
        found = True
        print(f"Updated post_d9cac2c3e400d579ee with image_path and image_variants.")
        break

if found:
    with open(db_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print("Database updated.")
else:
    print("Post post_d9cac2c3e400d579ee not found in database!")

# 2. Copy image file to site assets
src_image = ROOT / "data" / "final_assets" / "post_15331982b1d6e29fa5_site_1600x900.jpg"
dst_dir = ROOT / "site" / "assets" / "final"
dst_dir.mkdir(parents=True, exist_ok=True)
dst_image = dst_dir / "post_15331982b1d6e29fa5_site_1600x900.jpg"

if src_image.exists():
    shutil.copy2(src_image, dst_image)
    print(f"Copied image to: {dst_image.relative_to(ROOT)}")
else:
    print(f"Source image NOT found: {src_image}")

# 3. Synchronize site-feed.json
_sync_static_site_feed(state)
print("Static site feed synchronized.")

import os
import sys
import shutil
import json
from pathlib import Path

ROOT = Path("c:/Users/joaon/ptia-content-engine")
sys.path.insert(0, str(ROOT / "src"))

from ptia_engine.buffer_api import BufferClient
from ptia_engine.dashboard import DashboardState, _ensure_image_variants_for_posts, load_final_posts, write_jsonl

def load_dotenv() -> None:
    env_path = ROOT / ".env.local"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

load_dotenv()

# 1. Delete the old/duplicate Buffer posts
buffer_ids_to_delete = [
    "6a24954b38e4f9ff5ce213ff",  # Anthropic LinkedIn
    "6a24954ea0f5aeb6f4dd3326",  # Anthropic X
    "6a24954fa0f5aeb6f4dd334a"   # Instagram Carousel
]

print("=== 1. DELETING OLD BUFFER POSTS ===")
client = BufferClient()
for bid in buffer_ids_to_delete:
    try:
        success = client.delete_post(bid)
        print(f"Delete Buffer ID {bid}: {'SUCCESS' if success else 'FAILED'}")
    except Exception as e:
        print(f"Error deleting Buffer ID {bid}: {e}")

# 2. Copy the user's uploaded image to the master image path
print("\n=== 2. UPDATING MASTER IMAGE ===")
src_image = Path(r"C:\Users\joaon\.gemini\antigravity\brain\97b18b7a-bfe1-4412-bbd3-47410ebaa4bf\media__1780782322666.jpg")
dest_image = ROOT / "data" / "final_assets" / "post_0357526a44045c199d_anthropic_gender_gap_ai.png"

if src_image.exists():
    shutil.copy2(src_image, dest_image)
    print(f"Successfully copied user image to {dest_image}")
else:
    print(f"[ERROR] Source image not found at {src_image}")
    sys.exit(1)

# 3. Clean up existing variant files to force regeneration
print("\n=== 3. CLEANING UP OLD VARIANT FILES ===")
# Variant pattern to delete: post_77ae0b8b14feb7bb60* in data/final_assets and site/assets/final
for parent in [ROOT / "data" / "final_assets", ROOT / "site" / "assets" / "final"]:
    if parent.exists():
        for f in parent.glob("*post_77ae0b8b14feb7bb60*"):
            try:
                f.unlink()
                print(f"Deleted old variant file: {f.name}")
            except Exception as e:
                print(f"Error deleting variant file {f.name}: {e}")

# 4. Clear image_variants and reset post status in database
print("\n=== 4. UPDATING DATABASE STATUS ===")
state = DashboardState(ROOT / "data")
posts = load_final_posts(state.final_posts_path)

target_topics = {"topic_5dd5877f89e8ae4a81", "topic_866460195a3bac2212", "topic_1a1c15db417c871cb4", "topic_6e0deb1e52630a36e9"}

for post in posts:
    topic_id = post.topic_id
    
    # For Anthropic topic, update master image path, clear variants and status
    if topic_id == "topic_866460195a3bac2212":
        post.image_path = str(dest_image)
        post.image_status = "approved"
        post.image_variants = {}
        
        # Reset LinkedIn and X post status
        if post.channel in {"linkedin", "x", "site"}:
            post.status = "approved_for_schedule"
            post.buffer_post_id = ""
            print(f"Reset database entry for Anthropic {post.channel} (ID: {post.post_id})")
            
    # Reset all Instagram posts for tomorrow's carrossel so they get re-scheduled in a new carrossel
    if post.channel == "instagram" and topic_id in target_topics:
        post.status = "approved_for_schedule"
        post.buffer_post_id = ""
        post.image_variants = {}
        print(f"Reset database entry for Instagram {post.channel} (ID: {post.post_id})")

# Write the updated records back to final_posts.jsonl
write_jsonl(state.final_posts_path, posts)
print("Database file updated.")

# 5. Regenerate variants
print("\n=== 5. REGENERATING IMAGE VARIANTS ===")
posts = load_final_posts(state.final_posts_path)
_ensure_image_variants_for_posts(state, posts)
print("Image variants successfully regenerated!")

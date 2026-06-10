import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
db_path = ROOT / "data" / "final_posts.jsonl"
dest_image = ROOT / "data" / "final_assets" / "post_0357526a44045c199d_anthropic_gender_gap_ai.png"

# Source image from user upload
src_image = Path(r"C:\Users\joaon\.gemini\antigravity\brain\97b18b7a-bfe1-4412-bbd3-47410ebaa4bf\media__1780782322666.jpg")

# Copy the image (overwriting the previous one)
shutil.copy2(src_image, dest_image)
print(f"Overwrote image at: {dest_image}")

lines = db_path.read_text(encoding="utf-8").splitlines()
updated_lines = []

target_topics = {"topic_5dd5877f89e8ae4a81", "topic_866460195a3bac2212", "topic_1a1c15db417c871cb4", "topic_6e0deb1e52630a36e9"}

for line in lines:
    if not line.strip():
        continue
    record = json.loads(line)
    post_id = record.get("post_id")
    topic_id = record.get("topic_id")
    
    # Update image path for all posts in the Anthropic topic
    if topic_id == "topic_866460195a3bac2212":
        record["image_path"] = str(dest_image)
        record["image_status"] = "approved"
        
        # Reset LinkedIn and X post status so they get rescheduled with the new image
        if record["channel"] in {"linkedin", "x"}:
            record["status"] = "approved_for_schedule"
            record["buffer_post_id"] = ""
            print(f"Resetting {record['channel']} post {post_id} status.")
            
    # Reset all Instagram posts for tomorrow so the carrossel is regenerated with the new image
    if record.get("channel") == "instagram" and topic_id in target_topics:
        record["status"] = "approved_for_schedule"
        record["buffer_post_id"] = ""
        print(f"Resetting Instagram post {post_id} status.")
        
    updated_lines.append(json.dumps(record, ensure_ascii=False))

db_path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")
print("Database updated successfully.")

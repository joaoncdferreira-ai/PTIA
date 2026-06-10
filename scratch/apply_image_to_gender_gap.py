import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
db_path = ROOT / "data" / "final_posts.jsonl"
assets_dir = ROOT / "data" / "final_assets"

# Source image from brain folder
src_image = Path(r"C:\Users\joaon\.gemini\antigravity\brain\97b18b7a-bfe1-4412-bbd3-47410ebaa4bf\anthropic_gender_gap_ai_1780781666893.png")
dest_image = assets_dir / "post_0357526a44045c199d_anthropic_gender_gap_ai.png"

# Copy the image
assets_dir.mkdir(parents=True, exist_ok=True)
shutil.copy2(src_image, dest_image)
print(f"Copied image to: {dest_image}")

lines = db_path.read_text(encoding="utf-8").splitlines()
updated_lines = []

for line in lines:
    if not line.strip():
        continue
    record = json.loads(line)
    topic_id = record.get("topic_id")
    if topic_id == "topic_866460195a3bac2212":
        record["image_path"] = str(dest_image)
        record["image_status"] = "approved"
        # Reset the failed X post so it gets scheduled
        if record["channel"] == "x":
            record["status"] = "approved_for_schedule"
            print(f"Resetting X post status to approved_for_schedule.")
    updated_lines.append(json.dumps(record, ensure_ascii=False))

db_path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")
print("Database updated successfully.")

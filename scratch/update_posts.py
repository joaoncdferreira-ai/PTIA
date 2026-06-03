import json
import shutil
from pathlib import Path

ROOT = Path("c:/Users/joaon/ptia-content-engine")
db_path = ROOT / "data" / "final_posts.jsonl"
backup_path = db_path.with_name("final_posts.jsonl.bak_pre_polish_20260602")

# Create a safe backup first
shutil.copy2(db_path, backup_path)
print(f"Created backup at {backup_path}")

posts = []
with open(db_path, "r", encoding="utf-8") as f:
    for line in f:
        if line.strip():
            posts.append(json.loads(line))

updated_count = 0
for post in posts:
    # 1. Google Cloud Site Post
    if post.get("post_id") == "post_d9cac2c3e400d579ee":
        post["status"] = "approved_for_schedule"
        print(f"Updated Google Cloud Site Post status to approved_for_schedule.")
        updated_count += 1
    
    # 2. Google Cloud X Post
    elif post.get("post_id") == "post_cf02ffcea47c0706f1":
        new_body = (
            "A APCC, a Google Cloud e a NTT Data lançaram a Retail Spaces AI Academy para formar o setor de retalho "
            "nacional em IA. A batalha pela adoção ganha-se na integração invisível e no hábito diário das equipas."
        )
        post["body"] = new_body
        post["status"] = "approved_for_schedule"
        print(f"Updated Google Cloud X Post body and status.")
        updated_count += 1
        
    # 3. NVIDIA & Foxconn X Post
    elif post.get("post_id") == "post_f99b6bed5ef16caf31":
        new_body = (
            "A NVIDIA e a Foxconn aliam-se a centros médicos em Taiwan para lançar forças de trabalho de agentes de "
            "IA na saúde. A parceria realça que a revolução dos agentes exige infraestrutura física e semicondutores robustos."
        )
        post["body"] = new_body
        post["status"] = "approved_for_schedule"
        print(f"Updated NVIDIA & Foxconn X Post body and status.")
        updated_count += 1

# Write back
with open(db_path, "w", encoding="utf-8") as f:
    for post in posts:
        f.write(json.dumps(post, ensure_ascii=False) + "\n")

print(f"Database updated. Total modifications: {updated_count}")

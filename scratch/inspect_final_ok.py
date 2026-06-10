import json
from pathlib import Path

def main():
    posts_path = Path("data/final_posts.jsonl")
    if not posts_path.exists():
        print("final_posts.jsonl not found")
        return
        
    posts = [json.loads(line) for line in posts_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    approved = [p for p in posts if p.get("status") == "approved_for_schedule"]
    print(f"Total approved posts: {len(approved)}")
    for p in approved:
        print(f"- ID: {p.get('post_id')}, Topic: {p.get('topic_id')}, Channel: {p.get('channel')}, Title: {p.get('title')}")

if __name__ == "__main__":
    main()

import json
from pathlib import Path

def main():
    posts_path = Path("data/final_posts.jsonl")
    if not posts_path.exists():
        print("final_posts.jsonl not found")
        return
        
    posts = [json.loads(line) for line in posts_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    x_posts = [p for p in posts if p.get("channel") == "x" and p.get("status") == "approved_for_schedule"]
    print(f"Found {len(x_posts)} approved X posts:")
    for p in x_posts:
        print(f"--- Post ID: {p.get('post_id')} | Topic: {p.get('topic_id')} ---")
        print(f"Body: {repr(p.get('body'))}")
        print(f"Hashtags: {p.get('hashtags')}")

if __name__ == "__main__":
    main()

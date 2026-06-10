import json

posts = []
with open('data/final_posts.jsonl', 'r', encoding='utf-8') as f:
    for line in f:
        if line.strip():
            posts.append(json.loads(line))

tomorrow_posts = [p for p in posts if p.get('scheduled_time', '') and p.get('scheduled_time', '').startswith('2026-06-05')]
for p in tomorrow_posts:
    print(f"Post ID: {p.get('post_id')}")
    print(f"  Channel: {p.get('channel')}")
    print(f"  Status: {p.get('status')}")
    print(f"  Scheduled Time: {p.get('scheduled_time')}")
    print(f"  Buffer ID: {p.get('buffer_post_id')}")
    print(f"  Notes: {p.get('notes')}")
    print("-" * 40)

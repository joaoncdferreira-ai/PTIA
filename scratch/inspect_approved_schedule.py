import json
import os
from pathlib import Path

posts = []
with open('data/final_posts.jsonl', 'r', encoding='utf-8') as f:
    for line in f:
        if line.strip():
            posts.append(json.loads(line))

tomorrow_posts = [p for p in posts if p.get('scheduled_time', '') and p.get('scheduled_time', '').startswith('2026-06-05')]
site_posts = [p for p in tomorrow_posts if p.get('channel') == 'site']

print(f"Checking {len(site_posts)} site posts for tomorrow:")
for p in site_posts:
    post_id = p.get('post_id')
    title = p.get('title')
    # Let's inspect the fields in the post JSON
    print(f"\nPost ID: {post_id}")
    print(f"  Title: {title}")
    print(f"  Url Path: {p.get('url_path')}")
    print(f"  Image Path: {p.get('image_path')}")
    
    # Check if files exist
    url_path = p.get('url_path')
    if url_path:
        # e.g. "artigos/slug/"
        full_path = Path("site") / url_path / "index.html"
        print(f"  Checking page path: {full_path} -> Exists? {full_path.exists()}")
    else:
        print("  No url_path defined for this site post!")

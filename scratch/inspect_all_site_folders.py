import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ptia_engine.services.site import article_url_for_site_post
from ptia_engine.models import FinalPost

posts = []
with open('data/final_posts.jsonl', 'r', encoding='utf-8') as f:
    for line in f:
        if line.strip():
            posts.append(json.loads(line))

site_posts = [FinalPost(**p) for p in posts if p.get('channel') == 'site' and p.get('status') in {'scheduled', 'published'}]

print(f"Total site posts in DB: {len(site_posts)}")
exists_count = 0
missing_count = 0

for p in sorted(site_posts, key=lambda x: x.scheduled_time or ""):
    url_path = article_url_for_site_post(p)
    full_path = Path("site") / url_path
    exists = full_path.exists()
    if exists:
        exists_count += 1
    else:
        missing_count += 1
    print(f"  - {p.post_id} | Scheduled: {p.scheduled_time} | Status: {p.status} | Folder: {url_path} | Exists? {exists}")

print(f"\nSummary: Exists: {exists_count}, Missing: {missing_count}")

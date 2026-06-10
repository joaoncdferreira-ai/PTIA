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

tomorrow_posts = [p for p in posts if p.get('scheduled_time', '') and p.get('scheduled_time', '').startswith('2026-06-05')]
site_posts = [FinalPost(**p) for p in tomorrow_posts if p.get('channel') == 'site']

print(f"Checking physical folders for {len(site_posts)} site posts:")
for p in site_posts:
    url_path = article_url_for_site_post(p)
    full_path = Path("site") / url_path
    print(f"Post {p.post_id}: slug={url_path} -> Exists? {full_path.exists()}")

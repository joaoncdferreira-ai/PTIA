import json
from collections import Counter

posts = []
with open('data/final_posts.jsonl', 'r', encoding='utf-8') as f:
    for line in f:
        if line.strip():
            posts.append(json.loads(line))

scheduled = [p for p in posts if p.get('status') == 'scheduled']
print(f"Total scheduled posts: {len(scheduled)}")

print("\nScheduled times distribution (top 20):")
times = [p.get('scheduled_time', 'N/A') for p in scheduled]
for k, v in Counter(times).most_common(20):
    print(f"  {k}: {v}")

print("\nScheduled posts for other dates (preview):")
for p in scheduled[:15]:
    print(f"  - {p.get('post_id')} ({p.get('channel')}): {p.get('scheduled_time')} | Topic: {p.get('topic_id')} | Title: {p.get('title')[:30]}")

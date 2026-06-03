import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

comments_file = r"c:\Users\joaon\ptia-content-engine\data\linkedin_comments.jsonl"

comments = []
with open(comments_file, 'r', encoding='utf-8') as f:
    for line in f:
        try:
            obj = json.loads(line)
            if obj.get('comment_text'):
                comments.append(obj)
        except Exception:
            pass

print(f"Found {len(comments)} generated comments in the database:")
for idx, c in enumerate(comments, 1):
    print(f"\n[{idx}] Profile: {c.get('profile_name')}")
    print(f"Status: {c.get('status')}")
    print(f"Created: {c.get('created_at')}")
    print(f"Post URL: {c.get('post_url')}")
    body_preview = c.get('post_body', '')[:120].replace('\n', ' ') + "..."
    print(f"Post Preview: {body_preview}")
    print(f"Comment Text: {c.get('comment_text')}")

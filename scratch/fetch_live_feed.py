import urllib.request
import json

url = "https://ptia.pt/site-feed.json"
print(f"=== FETCHING {url} ===")
try:
    with urllib.request.urlopen(url) as response:
        content = response.read().decode("utf-8")
        payload = json.loads(content)
        posts = payload.get("posts", [])
        print(f"Total posts in live feed: {len(posts)}")
        for p in posts[:10]:
            print(f"ID: {p.get('id')} | Title: {p.get('title')[:50]} | PublishedAt: {p.get('published_at')}")
except Exception as e:
    print("Error:", e)

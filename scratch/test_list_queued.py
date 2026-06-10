import os
import sys
import json
from pathlib import Path

ROOT = Path("c:/Users/joaon/ptia-content-engine")
sys.path.insert(0, str(ROOT / "src"))

from ptia_engine.buffer_api import BufferClient

def load_dotenv() -> None:
    env_path = ROOT / ".env.local"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

load_dotenv()
client = BufferClient()

org_id = "6a06f865975a114e1d194d52"
linkedin_id = "6a07030a090476fb9921cacc"

query = """
query GetPosts($input: PostsInput!) {
  posts(input: $input) {
    edges {
      node {
        id
        text
        status
        dueAt
      }
    }
  }
}
"""

try:
    input_payload = {
        "organizationId": org_id,
        "filter": {
            "channelIds": [linkedin_id]
        }
    }
    res = client._graphql(query, {"input": input_payload})
    edges = res.get("data", {}).get("posts", {}).get("edges", [])
    print(f"Total posts: {len(edges)}")
    for edge in edges:
        p = edge.get("node") or {}
        print(f"ID: {p.get('id')} | Status: {p.get('status')} | DueAt: {p.get('dueAt')} | Text: {p.get('text', '')[:60]}")
except Exception as e:
    print("Error:", e)

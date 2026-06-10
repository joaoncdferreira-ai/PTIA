import json
import os
from pathlib import Path
import sys

ROOT = Path("c:/Users/joaon/ptia-content-engine")
sys.path.insert(0, str(ROOT / "src"))

def load_dotenv():
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

from ptia_engine.buffer_api import BufferClient

client = BufferClient()
post_id = "6a27048d9d09a94011d599c6"
print(f"Buscando post ID: {post_id} ...")
try:
    details = client.get_post(post_id)
    print("Sucesso!")
    print(f"ID: {details.id}")
    print(f"Status: {details.status}")
    print(f"Due At: {details.due_at}")
    print(f"External Link: {details.external_link}")
    print(f"Channel ID: {details.channel_id}")
    print(f"Channel Service: {details.channel_service}")
    print(f"Text:\n{details.text}")
except Exception as e:
    print(f"Erro: {e}")

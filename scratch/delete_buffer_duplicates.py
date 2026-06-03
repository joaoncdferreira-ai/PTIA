import os
import sys
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

buffer_ids_to_delete = [
    "6a1f56cdcf22acc174c79444",  # Bain LinkedIn (scheduled at 12:00 instead of 13:00)
    "6a1f56fa59a23d518d8c1c19",  # Bain X (scheduled at 12:00 instead of 13:00)
    "6a1f56fa4c5ee6e0b426229e"   # Combined Instagram Carousel (2-slide at 12:00 instead of 4-slide at 21:00)
]

print("=== DELETING DUPLICATE BUFFER POSTS ===")
client = BufferClient()
for bid in buffer_ids_to_delete:
    try:
        success = client.delete_post(bid)
        print(f"Delete Buffer ID {bid}: {'SUCCESS' if success else 'FAILED'}")
    except Exception as e:
        print(f"Error deleting Buffer ID {bid}: {e}")

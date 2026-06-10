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

ids_to_check = [
    "6a249196ba6da2e70f71adc4",  # First run LinkedIn
    "6a24954b38e4f9ff5ce213ff",  # Second run LinkedIn
    "6a2496c238e4f9ff5ce216fa",  # Third run LinkedIn (should be sent)
    "6a24954ea0f5aeb6f4dd3326",  # Second run X
    "6a2496e6ba6da2e70f71beeb",  # Third run X (should be sent)
]

print("=== CHECKING POST STATUS IN BUFFER ===")
for bid in ids_to_check:
    try:
        details = client.get_post(bid)
        print(f"ID: {bid} | Status: {details.status} | Time: {details.due_at} | Text: {details.text[:50]}")
    except Exception as e:
        print(f"ID: {bid} | Error: {e}")

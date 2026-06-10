import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

sys_path = Path("data/linkedin_comments.jsonl")
if sys_path.exists():
    with sys_path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                item = json.loads(line)
                if item.get("status") == "draft":
                    print("Raw keys and values:")
                    for k, v in item.items():
                        print(f"  {k}: {repr(v)}")
                    break
else:
    print("data/linkedin_comments.jsonl does not exist.")

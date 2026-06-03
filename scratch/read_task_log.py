import os
from pathlib import Path

log_path = Path(r"C:\Users\joaon\.gemini\antigravity\brain\97b18b7a-bfe1-4412-bbd3-47410ebaa4bf\.system_generated\tasks\task-5591.log")

if log_path.exists():
    print(f"File exists! Size: {log_path.stat().st_size} bytes")
    try:
        content = log_path.read_text(encoding="utf-8")
        print("\n=== LOG CONTENT ===")
        print(content)
    except Exception as e:
        print(f"Error reading file: {e}")
else:
    print(f"File {log_path} does not exist on disk.")

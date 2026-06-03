import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

log_path = r"C:\Users\joaon\.gemini\antigravity\brain\97b18b7a-bfe1-4412-bbd3-47410ebaa4bf\.system_generated\logs\transcript.jsonl"

found = []
with open(log_path, 'r', encoding='utf-8') as f:
    for line in f:
        try:
            obj = json.loads(line)
            obj_str = json.dumps(obj)
            if "test" in obj_str or "pytest" in obj_str:
                if obj.get('type') == 'RUN_COMMAND':
                    found.append(obj)
        except Exception:
            pass

print(f"Found {len(found)} RUN_COMMAND steps referencing test:")
for idx, s in enumerate(found[-10:], 1):
    print(f"[{idx}] Step {s.get('step_index')}: {s.get('content')}")

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
            if "pytest" in obj_str:
                found.append(obj)
        except Exception:
            pass

print(f"Found {len(found)} steps referencing pytest in the entire log:")
for idx, s in enumerate(found[:15], 1):
    print(f"\n[{idx}] Step {s.get('step_index')}: (Type: {s.get('type')}, Source: {s.get('source')})")
    print(f"Content: {str(s.get('content'))[:350]}...")
    if 'tool_calls' in s:
        for tc in s['tool_calls']:
            print(f"  Tool: {tc.get('name')} | Args: {tc.get('arguments')}")

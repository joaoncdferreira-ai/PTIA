import json
import sys

# Force stdout to be utf-8
sys.stdout.reconfigure(encoding='utf-8')

log_path = r"C:\Users\joaon\.gemini\antigravity\brain\97b18b7a-bfe1-4412-bbd3-47410ebaa4bf\.system_generated\logs\transcript.jsonl"

steps = []
with open(log_path, 'r', encoding='utf-8') as f:
    for line in f:
        try:
            obj = json.loads(line)
            if obj.get('step_index') >= 5330:
                steps.append(obj)
        except Exception:
            pass

for s in steps:
    print(f"=== STEP {s.get('step_index')} ({s.get('source')} - {s.get('type')}) ===")
    print(s.get('content'))
    if 'tool_calls' in s:
        print(f"Tool Calls: {len(s['tool_calls'])}")
        for tc in s['tool_calls']:
            print(f"  {tc.get('name')}: {tc.get('arguments')}")

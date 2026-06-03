import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

log_path = r"C:\Users\joaon\.gemini\antigravity\brain\97b18b7a-bfe1-4412-bbd3-47410ebaa4bf\.system_generated\logs\transcript.jsonl"

steps = []
with open(log_path, 'r', encoding='utf-8') as f:
    for line in f:
        try:
            obj = json.loads(line)
            # Gather steps starting from 5300
            if obj.get('step_index') >= 5300:
                steps.append(obj)
        except Exception:
            pass

# Let's search for USER_INPUT and the following MODEL steps
for i, s in enumerate(steps):
    if s.get('type') == 'USER_INPUT':
        print(f"\n--- USER [{s.get('step_index')}] ---")
        print(s.get('content'))
        # find the next non-system step or the next model response
        j = i + 1
        while j < len(steps):
            next_s = steps[j]
            if next_s.get('source') == 'MODEL' and next_s.get('content') is not None:
                print(f"--- MODEL REPLY [{next_s.get('step_index')}] ---")
                print(next_s.get('content'))
                break
            j += 1

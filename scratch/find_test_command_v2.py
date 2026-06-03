import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

log_path = r"C:\Users\joaon\.gemini\antigravity\brain\97b18b7a-bfe1-4412-bbd3-47410ebaa4bf\.system_generated\logs\transcript.jsonl"

found = []
with open(log_path, 'r', encoding='utf-8') as f:
    for line in f:
        try:
            obj = json.loads(line)
            tool_calls = obj.get('tool_calls', [])
            for tc in tool_calls:
                name = tc.get('name', '')
                args = str(tc.get('arguments', ''))
                if name == 'run_command' and ('test' in args or 'pytest' in args or 'venv' in args):
                    found.append((obj.get('step_index'), args))
        except Exception:
            pass

print(f"Found {len(found)} RUN_COMMAND tool calls referencing test/pytest/venv:")
for step_idx, args in found[-15:]:
    print(f"Step {step_idx}: {args}")

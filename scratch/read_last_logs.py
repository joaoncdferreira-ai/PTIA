import json

log_path = r"C:\Users\joaon\.gemini\antigravity\brain\97b18b7a-bfe1-4412-bbd3-47410ebaa4bf\.system_generated\logs\transcript.jsonl"

user_messages = []
with open(log_path, 'r', encoding='utf-8') as f:
    for line in f:
        try:
            obj = json.loads(line)
            if obj.get('type') == 'USER_INPUT':
                user_messages.append(obj)
        except Exception:
            pass

print("Last 15 User Messages:")
for msg in user_messages[-15:]:
    print(f"[{msg.get('step_index')}] {msg.get('content')}")

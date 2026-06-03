import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

log_path = r"C:\Users\joaon\.gemini\antigravity\brain\97b18b7a-bfe1-4412-bbd3-47410ebaa4bf\.system_generated\logs\transcript.jsonl"

found = []
with open(log_path, 'r', encoding='utf-8') as f:
    for line in f:
        try:
            obj = json.loads(line)
            # convert object to string representation to search
            obj_str = json.dumps(obj)
            if "linkedin_comments_report.pdf" in obj_str or "weasyprint" in obj_str:
                found.append(obj)
        except Exception:
            pass

print(f"Found {len(found)} steps referencing pdf/weasyprint:")
for idx, s in enumerate(found[-10:], 1):
    print(f"\n[{idx}] Step: {s.get('step_index')} (Source: {s.get('source')}, Type: {s.get('type')})")
    # print first 300 characters of content
    print(f"Content: {str(s.get('content'))[:300]}...")
    if 'tool_calls' in s:
        for tc in s['tool_calls']:
            print(f"  Tool Call Name: {tc.get('name')}")
            # print arguments preview
            print(f"  Tool Call Args: {str(tc.get('arguments'))[:200]}")

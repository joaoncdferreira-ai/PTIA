import pathlib
import json

for f in pathlib.Path('data').glob('*.jsonl'):
    print(f"Checking {f}...")
    try:
        content = f.read_text(encoding='utf-8')
    except Exception as e:
        print(f"Error reading {f}: {e}")
        continue
    for i, line in enumerate(content.splitlines(), 1):
        line_s = line.strip()
        if not line_s:
            continue
        try:
            json.loads(line_s)
        except Exception as e:
            print(f"Error in {f} line {i}: {e}")
            print(f"Content: {repr(line_s[:100])}...")

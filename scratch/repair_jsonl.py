import pathlib
import json

path = pathlib.Path("data/final_posts.jsonl")
backup_path = pathlib.Path("data/final_posts.jsonl.corrupted_backup")

if not path.exists():
    print("File does not exist.")
    exit(1)

print(f"Reading {path}...")
lines = path.read_text(encoding="utf-8").splitlines()

valid_lines = []
corrupted_count = 0

for i, line in enumerate(lines, 1):
    line_s = line.strip()
    if not line_s:
        continue
    try:
        json.loads(line_s)
        valid_lines.append(line_s)
    except Exception as e:
        print(f"Removing corrupted line {i}: {e}")
        print(f"Corrupted content: {repr(line_s)}")
        corrupted_count += 1

if corrupted_count > 0:
    print(f"Found {corrupted_count} corrupted lines. Creating backup at {backup_path}...")
    path.rename(backup_path)
    
    print(f"Writing {len(valid_lines)} valid lines to {path}...")
    with path.open("w", encoding="utf-8") as f:
        for line in valid_lines:
            f.write(line + "\n")
    print("Repair complete!")
else:
    print("No corruption found. Nothing to repair.")

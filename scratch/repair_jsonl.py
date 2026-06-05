import json
import re
from pathlib import Path

ROOT = Path("c:/Users/joaon/ptia-content-engine")
db_path = ROOT / "data/final_posts.jsonl"
backup_path = ROOT / "data/final_posts.jsonl.corrupted_backup"

print("=== REPAIR JSONL DATABASE ===")

if not db_path.exists():
    print(f"Database not found at {db_path}")
    sys.exit(1)

# Make a backup first
if not backup_path.exists():
    backup_path.write_bytes(db_path.read_bytes())
    print(f"Created a backup of corrupted database at {backup_path}")

with open(db_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

reconstructed_posts = []
corrupted_lines_indices = []

for idx, line in enumerate(lines, 1):
    if not line.strip():
        continue
    try:
        obj = json.loads(line)
        reconstructed_posts.append(obj)
    except json.JSONDecodeError as e:
        corrupted_lines_indices.append(idx)
        print(f"\nCorrupted Line {idx}: {e}")
        # Find all occurrences of {"post_id":
        # We split by '{"post_id":'
        parts = line.split('{"post_id":')
        for part_idx, part in enumerate(parts):
            if not part.strip():
                continue
            # Reconstruct the string
            candidate_str = '{"post_id":' + part.strip()
            # If it doesn't end with }, it might be truncated. Let's see if we can find a matching closing brace.
            # Try to load it. If it fails, try to trim it until it is valid or discard it.
            parsed_ok = False
            # We try parsing candidate_str directly
            try:
                obj = json.loads(candidate_str)
                reconstructed_posts.append(obj)
                print(f"  -> Successfully recovered complete JSON object: {obj.get('post_id')} ({obj.get('channel')})")
                parsed_ok = True
            except json.JSONDecodeError:
                # Try trimming trailing characters (e.g. if it has extra characters at the end before the next object)
                # Or try to add closing braces if it was truncated
                # Let's try to find if there is a valid JSON sub-prefix
                # We can iteratively remove characters from the end
                temp_str = candidate_str
                while len(temp_str) > 20:
                    # Find last index of }
                    last_brace = temp_str.rfind('}')
                    if last_brace == -1:
                        break
                    temp_str = temp_str[:last_brace+1]
                    try:
                        obj = json.loads(temp_str)
                        reconstructed_posts.append(obj)
                        print(f"  -> Recovered trimmed JSON object: {obj.get('post_id')} ({obj.get('channel')})")
                        parsed_ok = True
                        break
                    except json.JSONDecodeError:
                        # Continue searching for earlier closing braces
                        temp_str = temp_str[:-1]
                
                if not parsed_ok:
                    print(f"  -> Could not recover truncated part: {candidate_str[:120]}...")

print(f"\nTotal lines processed: {len(lines)}")
print(f"Corrupted lines found: {len(corrupted_lines_indices)} (Lines: {corrupted_lines_indices})")
print(f"Total valid posts recovered: {len(reconstructed_posts)}")

# Save the repaired database
repaired_path = ROOT / "data/final_posts.jsonl"
with open(repaired_path, "w", encoding="utf-8") as f:
    for post in reconstructed_posts:
        f.write(json.dumps(post, ensure_ascii=False) + "\n")

print(f"\nSUCCESS: Saved repaired database to {repaired_path}")

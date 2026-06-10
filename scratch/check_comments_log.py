import sys
from pathlib import Path

# Reconfigure stdout to use UTF-8
sys.stdout.reconfigure(encoding='utf-8')

log_path = Path("data/linkedin_comments_run.log")
if log_path.exists():
    lines = log_path.read_text(encoding="utf-8").splitlines()
    print(f"Total lines in log: {len(lines)}")
    print("\nLast 50 lines of data/linkedin_comments_run.log:")
    for line in lines[-50:]:
        print(line)
else:
    print("data/linkedin_comments_run.log does not exist.")

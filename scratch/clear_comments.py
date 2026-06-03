from pathlib import Path

ROOT = Path("c:/Users/joaon/ptia-content-engine")
comments_file = ROOT / "data" / "linkedin_comments.jsonl"

if comments_file.exists():
    # Clear the file content
    with open(comments_file, "w", encoding="utf-8") as f:
        f.write("")
    print(f"Successfully cleared all previous comments from: {comments_file}")
else:
    print(f"Comments file does not exist, nothing to clear: {comments_file}")

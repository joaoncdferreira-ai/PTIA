from pathlib import Path

ROOT = Path("c:/Users/joaon/ptia-content-engine")
posts_file = ROOT / "data/final_posts.jsonl"

with open(posts_file, "rb") as f:
    for i, line in enumerate(f):
        if b"topic_bea871e53735138a7c" in line:
            # print line number and sample bytes around corrupted chars
            print(f"Line {i+1}:")
            # find where b"prote" is
            idx = line.find(b"prote")
            if idx != -1:
                print(line[idx:idx+20])

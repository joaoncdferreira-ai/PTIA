import json
from pathlib import Path

def main():
    posts_path = Path("data/final_posts.jsonl")
    if not posts_path.exists():
        print("final_posts.jsonl not found")
        return
        
    lines = posts_path.read_text(encoding="utf-8").splitlines()
    updated_lines = []
    
    # We want to map:
    # linkedin: post_d86030d2d777f0c2a3
    # instagram: post_4f7c54afe11be6f3d8
    # site: post_41d383cb55bb5faa9d
    # x: post_0cf56cf36dc3a54295
    
    replacements = {
        "post_d86030d2d777f0c2a3": "Trump pondera participação estatal em empresas de IA: um novo capítulo para a política industrial",
        "post_4f7c54afe11be6f3d8": "Trump quer entrar no capital das Big Tech de IA",
        "post_41d383cb55bb5faa9d": "Trump Pondera Entrada do Estado em Empresas de Inteligência Artificial",
        "post_0cf56cf36dc3a54295": "Trump Pondera Entrada do Estado em Empresas de Inteligência Artificial"
    }
    
    count = 0
    for line in lines:
        if not line.strip():
            continue
        post = json.loads(line)
        pid = post.get("post_id")
        if pid in replacements:
            old_title = post["title"]
            new_title = replacements[pid]
            post["title"] = new_title
            print(f"Updating post {pid} ({post.get('channel')}):")
            print(f"  Old: {old_title}")
            print(f"  New: {new_title}")
            count += 1
        updated_lines.append(json.dumps(post, ensure_ascii=False))
        
    posts_path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")
    print(f"\nSuccessfully updated {count} posts.")

if __name__ == "__main__":
    main()

import json
from pathlib import Path
import sys

ROOT = Path("c:/Users/joaon/ptia-content-engine")
sys.path.insert(0, str(ROOT / "src"))

from ptia_engine.storage import load_final_posts, write_jsonl
from ptia_engine.services.editorial_hygiene import apply_ptia_editorial_rules

posts = load_final_posts(ROOT / "data/final_posts.jsonl")

plan_topic_ids = {
    "topic_bea871e53735138a7c",
    "topic_9f608c63c7c00e7174",
    "topic_847f4f1387a2651eee",
    "topic_5324eae70c3277eb71",
}

updated_count = 0
for post in posts:
    if post.status == "approved_for_schedule" and post.topic_id in plan_topic_ids:
        old_body = post.body
        old_title = post.title
        
        # Correr as regras editoriais actualizadas
        clean_title, clean_body = apply_ptia_editorial_rules(post.title, post.body, post.channel)
        
        if clean_body != old_body or clean_title != old_title:
            post.body = clean_body
            post.title = clean_title
            updated_count += 1
            print(f"Saneado post {post.post_id} ({post.channel})")

if updated_count > 0:
    write_jsonl(ROOT / "data/final_posts.jsonl", posts)
    print(f"Sucesso: {updated_count} posts saneados na base de dados.")
else:
    print("Nenhum post precisou de alterações adicionais.")

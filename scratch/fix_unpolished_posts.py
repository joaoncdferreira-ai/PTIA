import json
import os
from pathlib import Path
import sys

ROOT = Path("c:/Users/joaon/ptia-content-engine")
sys.path.insert(0, str(ROOT / "src"))

def load_dotenv():
    env_path = ROOT / ".env.local"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

load_dotenv()

from ptia_engine.storage import load_final_posts, write_jsonl
from ptia_engine.services.editorial_hygiene import apply_ptia_editorial_rules
from ptia_engine.services.gemini import polish_final_post_copy
from ptia_engine.search_providers import GeminiGroundedSearchProvider

posts = load_final_posts(ROOT / "data/final_posts.jsonl")

target_topics = {
    "topic_84c837ac4930992e12",
    "topic_d0d01b1d0755c68998",
}

# 1. Agrupar posts por tópico e canal
posts_by_topic = {}
for post in posts:
    if post.topic_id in target_topics:
        if post.topic_id not in posts_by_topic:
            posts_by_topic[post.topic_id] = {}
        posts_by_topic[post.topic_id][post.channel] = post

provider = GeminiGroundedSearchProvider()
updated_count = 0

for topic_id, channels in posts_by_topic.items():
    linkedin_post = channels.get("linkedin")
    if not linkedin_post:
        print(f"[ERRO] LinkedIn post em falta para o tópico {topic_id}")
        continue
    
    print("=" * 80)
    print(f"Tópico: {topic_id}")
    print(f"Base LinkedIn Title: {linkedin_post.title}")
    
    # Canais a polir baseando-se no LinkedIn
    for channel in ["instagram", "site", "x"]:
        post_to_fix = channels.get(channel)
        if not post_to_fix:
            print(f"   [AVISO] Post de {channel} em falta para o tópico {topic_id}")
            continue
            
        # Verificar se está com o placeholder
        is_placeholder = "A fonte publicou uma nova" in post_to_fix.body or post_to_fix.title.startswith("http")
        
        if is_placeholder:
            print(f"   A polir post de {channel.upper()}...")
            # Correr o polimento com o Gemini, usando a cópia do LinkedIn polido como ponto de partida
            polished = polish_final_post_copy(
                channel=channel,
                title=linkedin_post.title,
                body=linkedin_post.body,
                hashtags=linkedin_post.hashtags or "#IA #PTIA",
                source_urls=linkedin_post.source_urls,
                provider=provider,
                apply_editorial_rules=apply_ptia_editorial_rules,
            )
            
            old_title = post_to_fix.title
            old_body = post_to_fix.body
            
            post_to_fix.title = polished["title"]
            post_to_fix.body = polished["body"]
            if polished.get("hashtags"):
                from ptia_engine.services.editorial_hygiene import normalise_hashtags
                post_to_fix.hashtags = normalise_hashtags(polished["hashtags"], channel)
            post_to_fix.editor_notes = f"[AUTO-FIX] {polished['editor_notes']}"
            
            print(f"      [OK] Antigo Título: {old_title[:40]} -> Novo Título: {post_to_fix.title}")
            print(f"      [OK] Novo Corpo (início): {post_to_fix.body[:120]}...")
            updated_count += 1
        else:
            print(f"   Post de {channel.upper()} já parece polido.")

if updated_count > 0:
    write_jsonl(ROOT / "data/final_posts.jsonl", posts)
    print(f"\nSucesso: {updated_count} posts de placeholders corrigidos e gravados.")
else:
    print("\nNenhum post precisou de correção de placeholder.")

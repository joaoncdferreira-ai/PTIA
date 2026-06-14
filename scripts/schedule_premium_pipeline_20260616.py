from __future__ import annotations

import json
import os
import shutil
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

# Configurar stdout para UTF-8 para evitar erros de encoding no Windows
sys.stdout.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# Configurar a variável de ambiente para usar a CDN pública do GitHub
os.environ["PTIA_PUBLIC_ASSET_BASE_URL"] = "https://raw.githubusercontent.com/joaoncdferreira-ai/PTIA/main/site"

import ptia_engine.dashboard as dashboard_module
from ptia_engine.dashboard import (
    DashboardState,
    _channel_enabled,
    _copy_image_to_public_site_assets,
    _public_image_url_for_buffer,
    _public_url_available,
    _publish_site_assets_to_git,
    _schedule_post_in_buffer,
    load_final_posts,
    update_final_post_status,
    update_final_post_copy,
    _sync_static_site_feed
)
from ptia_engine.models import FinalPost
from ptia_engine.buffer_api import BufferClient

def load_dotenv() -> None:
    env_path = ROOT / ".env.local"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

# Plano de agendamento cronológico para amanhã (16 de Junho de 2026)
PLAN = [
    ("topic_1ab3dae66e6a9c88ec", "2026-06-16T09:00:00+01:00"),  # Visa e OpenAI
    ("topic_b35c96b074a01d441f", "2026-06-16T13:00:00+01:00"),  # Seguro - IA na Justiça
    ("topic_4b3b62db06f6eec116", "2026-06-16T16:00:00+01:00"),  # DeepMind - Interação de Agentes
]

def main() -> None:
    load_dotenv()
    print("=== INICIANDO AGENDAMENTO EDITORIAL PREMIUM (2026-06-16) ===")
    state = DashboardState(ROOT / "data")
    
    # 1. Efetuar Backup da base de dados local
    backup_path = state.final_posts_path.with_name(
        f"final_posts.jsonl.bak_before_schedule_{datetime.now():%Y%m%d_%H%M%S}"
    )
    shutil.copy2(state.final_posts_path, backup_path)
    print(f"-> Backup de segurança efetuado em: {backup_path.name}")

    # Recarregar posts
    posts = load_final_posts(state.final_posts_path)

    # 2. Filtrar posts em "approved_for_schedule" ou "scheduled" para os tópicos do plano
    target_topic_ids = {topic_id for topic_id, _ in PLAN}
    relevant = [
        post
        for post in posts
        if post.status in {"approved_for_schedule", "scheduled"}
        and post.topic_id in target_topic_ids
    ]
    
    print(f"-> Detetados {len(relevant)} posts relevantes aprovados para agendamento.")
    
    # Agrupar posts por tópico
    posts_by_topic = {topic_id: [] for topic_id, _ in PLAN}
    for post in relevant:
        posts_by_topic[post.topic_id].append(post)

    # 3. Validar integridade dos pacotes
    for topic_id, scheduled_time in PLAN:
        package = posts_by_topic[topic_id]
        channels_str = ",".join(p.channel for p in package)
        print(f"   Tópico {topic_id} ({scheduled_time[-14:-6]}): {len(package)} posts ({channels_str})")
        if len(package) == 0:
            print(f"   [AVISO] Tópico {topic_id} não possui posts aprovados.")

    # 4. Preparar e publicar imagens no repositório de assets públicos do Git
    print("-> A copiar e publicar imagens variantes de todos os posts sociais no Git...")
    # Apenas copiar imagens de canais que vamos agendar agora (LinkedIn, X)
    social_posts = [p for p in relevant if p.channel in {"linkedin", "x"} and p.image_path]
    public_paths = []
    for post in social_posts:
        path = _copy_image_to_public_site_assets(state, post)
        if path:
            public_paths.append(path)
            
    print(f"   {len(public_paths)} imagens copiadas localmente para site/assets/final.")
    
    # Commitar e empurrar (push) para o GitHub para expor em URL público
    if public_paths:
        print("   A executar 'git push' para disponibilizar ativos no GitHub Raw CDN...")
        _publish_site_assets_to_git(state, public_paths)
        print("   Push concluído!")
    else:
        print("   Nenhum ativo de imagem a publicar no Git.")

    # 5. Aguardar disponibilidade pública dos URLs no CDN do GitHub
    if social_posts:
        print("-> A verificar disponibilidade pública de todos os ativos via HTTP HEAD...")
        missing = list(social_posts)
        for attempt in range(15):
            missing = [post for post in missing if not _public_url_available(_public_image_url_for_buffer(post, state))]
            if not missing:
                break
            print(f"   Aguardando imagens públicas CDN... Tentativa {attempt + 1}/15 (Restantes em falta: {len(missing)})")
            time.sleep(3)
            
        if missing:
            first = missing[0]
            url = _public_image_url_for_buffer(first, state)
            print(f"   [AVISO] Algumas imagens ainda estão indisponíveis no CDN: {first.post_id} | URL: {url}")
        else:
            print("-> Sucesso: Todas as imagens estão publicamente acessíveis na CDN!")

    # 6. Executar agendamento por canais (LinkedIn, X, Site)
    print("\n--- INICIANDO PROCESSAMENTO DE AGENDAMENTOS ---")
    
    # Vamos armazenar os resultados
    scheduled_summary = []

    for topic_id, scheduled_time in PLAN:
        package = posts_by_topic[topic_id]
        
        # Site, LinkedIn, X
        for post in package:
            if post.channel in {"linkedin", "x", "site"}:
                print(f"-> A agendar {post.channel.upper()} de {topic_id} para as {scheduled_time[-14:-6]}...")
                try:
                    updated_post = _schedule_post_in_buffer(state, post.post_id, scheduled_time)
                    scheduled_summary.append({
                        "post_id": updated_post.post_id,
                        "channel": updated_post.channel,
                        "time": scheduled_time[-14:-6],
                        "buffer_id": updated_post.buffer_post_id or "site-local",
                        "title": updated_post.title
                    })
                    print(f"   [OK] {updated_post.channel} agendado: {updated_post.buffer_post_id or 'site-local'}")
                except Exception as exc:
                    print(f"   [ERRO] Falha no agendamento de {post.channel.upper()}: {exc}")

    # Instagram Carousel: Omitido agora por indicação do utilizador ("o que falta das 21h ponho amanhã")
    print("\n-> [INFO] Agendamento de Instagram Carrossel omitido hoje. Será processado amanhã com o post das 21:00.")

    # 7. Sincronizar static site feed final e dar git push
    _sync_static_site_feed(state, git_push=True)
    print("\n-> Static site feed (site-feed.json) regenerado com sucesso!")

    # 8. Mostrar Tabela de Resultados
    print("\n=== TABELA DE RESUMO DE AGENDAMENTO (2026-06-16) ===")
    print(f"{'HORA':<10} | {'CANAL':<12} | {'POST ID':<25} | {'BUFFER POST ID / SITE':<35} | {'TÍTULO'}")
    print("-" * 115)
    
    scheduled_summary.sort(key=lambda x: (x["time"], x["channel"]))
    for entry in scheduled_summary:
        print(f"{entry['time']:<10} | {entry['channel'].upper():<12} | {entry['post_id']:<25} | {entry['buffer_id']:<35} | {entry['title'][:40]}")
    
    print("\n=== AGENDAMENTO EDITORIAL CONCLUÍDO COM SUCESSO! ===")

if __name__ == "__main__":
    main()

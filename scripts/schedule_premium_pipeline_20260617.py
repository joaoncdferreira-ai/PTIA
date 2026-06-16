from __future__ import annotations

import json
import os
import shutil
import sys
import time
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

# Plano de agendamento cronológico para hoje (17 de Junho de 2026)
PLAN = [
    ("topic_a6039af048eedbc047", "2026-06-17T09:00:00+01:00"),  # Charm Security
    ("topic_5e40277b16552fbdd2", "2026-06-17T13:00:00+01:00"),  # Augusta Labs
    ("topic_a51edd9b9bcf74373e", "2026-06-17T16:00:00+01:00"),  # SpaceX / Anysphere
    ("topic_c92a37e9cfc763a509", "2026-06-17T21:00:00+01:00"),  # Gartner Supply Chain
]

def main() -> None:
    load_dotenv()
    print("=== INICIANDO AGENDAMENTO EDITORIAL PREMIUM (2026-06-17) ===")
    state = DashboardState(ROOT / "data")
    
    # 1. Efetuar Backup da base de dados local
    backup_path = state.final_posts_path.with_name(
        f"final_posts.jsonl.bak_before_schedule_{datetime.now():%Y%m%d_%H%M%S}"
    )
    shutil.copy2(state.final_posts_path, backup_path)
    print(f"-> Backup de segurança efetuado em: {backup_path.name}")

    # Recarregar posts
    posts = load_final_posts(state.final_posts_path)

    # 2. Filtrar posts em "approved_for_schedule" ou "scheduled" para hoje
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
    social_posts = [p for p in relevant if p.channel in {"instagram", "linkedin", "x"} and p.image_path]
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
    
    scheduled_summary = []

    # Primeiro: LinkedIn, Site e X (agendamentos diretos e normais)
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

    # Segundo: Instagram Carrossel às 21:00
    print("\n-> A preparar o Carrossel de Instagram para as 21:00...")
    instagram_posts_sorted = []
    original_plan_order = [
        "topic_a6039af048eedbc047",  # Charm Security
        "topic_5e40277b16552fbdd2",  # Augusta Labs
        "topic_a51edd9b9bcf74373e",  # SpaceX / Anysphere
        "topic_c92a37e9cfc763a509",  # Gartner Supply Chain
    ]
    for topic_id in original_plan_order:
        inst_posts = [p for p in posts_by_topic[topic_id] if p.channel == "instagram" and p.image_path]
        if inst_posts:
            instagram_posts_sorted.append(inst_posts[0])

    if len(instagram_posts_sorted) == 4:
        # Construir legenda
        paragraphs = []
        sources = []
        
        for idx, p in enumerate(instagram_posts_sorted, start=1):
            first_p = p.body.strip().split("\n\n")[0].strip()
            paragraphs.append(f"{idx}. {first_p}")
            if p.source_urls:
                sources.append(f"- {p.source_urls[0]}")
                
        combined_body = "\n\n".join(paragraphs)
        combined_hashtags = "#InteligenciaArtificial #IA #CharmSecurity #AugustaLabs #SpaceX #Cursor #Gartner #CadeiadeAbastecimento #PTIA #Negocios #Tech #Portugal #Trabalho #Seguranca"
        combined_sources = "Fontes:\n" + "\n".join(sources)
        
        legend_text = f"{combined_body}\n\n{combined_hashtags}\n\n{combined_sources}".strip()
        
        # Recolher as imagens públicas do Instagram
        image_urls = [_public_image_url_for_buffer(p, state) for p in instagram_posts_sorted]
        print(f"   Instagram composto por {len(image_urls)} slides:")
        for url in image_urls:
            print(f"     - {url}")

        # Configurar Canal do Instagram no Buffer
        config = dashboard_module._load_buffer_channels(state.buffer_channels_path)
        instagram_channel_id = dashboard_module._buffer_channel_id_for("instagram", config)
        if not instagram_channel_id:
            raise ValueError("Canal de Instagram não está configurado no Buffer!")

        # Agendar no Buffer
        print("   A chamar API do Buffer para carregar imagem/carrossel...")
        buffer_client = BufferClient()
        carousel_time = "2026-06-17T21:00:00+01:00"
        
        first_inst = instagram_posts_sorted[0]
        if first_inst.status == "scheduled" and first_inst.buffer_post_id and first_inst.buffer_post_id != "manual_buffer_media_required":
            print(f"   [SKIP] O Instagram já parece estar agendado no Buffer (ID: {first_inst.buffer_post_id}).")
            for p in instagram_posts_sorted:
                scheduled_summary.append({
                    "post_id": p.post_id,
                    "channel": "instagram",
                    "time": "21:00:00",
                    "buffer_id": p.buffer_post_id,
                    "title": p.title
                })
        else:
            try:
                buffer_post = buffer_client.create_scheduled_post(
                    channel_id=instagram_channel_id,
                    text=legend_text,
                    due_at=carousel_time,
                    image_urls=image_urls,
                    post_type="post"
                )
                print(f"   [OK] Instagram agendado no Buffer com ID: {buffer_post.id}")

                # Sincronizar posts no final_posts.jsonl como scheduled
                for p in instagram_posts_sorted:
                    # Usar um loop com retentativas para evitar o erro WinError 5 de bloqueio do arquivo
                    for attempt in range(5):
                        try:
                            update_final_post_status(
                                state.final_posts_path,
                                post_id=p.post_id,
                                status="scheduled",
                                scheduled_time=carousel_time,
                                buffer_post_id=buffer_post.id
                            )
                            update_final_post_copy(
                                state.final_posts_path,
                                post_id=p.post_id,
                                notes="[2026-06-17] Agendado no Instagram às 21:00."
                            )
                            break
                        except Exception as e:
                            print(f"   [RETRY {attempt + 1}/5] Falha ao atualizar post local {p.post_id}: {e}")
                            time.sleep(2)
                            
                    scheduled_summary.append({
                        "post_id": p.post_id,
                        "channel": "instagram",
                        "time": "21:00:00",
                        "buffer_id": buffer_post.id,
                        "title": p.title
                    })
                    print(f"   Sincronizado post local {p.post_id} (Instagram) como Scheduled.")
            except Exception as exc:
                print(f"   [ERRO] Falha ao agendar Instagram no Buffer: {exc}")
    else:
        print("-> Nenhum post de Instagram encontrado ou contagem incorreta. A saltar.")

    # 7. Sincronizar static site feed final e dar git push
    _sync_static_site_feed(state, git_push=True)
    print("\n-> Static site feed (site-feed.json) regenerado com sucesso!")

    # 8. Mostrar Tabela de Resultados
    print("\n=== TABELA DE RESUMO DE AGENDAMENTO (2026-06-17) ===")
    print(f"{'HORA':<10} | {'CANAL':<12} | {'POST ID':<25} | {'BUFFER POST ID / SITE':<35} | {'TÍTULO'}")
    print("-" * 115)
    
    scheduled_summary.sort(key=lambda x: (x["time"], x["channel"]))
    for entry in scheduled_summary:
        print(f"{entry['time']:<10} | {entry['channel'].upper():<12} | {entry['post_id']:<25} | {entry['buffer_id']:<35} | {entry['title'][:40]}")
    
    print("\n=== AGENDAMENTO EDITORIAL CONCLUÍDO COM SUCESSO! ===")

if __name__ == "__main__":
    main()

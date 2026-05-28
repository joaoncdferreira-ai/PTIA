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
    _validate_final_package_copy,
    load_final_posts,
    update_final_post_status,
    update_final_post_copy,
    _sync_static_site_feed
)
from ptia_engine.models import FinalPost
from ptia_engine.buffer_api import BufferClient

# Dicionário com os novos corpos de texto otimizados e completos para o X (limite 280 caracteres)
# Resolvemos os textos cortados, garantindo coerência, elegância e fim sem reticências.
X_POLISHED_BODIES = {
    "post_53d7d9f82f15e8e692": "A Anthropic lançou o Claude Opus 4.8 com modos de esforço configuráveis e fluxos dinâmicos no Claude Code. O objetivo é claro: criar hábitos no programador e fidelizar antes que a concorrência reaja. Para Portugal, o que importa é a utilidade operacional diária.",
    "post_c6a546db5072c983c9": "Despedimentos na Coinbase, Meta e Cisco são atribuídos à IA, mas os números escondem ajustes de mercado e contratações excessivas do passado. O desafio real não é a substituição imediata, mas a velocidade de adaptação das equipas para usar a IA como alavanca de valor.",
    "post_4899cc2470b3316d22": "O ChatGPT está a fabricar batalhas e a omitir factos históricos, gerando preocupação na educação. O problema não é a tecnologia em si, mas a sua utilização acrítica. Em Portugal, a prioridade urgente deve ser a literacia digital e a capacidade de questionar o que a IA gera.",
    "post_b85f6961493afa4911": "Demis Hassabis traçou o caminho para a AGI e a cura de doenças com IA, com foco em oncologia e imunologia. Mas a verdadeira corrida não é apenas técnica: é pelo hábito. Vence quem integrar a IA de forma tão profunda nas ferramentas diárias que a torne um padrão invisível."
}

# Plano de agendamento cronológico para amanhã (29 de Maio de 2026)
PLAN = [
    ("topic_1ef871b30308151949", "2026-05-29T09:00:00+01:00"),  # Claude Opus 4.8
    ("topic_035f9d48bebe1d7ea7", "2026-05-29T13:00:00+01:00"),  # IA e Emprego
    ("topic_9568c456abec2f18d5", "2026-05-29T16:00:00+01:00"),  # ChatGPT inventa História
    ("topic_0a7c5338c2d566d6f2", "2026-05-29T21:00:00+01:00"),  # Demis Hassabis DeepMind
]

def apply_x_polish_replacements(posts_path: Path) -> None:
    print("-> A aplicar otimizações e correções nos textos do canal X...")
    lines = []
    modified_count = 0
    for line in posts_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        post = json.loads(line)
        post_id = post.get("post_id")
        if post_id in X_POLISHED_BODIES:
            old_body = post.get("body", "")
            new_body = X_POLISHED_BODIES[post_id]
            post["body"] = new_body
            post["editor_notes"] = post.get("editor_notes", "") + f"\n[{datetime.now().isoformat()}] Polimento manual do X aplicado para conformidade de 280 caracteres sem truncagem."
            modified_count += 1
            print(f"   [Polido] {post_id} | Antigo: {old_body[:40]}... -> Novo: {new_body[:60]}...")
        lines.append(json.dumps(post, ensure_ascii=False))
    
    # Escreve atomicamente usando o novo write_jsonl importado indiretamente ou de forma segura
    # Para ser consistente com o nosso storage.py atualizado, gravamos o texto diretamente no ficheiro
    posts_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"-> {modified_count} posts do X otimizados e gravados com sucesso!")

def main() -> None:
    print("=== INICIANDO AGENDAMENTO EDITORIAL PREMIUM (2026-05-29) ===")
    state = DashboardState(ROOT / "data")
    
    # 1. Efetuar Backup da base de dados local
    backup_path = state.final_posts_path.with_name(
        f"final_posts.jsonl.bak_before_schedule_{datetime.now():%Y%m%d_%H%M%S}"
    )
    shutil.copy2(state.final_posts_path, backup_path)
    print(f"-> Backup de segurança efetuado em: {backup_path.name}")

    # 2. Aplicar correções de enquadramento do X
    apply_x_polish_replacements(state.final_posts_path)

    # Recarregar posts atualizados
    posts = load_final_posts(state.final_posts_path)

    # 3. Filtrar posts em "approved_for_schedule" para amanhã
    target_topic_ids = {topic_id for topic_id, _ in PLAN}
    relevant = [
        post
        for post in posts
        if post.status == "approved_for_schedule"
        and post.topic_id in target_topic_ids
    ]
    
    print(f"-> Detetados {len(relevant)} posts relevantes aprovados para agendamento.")
    
    # Agrupar posts por tópico
    posts_by_topic = {topic_id: [] for topic_id, _ in PLAN}
    for post in relevant:
        posts_by_topic[post.topic_id].append(post)

    # 4. Validar integridade dos pacotes
    for topic_id, scheduled_time in PLAN:
        package = posts_by_topic[topic_id]
        print(f"   Tópico {topic_id} ({scheduled_time[-14:-6]}): {len(package)} posts ({','.join(p.channel for p in package)})")
        if len(package) != 4:
            raise SystemExit(f"ERRO: O tópico {topic_id} tem {len(package)} posts (esperado: 4 canais: linkedin, instagram, x, site).")

    # 5. Preparar e publicar imagens no repositório de assets públicos do Git
    print("-> A copiar e publicar imagens variantes de todos os posts sociais no Git...")
    social_posts = [p for p in relevant if p.channel in {"instagram", "linkedin", "x"}]
    public_paths = []
    for post in social_posts:
        path = _copy_image_to_public_site_assets(state, post)
        if path:
            public_paths.append(path)
            
    print(f"   {len(public_paths)} imagens copiadas localmente para site/assets/final.")
    
    # Commitar e empurrar (push) para o GitHub para expor em URL público
    print("   A executar 'git push' para disponibilizar ativos no GitHub Raw CDN...")
    _publish_site_assets_to_git(state, public_paths)
    print("   Push concluído!")

    # 6. Aguardar disponibilidade pública dos URLs no CDN do GitHub
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
        raise SystemExit(f"ERRO: Imagem ainda indisponível no CDN: {first.post_id} | URL: {url}")
    print("-> Sucesso: Todas as imagens estão publicamente acessíveis na CDN!")

    # 7. Executar agendamento por canais
    print("\n--- INICIANDO PROCESSAMENTO DE AGENDAMENTOS ---")
    
    # Vamos armazenar os resultados
    scheduled_summary = []

    # Primeiro: LinkedIn, Site e X (agendamentos diretos e normais)
    for topic_id, scheduled_time in PLAN:
        package = posts_by_topic[topic_id]
        
        # Site, LinkedIn, X
        for post in package:
            if post.channel in {"linkedin", "x", "site"}:
                print(f"-> A agendar {post.channel.upper()} de {topic_id} para as {scheduled_time[-14:-6]}...")
                updated_post = _schedule_post_in_buffer(state, post.post_id, scheduled_time)
                scheduled_summary.append({
                    "post_id": updated_post.post_id,
                    "channel": updated_post.channel,
                    "time": scheduled_time[-14:-6],
                    "buffer_id": updated_post.buffer_post_id or "site-local",
                    "title": updated_post.title
                })
                print(f"   [OK] {updated_post.channel} agendado: {updated_post.buffer_post_id or 'site-local'}")

    # Segundo: Instagram Carrossel Combinado às 21:00
    print("\n-> A preparar o Carrossel Combinado de Instagram (4 slides) para as 21:00...")
    instagram_posts_sorted = []
    # Cronológica: Topic 1 (09:00), Topic 2 (13:00), Topic 3 (16:00), Topic 4 (21:00)
    for topic_id, _ in PLAN:
        inst_post = next(p for p in posts_by_topic[topic_id] if p.channel == "instagram")
        instagram_posts_sorted.append(inst_post)

    # Construir legenda combinada (um parágrafo por post + hashtags e fontes organizadas)
    paragraphs = []
    sources = []
    
    for idx, p in enumerate(instagram_posts_sorted, start=1):
        # O primeiro parágrafo é o texto até à primeira quebra de linha dupla
        first_p = p.body.strip().split("\n\n")[0].strip()
        paragraphs.append(f"{idx}. {first_p}")
        if p.source_urls:
            sources.append(f"- {p.source_urls[0]}")
            
    combined_body = "\n\n".join(paragraphs)
    combined_hashtags = "#InteligenciaArtificial #IA #Produtividade #Negocios #Gestao #Governanca #Portugal #PTIA"
    combined_sources = "Fontes:\n" + "\n".join(sources)
    
    legend_text = f"{combined_body}\n\n{combined_hashtags}\n\n{combined_sources}".strip()
    
    # Recolher as 4 imagens públicas do Instagram
    image_urls = [_public_image_url_for_buffer(p, state) for p in instagram_posts_sorted]
    print(f"   Carrossel composto por {len(image_urls)} slides:")
    for url in image_urls:
        print(f"     - {url}")

    # Configurar Canal do Instagram no Buffer
    config = dashboard_module._load_buffer_channels(state.buffer_channels_path)
    instagram_channel_id = dashboard_module._buffer_channel_id_for("instagram", config)
    if not instagram_channel_id:
        config = dashboard_module._discover_buffer_channels(state.buffer_channels_path)
        instagram_channel_id = dashboard_module._buffer_channel_id_for("instagram", config)
    if not instagram_channel_id:
        raise ValueError("Canal de Instagram não está configurado no Buffer!")

    # Agendar carrossel no Buffer
    print("   A chamar API do Buffer para carregar carrossel...")
    buffer_client = BufferClient()
    carousel_time = "2026-05-29T21:00:00+01:00"
    
    # Criar post no Buffer com as 4 URLs de imagem
    buffer_post = buffer_client.create_scheduled_post(
        channel_id=instagram_channel_id,
        text=legend_text,
        due_at=carousel_time,
        image_urls=image_urls,
        post_type="post"
    )
    print(f"   [OK] Carrossel agendado no Buffer com ID: {buffer_post.id}")

    # Sincronizar todos os 4 posts de Instagram no ficheiro final_posts.jsonl como scheduled
    for p in instagram_posts_sorted:
        # Atualizar status e buffer_post_id
        update_final_post_status(
            state.final_posts_path,
            post_id=p.post_id,
            status="scheduled",
            scheduled_time=carousel_time,
            buffer_post_id=buffer_post.id
        )
        # Adicionar nota editorial de agendamento combinado
        update_final_post_copy(
            state.final_posts_path,
            post_id=p.post_id,
            notes="[2026-05-28] Agendado como parte do Carrossel Combinado de 4 slides das 21:00 para amanhã (29 de Maio)."
        )
        scheduled_summary.append({
            "post_id": p.post_id,
            "channel": "instagram",
            "time": "21:00:00",
            "buffer_id": buffer_post.id,
            "title": p.title
        })
        print(f"   Sincronizado post local {p.post_id} (Instagram) como Scheduled.")

    # 8. Sincronizar static site feed final
    _sync_static_site_feed(state)
    print("\n-> Static site feed (site-feed.json) regenerado com sucesso!")

    # 9. Mostrar Tabela de Resultados do Agendamento
    print("\n=== TABELA DE RESUMO DE AGENDAMENTO (2026-05-29) ===")
    print(f"{'HORA':<10} | {'CANAL':<12} | {'POST ID':<25} | {'BUFFER POST ID / SITE':<35} | {'TÍTULO'}")
    print("-" * 115)
    
    # Ordenar por hora e canal
    scheduled_summary.sort(key=lambda x: (x["time"], x["channel"]))
    for entry in scheduled_summary:
        print(f"{entry['time']:<10} | {entry['channel'].upper():<12} | {entry['post_id']:<25} | {entry['buffer_id']:<35} | {entry['title'][:40]}")
    
    print("\n=== AGENDAMENTO EDITORIAL CONCLUÍDO COM SUCESSO! ===")

if __name__ == "__main__":
    main()

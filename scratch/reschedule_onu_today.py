import os
import sys
import time
from pathlib import Path

ROOT = Path("c:/Users/joaon/ptia-content-engine")
sys.path.insert(0, str(ROOT / "src"))

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

def main():
    load_dotenv()
    from ptia_engine.buffer_api import BufferClient
    from ptia_engine.storage import load_final_posts, write_jsonl
    from ptia_engine.dashboard import DashboardState, _ensure_image_variants_for_posts, _copy_image_to_public_site_assets, _publish_site_assets_to_git, _sync_static_site_feed
    
    state = DashboardState(ROOT / "data")
    buffer_client = BufferClient()
    
    # 1. Cancelar o carrossel de Instagram de hoje no Buffer
    today_instagram_buffer_id = "6a28a1d1c1ee77c7b6b2aa24"
    print(f"-> Cancelando carrossel de Instagram de hoje no Buffer (ID: {today_instagram_buffer_id})...")
    try:
        success = buffer_client.delete_post(today_instagram_buffer_id)
        print(f"   Carrossel cancelado no Buffer: {success}")
    except Exception as e:
        print(f"   Erro ao cancelar carrossel: {e}")

    # 2. Carregar posts
    posts = load_final_posts(state.final_posts_path)
    
    # Tópicos de hoje (dia 10)
    onu_topic = "topic_d0d01b1d0755c68998"
    day10_topics = {
        "topic_9c9a63c2c44df11dc6",  # Claude Fable 5
        "topic_84c837ac4930992e12",  # OCC Contabilidade
        "topic_d0d01b1d0755c68998",  # ONU fosso digital
        "topic_89a3bf38de1eec038e",  # Copa do Mundo
    }
    
    print("-> Atualizando base de dados local para re-agendamento...")
    for post in posts:
        # Posts da ONU (LinkedIn, X, Site) vão para as 18:00
        if post.topic_id == onu_topic and post.channel in {"linkedin", "x", "site"}:
            post.status = "approved_for_schedule"
            post.scheduled_time = "2026-06-10T18:00:00+01:00"
            post.buffer_post_id = ""
            post.image_variants = {}
            print(f"   ONU {post.channel} preparado para as 18:00.")
            
        # Todos os posts de Instagram de hoje (dia 10) precisam de ser re-agendados no carrossel de hoje às 21:00!
        if post.topic_id in day10_topics and post.channel == "instagram":
            post.status = "approved_for_schedule"
            post.scheduled_time = ""
            post.buffer_post_id = ""
            post.image_variants = {}
            print(f"   Instagram de {post.topic_id} preparado para re-agendamento no carrossel de hoje às 21:00.")

    # Salvar base de dados antes de re-gerar
    write_jsonl(state.final_posts_path, posts)
    
    # 3. Forçar a re-geração de todas as variantes de imagem!
    print("-> Re-gerando variantes de imagem...")
    posts = load_final_posts(state.final_posts_path)
    posts = _ensure_image_variants_for_posts(state, posts)
    
    # 4. Copiar variantes re-geradas para os assets do site e Git
    print("-> Copiando imagens para assets do site...")
    public_paths = []
    for post in posts:
        if post.topic_id in day10_topics and post.channel in {"instagram", "linkedin", "x", "site"} and post.image_path:
            path = _copy_image_to_public_site_assets(state, post)
            if path:
                public_paths.append(path)
                
    # Fazer push para o Git
    if public_paths:
        print("-> A fazer git push de novas imagens variantes...")
        _publish_site_assets_to_git(state, public_paths)
        print("   Push concluído!")
        
    # 5. Executar o re-agendamento do Buffer para hoje (dia 10)
    print("\n--- INICIANDO PROCESSAMENTO DO RE-AGENDAMENTO ---")
    
    # Recarregar posts
    posts = load_final_posts(state.final_posts_path)
    posts_by_topic = {topic_id: [] for topic_id in day10_topics}
    for post in posts:
        if post.topic_id in day10_topics and post.status in {"approved_for_schedule", "scheduled"}:
            posts_by_topic[post.topic_id].append(post)
            
    # Agendar LinkedIn, X, Site do tópico ONU para as 18:00
    onu_package = posts_by_topic[onu_topic]
    from ptia_engine.dashboard import _schedule_post_in_buffer
    for post in onu_package:
        if post.channel in {"linkedin", "x", "site"}:
            print(f"-> A agendar {post.channel.upper()} da ONU para as 18:00...")
            try:
                updated_post = _schedule_post_in_buffer(state, post.post_id, "2026-06-10T18:00:00+01:00")
                print(f"   [OK] {updated_post.channel} agendado: {updated_post.buffer_post_id or 'site-local'}")
            except Exception as exc:
                print(f"   [ERRO] Falha ao agendar {post.channel.upper()} da ONU: {exc}")

    # Re-agendar o Instagram Combined Carousel às 21:00
    print("\n-> A preparar o novo Carrossel Combinado de Instagram para as 21:00...")
    instagram_posts_sorted = []
    # Seguir a mesma ordem de PLAN do script original
    original_plan_order = [
        "topic_9c9a63c2c44df11dc6",
        "topic_84c837ac4930992e12",
        "topic_d0d01b1d0755c68998",
        "topic_89a3bf38de1eec038e",
    ]
    for topic_id in original_plan_order:
        inst_posts = [p for p in posts if p.topic_id == topic_id and p.channel == "instagram" and p.image_path]
        if inst_posts:
            instagram_posts_sorted.append(inst_posts[0])

    if instagram_posts_sorted:
        paragraphs = []
        sources = []
        for idx, p in enumerate(instagram_posts_sorted, start=1):
            first_p = p.body.strip().split("\n\n")[0].strip()
            paragraphs.append(f"{idx}. {first_p}")
            if p.source_urls:
                sources.append(f"- {p.source_urls[0]}")
                
        combined_body = "\n\n".join(paragraphs)
        combined_hashtags = "#InteligenciaArtificial #IA #Produtividade #Negocios #Gestao #Governanca #Portugal #PTIA"
        combined_sources = "Fontes:\n" + "\n".join(sources)
        legend_text = f"{combined_body}\n\n{combined_hashtags}\n\n{combined_sources}".strip()
        
        image_urls = [_public_image_url_for_buffer(p, state) for p in instagram_posts_sorted]
        print(f"   Carrossel composto por {len(image_urls)} slides:")
        for url in image_urls:
            print(f"     - {url}")

        config = dashboard_module._load_buffer_channels(state.buffer_channels_path)
        instagram_channel_id = dashboard_module._buffer_channel_id_for("instagram", config)
        
        print("   A chamar API do Buffer para carregar carrossel...")
        try:
            buffer_post = buffer_client.create_scheduled_post(
                channel_id=instagram_channel_id,
                text=legend_text,
                due_at="2026-06-10T21:00:00+01:00",
                image_urls=image_urls,
                post_type="post"
            )
            print(f"   [OK] Novo Carrossel agendado no Buffer com ID: {buffer_post.id}")

            # Sincronizar todos os posts de Instagram na base de dados
            for p in instagram_posts_sorted:
                update_final_post_status(
                    state.final_posts_path,
                    post_id=p.post_id,
                    status="scheduled",
                    scheduled_time="2026-06-10T21:00:00+01:00",
                    buffer_post_id=buffer_post.id
                )
                update_final_post_copy(
                    state.final_posts_path,
                    post_id=p.post_id,
                    notes="[2026-06-10] Re-agendado no Carrossel de Instagram das 21:00 com a imagem corrigida."
                )
                print(f"   Sincronizado post local {p.post_id} (Instagram) como Scheduled.")
        except Exception as exc:
            print(f"   [ERRO] Falha ao agendar Carrossel de Instagram no Buffer: {exc}")
            
    # 6. Sincronizar static site feed final e dar git push
    _sync_static_site_feed(state, git_push=True)
    print("\n-> Static site feed (site-feed.json) e sitemaps atualizados e enviados ao Git!")

if __name__ == "__main__":
    main()

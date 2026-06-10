import sys
import os
import shutil
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
    from ptia_engine.storage import load_final_posts, write_jsonl
    from ptia_engine.dashboard import DashboardState, _ensure_image_variants_for_posts, _copy_image_to_public_site_assets, _publish_site_assets_to_git, _sync_static_site_feed
    
    state = DashboardState(ROOT / "data")
    
    # 1. Carregar todos os posts
    posts = load_final_posts(state.final_posts_path)
    
    # 2. Corrigir image_path do tópico da Igreja e limpar as suas variantes
    church_topic = "topic_8c3e0909bc914098ca"
    church_image = "data/final_assets/post_c38262fe28ece80db3_church_ai_cover.png"
    
    print("-> Atualizando base de dados local...")
    for post in posts:
        if post.topic_id == church_topic:
            post.image_path = church_image
            post.image_variants = {}
            post.image_status = "needs_review"
            post.status = "approved_for_schedule"  # Mudar status para approved_for_schedule para que possa ser agendado!
            print(f"   Post {post.post_id} ({post.channel}) atualizado com a imagem base da Igreja.")

    # 3. Limpar variantes dos tópicos do dia 10 para forçar a re-geração (para que tire as URLs dos overlays!)
    day10_topics = {
        "topic_9c9a63c2c44df11dc6",  # Claude Fable 5
        "topic_84c837ac4930992e12",  # OCC Contabilidade
        "topic_d0d01b1d0755c68998",  # ONU fosso digital
        "topic_89a3bf38de1eec038e",  # Copa do Mundo
    }
    for post in posts:
        if post.topic_id in day10_topics:
            post.image_variants = {}
            print(f"   Limpando variantes do post {post.post_id} ({post.channel}) para forçar re-geração com título correto.")
            
    # Salvar base de dados antes de re-gerar
    write_jsonl(state.final_posts_path, posts)
    
    # 4. Forçar a re-geração de todas as variantes de imagem!
    print("-> Forçando a re-geração das variantes de imagem (e desenhando overlays corretos)...")
    posts = load_final_posts(state.final_posts_path)
    posts = _ensure_image_variants_for_posts(state, posts)
    
    # 5. Copiar variantes re-geradas para os assets públicos do site
    print("-> Copiando imagens para a pasta pública do site...")
    target_topics = day10_topics | {church_topic}
    public_paths = []
    for post in posts:
        if post.topic_id in target_topics and post.image_path:
            path = _copy_image_to_public_site_assets(state, post)
            if path:
                public_paths.append(path)
                print(f"   Copiado: {Path(path).name} para assets/final/")
                
    # 6. Sincronizar estática do site (para atualizar o feed JSON com os caminhos absolutos e novos títulos!)
    print("-> Sincronizando estática do site (site-feed.json)...")
    _sync_static_site_feed(state, deploy=False)
    
    # 7. Adicionar site-feed.json e imagens variantes novas ao Git e fazer push
    print("-> Publicando novos ativos no GitHub...")
    files_to_publish = public_paths + [
        str(state.site_dir / "site-feed.json"),
        str(state.site_dir / "sitemap.xml"),
        str(state.site_dir / "news-sitemap.xml"),
        str(state.site_dir / "rss.xml")
    ]
    try:
        _publish_site_assets_to_git(state, files_to_publish)
        print("-> [SUCESSO] Ativos enviados para o GitHub com sucesso!")
    except Exception as e:
        print(f"-> [ERRO] Falha no push para o Git: {e}")

if __name__ == "__main__":
    main()

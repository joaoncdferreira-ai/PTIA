import os
import sys
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
    from ptia_engine.dashboard import DashboardState
    
    state = DashboardState(ROOT / "data")
    buffer_client = BufferClient()
    
    # 1. Apagar posts agendados para amanhã do Buffer
    tomorrow_buffer_ids = [
        "6a29893d622a3bcae5dd4866",  # LinkedIn Igreja
        "6a29894ecbc019b4d3acce47"   # Instagram Igreja
    ]
    
    print("-> Apagando posts de amanhã do Buffer...")
    for post_id in tomorrow_buffer_ids:
        try:
            success = buffer_client.delete_post(post_id)
            print(f"   Post {post_id} apagado do Buffer: {success}")
        except Exception as e:
            print(f"   Erro ao apagar post {post_id}: {e}")
            
    # Na verdade, no BufferClient da ptia_engine, há algum método de deleção?
    # Vamos rodar uma mutation GraphQL para apagar os posts ou usar o método do BufferClient.
    # Vamos inspecionar os métodos de BufferClient em src/ptia_engine/buffer_api.py.
    
    # Repor estado na base de dados local
    posts = load_final_posts(state.final_posts_path)
    church_topic = "topic_8c3e0909bc914098ca"
    print("-> Revertendo posts do tópico da Igreja para needs_final_review...")
    for post in posts:
        if post.topic_id == church_topic:
            post.status = "needs_final_review"
            post.scheduled_time = ""
            post.buffer_post_id = ""
            post.image_variants = {}
            print(f"   Revertido post {post.post_id} ({post.channel})")
            
    write_jsonl(state.final_posts_path, posts)
    print("-> Base de dados local atualizada e posts de amanhã cancelados localmente.")

if __name__ == "__main__":
    main()

import sys
from pathlib import Path

ROOT = Path(r"c:\Users\joaon\ptia-content-engine")
sys.path.insert(0, str(ROOT / "src"))

from ptia_engine.dashboard import update_final_post_copy

def main():
    posts_path = ROOT / "data" / "final_posts.jsonl"
    
    # 1. Update post_cc815bc760972d8573 (Topic topic_3c63d008c9bda317af)
    update_final_post_copy(
        posts_path,
        "post_cc815bc760972d8573",
        body="Um estudo da QSP revela um aumento do investimento em IA pelas empresas portuguesas. Contudo, esta aceleração ocorre sem que as organizações definam políticas internas de governança e compliance para mitigar riscos.\n\nFonte: Jornal Económico"
    )
    print("Updated post_cc815bc760972d8573")
    
    # 2. Update post_b9338f884dbaa60bf7 (Topic topic_aef3422a94b3bacd1e)
    update_final_post_copy(
        posts_path,
        "post_b9338f884dbaa60bf7",
        body="A Anthropic apelou a uma pausa temporária no desenvolvimento de modelos de inteligência artificial de ponta. O alerta surge perante o risco de perda de controlo humano sobre sistemas de IA cada vez mais autónomos.\n\nFonte: Globo"
    )
    print("Updated post_b9338f884dbaa60bf7")
    
    # 3. Update post_286dd5a833f314848d (Topic topic_8e074bba70858b0d84)
    update_final_post_copy(
        posts_path,
        "post_286dd5a833f314848d",
        body="A OpenAI propôs um plano para resiliência biológica com IA. O documento «Biodefense in the Intelligence Age» detalha como usar modelos avançados para mitigar riscos e fortalecer a biodefesa global.\n\nFonte: OpenAI News"
    )
    print("Updated post_286dd5a833f314848d")

if __name__ == "__main__":
    main()

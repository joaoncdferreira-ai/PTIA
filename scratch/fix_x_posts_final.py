import json
from pathlib import Path
import sys

ROOT = Path("c:/Users/joaon/ptia-content-engine")
sys.path.insert(0, str(ROOT / "src"))

from ptia_engine.storage import load_final_posts, write_jsonl

posts = load_final_posts(ROOT / "data/final_posts.jsonl")

replacements = {
    "post_7fd4343d9401dff7dc": (
        "Portugal reafirma a sua posição na defesa dos trabalhadores face à integração da IA, "
        "sublinhando a importância de condições laborais dignas perante a rápida inovação tecnológica. #IA #PTIA\n\n"
        "Fonte: Governo de Portugal"
    ),
    "post_9d2a328b7772c84e89": (
        "A OpenAI planeia reformular o ChatGPT para o tornar numa \"superapp\" com ferramentas de codificação "
        "e agentes de IA, com o objetivo de acelerar receitas antes de uma eventual Oferta Pública de Venda. #IA #PTIA\n\n"
        "Fonte: CNN Brasil"
    ),
    "post_631503cf53b7e2de56": (
        "A Nvidia adquiriu a Kumo, startup de IA preditiva, por mais de 400 milhões de dólares. A operação "
        "reforça a liderança da Nvidia no setor e abre caminho ao desenvolvimento de novas ferramentas avançadas de análise. #IA #PTIA\n\n"
        "Fonte: Nvidia"
    ),
    "post_cef78c317ceff5953a": (
        "A Microsoft revelou o Scout, um sistema de Autopilot agêntico integrado no ecossistema do M365. "
        "O desenvolvimento marca uma evolução relevante na integração de agentes inteligentes no trabalho diário. #IA #PTIA\n\n"
        "Fonte: Microsoft"
    )
}

updated_count = 0
for post in posts:
    if post.post_id in replacements:
        post.body = replacements[post.post_id]
        # Garantir que o status está limpo para ser re-agendado se necessário
        if post.status == "scheduled":
            post.status = "approved_for_schedule"
        updated_count += 1
        print(f"Updated post body for X: {post.post_id}")

if updated_count > 0:
    write_jsonl(ROOT / "data/final_posts.jsonl", posts)
    print(f"Sucesso: {updated_count} posts de X corrigidos no JSONL.")
else:
    print("Nenhum post foi modificado.")

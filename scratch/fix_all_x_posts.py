import json
from pathlib import Path
import sys

ROOT = Path("c:/Users/joaon/ptia-content-engine")
sys.path.insert(0, str(ROOT / "src"))

from ptia_engine.storage import load_final_posts, write_jsonl

posts = load_final_posts(ROOT / "data/final_posts.jsonl")

replacements = {
    "post_27feeabb841f0dac91": (
        "A Anthropic lançou o Claude Fable 5 e o Mythos 5, novos modelos otimizados para uso geral e focados em segurança. "
        "A corrida dos modelos continua a acelerar para tornar a IA mais acessível e integrada. #IA #PTIA\n\n"
        "Fonte: Anthropic"
    ),
    "post_f7f9e2d617512828a8": (
        "A Ordem dos Contabilistas Certificados (OCC) lançou um guia sobre a IA no setor. "
        "O sinal é claro: a automação liberta os profissionais para tarefas de consultoria estratégica, "
        "redefinindo a proposta de valor. #IA #PTIA\n\n"
        "Fonte: OCC"
    ),
    "post_0d0412f6db433230e4": (
        "A ONU alerta que o desequilíbrio no acesso à IA pode criar novas dependências globais. "
        "Para Portugal, a resposta passa por desenvolver infraestruturas e literacia digital própria, "
        "garantindo a autonomia tecnológica. #IA #PTIA\n\n"
        "Fonte: ONU"
    ),
    "post_5979cef137f7fa3f96": (
        "A Copa do Mundo de 2026 será um marco na aplicação da IA no desporto, "
        "desde a análise tática avançada até à transparência nas decisões de arbitragem (VAR). "
        "A tecnologia ao serviço da dinâmica do jogo. #IA #PTIA\n\n"
        "Fonte: CNN"
    )
}

updated_count = 0
for post in posts:
    if post.post_id in replacements:
        post.body = replacements[post.post_id]
        updated_count += 1
        print(f"Updated X post: {post.post_id}")

if updated_count > 0:
    write_jsonl(ROOT / "data/final_posts.jsonl", posts)
    print(f"Sucesso: {updated_count} posts de X corrigidos na base de dados.")
else:
    print("Nenhum post foi modificado.")

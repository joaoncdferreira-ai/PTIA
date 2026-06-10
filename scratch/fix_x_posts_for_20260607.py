import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
db_path = ROOT / "data" / "final_posts.jsonl"

fixes = {
    "post_6a4f15d04449b4f788": "Estudo da Anthropic revela que homens usam agentes de codificação de IA mais que o dobro de mulheres em pesquisa de ciências sociais. Esta disparidade exige foco em estratégias inclusivas de formação e adoção de tecnologia em Portugal para evitar novas clivagens.",
    "post_513d85431be3010ac7": "Amazon lança o robô Proteus e investe 10 mil milhões de euros na Europa para acelerar a automação logística. A introdução destes robôs inteligentes promete transformar a eficiência operacional de armazéns e redefinir o futuro da robótica no continente.",
    "post_8402edd5c04793a170": "Lisboa consolida a sua posição no Top 10 europeu dos ecossistemas de startups em crescimento acelerado. Esta ascensão, impulsionada por um ambiente dinâmico de inovação, coloca a capital portuguesa no radar de decisores e investidores globais."
}

lines = db_path.read_text(encoding="utf-8").splitlines()
updated_lines = []
updated_count = 0

for line in lines:
    if not line.strip():
        continue
    record = json.loads(line)
    post_id = record.get("post_id")
    if post_id in fixes:
        record["body"] = fixes[post_id]
        # Also clean up status back to approved_for_schedule so it gets processed
        record["status"] = "approved_for_schedule"
        updated_count += 1
        print(f"Fixed post {post_id}: status set to approved_for_schedule, body updated.")
    updated_lines.append(json.dumps(record, ensure_ascii=False))

db_path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")
print(f"Total fixed: {updated_count} posts.")

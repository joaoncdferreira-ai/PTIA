import json
from pathlib import Path

ROOT = Path("c:/Users/joaon/ptia-content-engine")
db_path = ROOT / "data" / "linkedin_comments.jsonl"
artifact_dir = Path("C:/Users/joaon/.gemini/antigravity/brain/97b18b7a-bfe1-4412-bbd3-47410ebaa4bf")
output_path = artifact_dir / "linkedin_comments_report.md"

comments = []
if db_path.exists():
    with open(db_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    record = json.loads(line)
                    if record.get("status") in ["draft", "commented"]:
                        comments.append(record)
                except Exception as e:
                    pass

# Sort comments by creation date (most recent first)
comments.sort(key=lambda x: x.get("created_at", ""), reverse=True)

markdown_lines = [
    "# 💬 Relatório de Comentários Editoriais PTIA",
    "",
    "Este relatório apresenta a lista de comentários estratégicos propostos ou efetuados pelo motor da **PTIA.pt** nas redes de líderes e empresas do ecossistema tecnológico português.",
    "",
    "> [!NOTE]",
    " O motor foi agora atualizado com a filosofia **\"Sim, e...\"** (adição booster de produtividade), pelo que os novos comentários gerados daqui em diante seguirão este tom impulsionador e aditivo.",
    "",
    "| Autor / Decisor | Post Original (Excerto) | Proposta de Comentário PTIA | Estado | Link Original |",
    "| :--- | :--- | :--- | :--- | :--- |"
]

for c in comments:
    profile = c.get("profile_name", "N/A")
    post_body = c.get("post_body", "").strip().replace("\n", " ").replace("|", "\\|")
    if len(post_body) > 120:
        post_body = post_body[:117] + "..."
    
    comment_text = c.get("comment_text", "").strip().replace("\n", " ").replace("|", "\\|")
    status = c.get("status", "draft")
    status_pill = f"`{status}`"
    post_url = c.get("post_url", "#")
    
    markdown_lines.append(
        f"| **{profile}** | *{post_body}* | {comment_text} | {status_pill} | [Ver Post]({post_url}) |"
    )

with open(output_path, "w", encoding="utf-8") as f:
    f.write("\n".join(markdown_lines))

print(f"Generated beautifully formatted report with {len(comments)} comments at: {output_path}")

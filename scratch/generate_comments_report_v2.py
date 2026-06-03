import json
import os
import sys
import subprocess
from pathlib import Path
from datetime import datetime

# Configure output to support UTF-8 on Windows
sys.stdout.reconfigure(encoding='utf-8')

ROOT = Path("c:/Users/joaon/ptia-content-engine")
db_path = ROOT / "data" / "linkedin_comments.jsonl"
output_md = Path("C:/Users/joaon/.gemini/antigravity/brain/97b18b7a-bfe1-4412-bbd3-47410ebaa4bf/linkedin_comments_report.md")
output_pdf = Path("C:/Users/joaon/.gemini/antigravity/brain/97b18b7a-bfe1-4412-bbd3-47410ebaa4bf/linkedin_comments_report.pdf")

print("=== GENERATING LINKEDIN COMMENTS REPORT V2 ===")

if not db_path.exists():
    print(f"Error: Database file not found at {db_path}")
    sys.exit(1)

# Read all generated comments from the DB
comments = []
with open(db_path, "r", encoding="utf-8") as f:
    for line in f:
        if line.strip():
            try:
                record = json.loads(line)
                if record.get('comment_text'):
                    comments.append(record)
            except Exception as e:
                pass

# Sort comments by creation date (most recent first)
def parse_date(date_str):
    try:
        # e.g., 2026-06-03T16:06:39+00:00 or similar
        return datetime.fromisoformat(date_str)
    except:
        return datetime.min

comments.sort(key=lambda x: parse_date(x.get('created_at', '')), reverse=True)

# Generate Markdown content for linkedin_comments_report.md
current_time_str = datetime.now().strftime("%d/%m/%Y às %H:%M")

md_content = f"""# 💬 Relatório de Comentários Gerados pelo PTIA Content Engine

Este relatório reúne todos os comentários simulados e rascunhos criados pelo motor de Inteligência Artificial da **PTIA.pt** para o LinkedIn.

* **Data de Atualização**: {current_time_str}
* **Total de Comentários no Relatório**: {len(comments)}
* **Versão PDF Premium**: [Descarregar linkedin_comments_report.pdf](file:///C:/Users/joaon/.gemini/antigravity/brain/97b18b7a-bfe1-4412-bbd3-47410ebaa4bf/linkedin_comments_report.pdf)

---

## 🎯 Lista de Comentários Gerados

"""

for idx, c in enumerate(comments, 1):
    profile = c.get('profile_name', 'Desconhecido')
    post_url = c.get('post_url', '#')
    post_body = c.get('post_body', '').strip()
    comment = c.get('comment_text', '').strip()
    status = c.get('status', 'draft')
    created_at = c.get('created_at', '')
    
    # Format date for display
    try:
        dt = datetime.fromisoformat(created_at)
        created_display = dt.strftime("%d/%m/%Y %H:%M")
    except:
        created_display = created_at
        
    md_content += f"""### {idx}. Canal/Perfil: **{profile}**
* **Data**: {created_display} | **Estado**: `{status}`
* **Link do Post**: [{post_url}]({post_url})

**Post de Origem:**
> {post_body[:300].replace(chr(10), " ")}...

**Comentário Gerado pelo PTIA Engine:**
> 💡 **"{comment}"**

---
"""

# Write MD report
output_md.parent.mkdir(parents=True, exist_ok=True)
output_md.write_text(md_content, encoding="utf-8")
print(f"MD Report written to {output_md}")

# Build HTML content for PDF generation
html_comments = ""
for idx, c in enumerate(comments, 1):
    profile = c.get('profile_name', 'Desconhecido')
    post_url = c.get('post_url', '#')
    post_body = c.get('post_body', '').strip().replace('\n', '<br>')
    comment = c.get('comment_text', '').strip()
    status = c.get('status', 'draft')
    created_at = c.get('created_at', '')
    
    try:
        dt = datetime.fromisoformat(created_at)
        created_display = dt.strftime("%d de %B de %Y às %H:%M")
    except:
        created_display = created_at
        
    # Translate status to PT
    status_label = {
        'draft': 'Rascunho Editorial (Pronto)',
        'failed': 'Falha no Scraper (Playwright)',
        'posted': 'Publicado no LinkedIn',
        'rejected': 'Rejeitado por AI/Utilizador'
    }.get(status, status)
    
    status_class = f"status-{status}"
    
    html_comments += f"""
    <div class="comment-card">
        <div class="card-header">
            <span class="card-num">#{idx}</span>
            <span class="profile-name">{profile}</span>
            <span class="status-badge {status_class}">{status_label}</span>
        </div>
        <div class="meta-row">
            <strong>Data:</strong> {created_display} | 
            <strong>Link:</strong> <a href="{post_url}" target="_blank">Ver post no LinkedIn</a>
        </div>
        <div class="section-title">Post Original</div>
        <div class="original-post">
            {post_body}
        </div>
        <div class="section-title">Comentário Gerado (Fórmula "Sim, e...")</div>
        <div class="engine-comment">
            "{comment}"
        </div>
    </div>
    """

html_content = f"""<!DOCTYPE html>
<html lang="pt">
<head>
    <meta charset="UTF-8">
    <title>Relatório de Comentários LinkedIn - PTIA Content Engine</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=Playfair+Display:ital,wght@0,600;0,700;0,800;1,600&display=swap');
        
        @page {{
            size: A4;
            margin: 20mm;
            @bottom-right {{
                content: counter(page);
                font-family: 'Outfit', sans-serif;
                font-size: 9pt;
                color: #64748b;
            }}
            @bottom-left {{
                content: "PTIA.pt Content Engine — Relatório de Performance";
                font-family: 'Outfit', sans-serif;
                font-size: 9pt;
                color: #64748b;
            }}
        }}
        
        body {{
            font-family: 'Outfit', sans-serif;
            background-color: #ffffff;
            color: #1e293b;
            margin: 0;
            padding: 0;
            line-height: 1.6;
        }}
        
        /* Cover Page */
        .cover-page {{
            page-break-after: always;
            height: 100%;
            display: flex;
            flex-direction: column;
            justify-content: center;
            padding-top: 40mm;
        }}
        
        .logo-area {{
            font-family: 'Playfair Display', serif;
            font-size: 38pt;
            font-weight: 800;
            color: #1e3a8a;
            border-bottom: 3px solid #fbbf24;
            padding-bottom: 10px;
            margin-bottom: 20px;
        }}
        
        .title {{
            font-size: 28pt;
            font-weight: 700;
            color: #0f172a;
            line-height: 1.2;
            margin-bottom: 15px;
        }}
        
        .subtitle {{
            font-size: 16pt;
            color: #475569;
            margin-bottom: 40mm;
            font-weight: 300;
        }}
        
        .metadata-box {{
            background-color: #f8fafc;
            border-left: 4px solid #1e3a8a;
            padding: 15px 20px;
            font-size: 11pt;
            color: #334155;
        }}
        
        .metadata-box p {{
            margin: 5px 0;
        }}
        
        /* Content Header */
        .page-header {{
            border-bottom: 1px solid #e2e8f0;
            padding-bottom: 10px;
            margin-bottom: 25px;
        }}
        
        .page-header h2 {{
            font-family: 'Playfair Display', serif;
            font-size: 22pt;
            color: #0f172a;
            margin: 0;
        }}
        
        .introduction {{
            font-size: 11pt;
            color: #475569;
            margin-bottom: 30px;
            background-color: #f0fdf4;
            border: 1px solid #bbf7d0;
            border-radius: 8px;
            padding: 15px;
        }}
        
        /* Cards */
        .comment-card {{
            background-color: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 25px;
            page-break-inside: avoid;
        }}
        
        .card-header {{
            display: flex;
            align-items: center;
            margin-bottom: 12px;
            border-bottom: 1px solid #f1f5f9;
            padding-bottom: 10px;
        }}
        
        .card-num {{
            background-color: #1e3a8a;
            color: #ffffff;
            font-weight: 700;
            font-size: 10pt;
            padding: 2px 8px;
            border-radius: 4px;
            margin-right: 12px;
        }}
        
        .profile-name {{
            font-size: 13pt;
            font-weight: 700;
            color: #0f172a;
            flex-grow: 1;
        }}
        
        .status-badge {{
            font-size: 9pt;
            font-weight: 600;
            padding: 3px 10px;
            border-radius: 9999px;
            text-transform: uppercase;
        }}
        
        .status-draft {{
            background-color: #fef3c7;
            color: #d97706;
        }}
        
        .status-failed {{
            background-color: #fee2e2;
            color: #dc2626;
        }}
        
        .status-posted {{
            background-color: #dcfce7;
            color: #16a34a;
        }}
        
        .status-rejected {{
            background-color: #f1f5f9;
            color: #475569;
        }}
        
        .meta-row {{
            font-size: 9.5pt;
            color: #64748b;
            margin-bottom: 15px;
        }}
        
        .meta-row a {{
            color: #2563eb;
            text-decoration: none;
        }}
        
        .section-title {{
            font-size: 10pt;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: #475569;
            margin-top: 15px;
            margin-bottom: 6px;
        }}
        
        .original-post {{
            background-color: #f8fafc;
            border-radius: 6px;
            padding: 12px 16px;
            font-size: 10pt;
            color: #334155;
            border-left: 3px solid #cbd5e1;
            font-style: italic;
            max-height: 120px;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        
        .engine-comment {{
            background-color: #eff6ff;
            border-radius: 6px;
            padding: 14px 18px;
            font-size: 11pt;
            font-weight: 500;
            color: #1e3a8a;
            border-left: 4px solid #3b82f6;
            margin-top: 8px;
        }}
        
    </style>
</head>
<body>
    <div class="cover-page">
        <div class="logo-area">PTIA.pt</div>
        <div class="title">Relatório de Simulação de Comentários</div>
        <div class="subtitle">Análise de interações orgânicas geradas pelo Content Engine</div>
        
        <div class="metadata-box">
            <p><strong>Projeto:</strong> Portugal Tech & AI (PTIA.pt)</p>
            <p><strong>Módulo:</strong> Motor de Comentários LinkedIn (Fórmula "Sim, e...")</p>
            <p><strong>Data de Emissão:</strong> {current_time_str}</p>
            <p><strong>Âmbito:</strong> Comentários de Rascunho & Auditoria Social</p>
            <p><strong>Total de Registos:</strong> {len(comments)}</p>
        </div>
    </div>
    
    <main>
        <div class="page-header">
            <h2>Últimos Comentários Gerados pelo Engine</h2>
        </div>
        
        <div class="introduction">
            <strong>Nota Editorial:</strong> O motor de comentários do PTIA está configurado com a diretriz editorial <strong>"Sim, e..."</strong>. Esta técnica incentiva o diálogo positivo e o pensamento construtivo sobre produtividade empresarial, soberania de dados, regulação ética e inovação tecnológica em Portugal, evitando ceticismo destrutivo ou autopromoção direta.
        </div>
        
        {html_comments}
    </main>
</body>
</html>
"""

tmp_html = ROOT / ".tmp" / "comments_report_v2.html"
tmp_html.parent.mkdir(parents=True, exist_ok=True)
tmp_html.write_text(html_content, encoding="utf-8")
print(f"HTML Temp file written to {tmp_html}")

# Try generating using Weasyprint
print("Attempting to generate PDF via Weasyprint...")
try:
    from weasyprint import HTML
    HTML(string=html_content).write_pdf(str(output_pdf))
    print(f"SUCCESS: PDF generated using Weasyprint at {output_pdf}")
    sys.exit(0)
except Exception as e:
    print(f"Weasyprint failed or not fully configured: {e}")
    print("Falling back to Playwright...")

# Fallback: Generate PDF using Playwright via Node.js
node_script = f"""
const {{ chromium }} = require("playwright");
async function render() {{
  const browser = await chromium.launch({{ headless: true }});
  const page = await browser.newPage();
  await page.goto("file:///{tmp_html.as_posix()}", {{ waitUntil: "networkidle" }});
  await page.pdf({{
    path: "{output_pdf.as_posix()}",
    format: "A4",
    printBackground: true,
    margin: {{ top: "20mm", right: "20mm", bottom: "20mm", left: "20mm" }}
  }});
  await browser.close();
  console.log("PDF rendered successfully via Playwright.");
}}
render();
"""

tmp_node_js = ROOT / ".tmp" / "render_report_v2.js"
tmp_node_js.write_text(node_script, encoding="utf-8")

try:
    res = subprocess.run(["node", str(tmp_node_js)], capture_output=True, text=True, check=True)
    print(res.stdout)
    print(f"SUCCESS: PDF generated via Playwright fallback at {output_pdf}")
except Exception as err:
    print(f"Error rendering PDF via Playwright: {err}")
    if hasattr(err, 'stderr'):
        print(err.stderr)

import os
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Paths
PROJECT_DIR = Path(__file__).resolve().parent.parent
FINAL_POSTS_PATH = PROJECT_DIR / "data" / "final_posts.jsonl"
TMP_DIR = PROJECT_DIR / ".tmp"
HTML_OUT_PATH = TMP_DIR / "carousel.html"
NODE_RENDER_SCRIPT = PROJECT_DIR / "scripts" / "render_carousel_pdf.js"

def _parse_date(value: str) -> datetime:
    raw = (value or "").strip()
    if not raw:
        return datetime.min.replace(tzinfo=timezone.utc)
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        if len(raw) == 10:
            return datetime.fromisoformat(raw).replace(tzinfo=timezone.utc)
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)

def load_recent_posts(limit=4) -> list[dict]:
    posts = []
    if not FINAL_POSTS_PATH.exists():
        return []
        
    with open(FINAL_POSTS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                if record.get("status") in ["published", "scheduled"] and record.get("channel") in ["site", "linkedin"]:
                    posts.append(record)
            except Exception as e:
                print(f"Erro ao ler linha: {e}")

    # Sort by created_at or scheduled_time descending
    posts.sort(key=lambda p: _parse_date(p.get("scheduled_time") or p.get("created_at")), reverse=True)
    
    # Filter unique titles to avoid duplicates in carousel
    seen_titles = set()
    unique_posts = []
    for p in posts:
        title = p.get("title", "").strip().lower()
        if title not in seen_titles:
            seen_titles.add(title)
            unique_posts.append(p)
            if len(unique_posts) >= limit:
                break
                
    return unique_posts

def clean_body_text(text: str) -> str:
    # Remove hashtags and trailing urls
    lines = []
    for line in text.split("\n"):
        line_clean = line.strip()
        if not line_clean:
            continue
        if line_clean.lower().startswith("hashtag") or line_clean.startswith("#"):
            continue
        if "http://" in line_clean or "https://" in line_clean:
            continue
        lines.append(line_clean)
    
    body = " ".join(lines)
    if len(body) > 280:
        body = body[:277] + "..."
    return body

def get_portugal_angle(title: str, body: str) -> str:
    text = f"{title} {body}".lower()
    if any(word in text for word in ["regulation", "regul", "ai act", "gdpr", "privacy", "lei", "governo"]):
        return "Importa para decisores em Portugal que necessitam de auditar compliance antes de automatizar fluxos operacionais."
    if any(word in text for word in ["agent", "developer", "api", "open source", "model", "codigo", "program"]):
        return "Fundamental para builders e engenheiros de produto portugueses focados em testar inovação ignorando o hype."
    if any(word in text for word in ["enterprise", "business", "sales", "marketing", "work", "produtividade"]):
        return "Crucial para PMEs nacionais que procuram poupança de tempo e ganhos de eficiência operacional imediata."
    return "Ajuda o ecossistema empresarial português a separar avanço tecnológico real de narrativas promocionais."

def generate_carousel_html(posts: list[dict]):
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    
    # Format Date
    today = datetime.now()
    months_pt = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    date_str = f"{today.day} de {months_pt[today.month - 1]} de {today.year}"
    
    slides_html = []
    
    # Slide 1: Cover
    cover_html = f"""
    <section class="slide cover">
      <div class="mesh-overlay"></div>
      <div class="cover-header">
        <span class="eyebrow">PTIA WEEKLY BRIEFING</span>
        <div class="issue-badge">EDIÇÃO #{today.strftime('%W')}</div>
      </div>
      <div class="cover-content">
        <h1>Os Sinais de IA que Importam para Portugal</h1>
        <p>Curadoria independente e análise crítica sobre o impacto real dos maiores avanços de Inteligência Artificial nas empresas nacionais.</p>
      </div>
      <div class="cover-footer">
        <span class="brand-text">ptia.pt</span>
        <span class="date-text">{date_str}</span>
      </div>
    </section>
    """
    slides_html.append(cover_html)
    
    # Slides 2-5: News Content
    for idx, post in enumerate(posts, start=1):
        title = post.get("title", "Sinal de IA")
        body = clean_body_text(post.get("body", ""))
        pt_angle = get_portugal_angle(title, post.get("body", ""))
        
        # Resolve category
        category = "MUNDO"
        if "regul" in title.lower() or "ai act" in title.lower():
          category = "REGULAÇÃO"
        elif "portugal" in title.lower() or "siemens" in title.lower():
          category = "PORTUGAL"
        elif "codigo" in title.lower() or "agent" in title.lower() or "codex" in title.lower():
          category = "BUILDERS"
          
        source_name = "PTIA"
        if post.get("source_urls"):
            # extract domain name
            from urllib.parse import urlparse
            try:
                parsed = urlparse(post.get("source_urls")[0])
                source_name = parsed.netloc.replace("www.", "")
            except:
                source_name = "Fonte Oficial"
                
        news_html = f"""
        <section class="slide">
          <div class="slide-header">
            <span class="slide-index">0{idx + 1} / 0{len(posts) + 2}</span>
            <span class="slide-category">{category}</span>
          </div>
          <div class="slide-body">
            <h2>{title}</h2>
            <p class="summary">{body}</p>
            
            <div class="pt-angle-box">
              <div class="pt-badge">ÂNGULO PORTUGAL</div>
              <p class="pt-text">{pt_angle}</p>
            </div>
          </div>
          <div class="slide-footer">
            <span class="brand-text">ptia.pt</span>
            <span class="source-text">Fonte: {source_name}</span>
          </div>
        </section>
        """
        slides_html.append(news_html)
        
    # Slide 6: Outro (CTA)
    outro_html = f"""
    <section class="slide cover outro">
      <div class="mesh-overlay"></div>
      <div class="cover-content">
        <span class="eyebrow">OBRIGADO POR LER</span>
        <h1>Recebe estes sinais em primeira mão</h1>
        <p class="outro-p">Subscreve gratuitamente a nossa Weekly Briefing para receberes poucas leituras práticas e profundas sobre Inteligência Artificial, todas as sextas-feiras no teu email.</p>
        <div class="cta-box">Acede a: <strong>ptia.pt</strong></div>
      </div>
      <div class="cover-footer">
        <span class="brand-text">ptia.pt</span>
        <span class="tagline-text">Separa o sinal do ruído.</span>
      </div>
    </section>
    """
    slides_html.append(outro_html)
    
    # Combined HTML
    html_content = f"""<!doctype html>
<html lang="pt">
<head>
  <meta charset="utf-8">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Newsreader:opsz,wght@6..72,300;6..72,400;6..72,500;6..72,600&family=Geist:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    :root {{
      --navy: #051A3B;
      --navy-dark: #020C1C;
      --cream: #FAF6EC;
      --cream-dark: #F3EEE2;
      --gold: #C0A062;
      --signal: #C44419;
      --ink: #14110C;
      --ink-2: #3A332A;
      --muted: #7A715E;
      
      --serif: "Instrument Serif", Georgia, serif;
      --serif-text: "Newsreader", Georgia, serif;
      --sans: "Geist", sans-serif;
      --mono: "JetBrains Mono", monospace;
    }}
    
    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}
    
    body {{
      background: var(--cream);
      color: var(--ink);
    }}
    
    /* Layout dos Slides */
    .slide {{
      width: 1080px;
      height: 1080px;
      padding: 90px 100px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      position: relative;
      overflow: hidden;
      background: var(--cream);
      page-break-after: always;
    }}
    
    .slide:last-child {{
      page-break-after: avoid;
    }}
    
    /* Capa e Contracapa */
    .slide.cover {{
      background: var(--navy);
      color: var(--cream);
    }}
    
    .slide.outro {{
      background: linear-gradient(135deg, var(--navy-dark) 0%, var(--navy) 100%);
    }}
    
    .mesh-overlay {{
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background-image: radial-gradient(circle at 20% 30%, var(--signal) 0, transparent 40%), radial-gradient(circle at 80% 70%, var(--gold) 0, transparent 45%);
      opacity: 0.15;
      pointer-events: none;
    }}
    
    /* Tipografia e Conteúdo */
    .eyebrow {{
      font-family: var(--sans);
      font-size: 1.1rem;
      font-weight: 700;
      letter-spacing: 0.2em;
      color: var(--gold);
      display: block;
    }}
    
    .cover-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
    
    .issue-badge {{
      font-family: var(--mono);
      font-size: 0.95rem;
      font-weight: 600;
      color: var(--cream);
      border: 1px solid var(--gold);
      padding: 6px 14px;
      border-radius: 4px;
    }}
    
    .cover-content {{
      margin: auto 0;
      position: relative;
      z-index: 2;
    }}
    
    .slide.cover h1 {{
      font-family: var(--serif);
      font-size: 5.6rem;
      font-weight: 400;
      line-height: 0.95;
      letter-spacing: -0.03em;
      margin-bottom: 24px;
      color: var(--cream);
    }}
    
    .slide.cover p {{
      font-family: var(--serif-text);
      font-size: 1.85rem;
      line-height: 1.45;
      color: var(--cream-dark);
      opacity: 0.9;
      max-width: 32ch;
    }}
    
    .slide.cover p.outro-p {{
      max-width: 38ch;
      font-size: 1.7rem;
    }}
    
    .cta-box {{
      margin-top: 40px;
      display: inline-block;
      background: var(--gold);
      color: var(--navy-dark);
      font-family: var(--sans);
      font-size: 1.4rem;
      padding: 12px 28px;
      border-radius: 99px;
    }}
    
    /* Slides Regulares */
    .slide-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 2px solid var(--rule-2);
      padding-bottom: 20px;
    }}
    
    .slide-index {{
      font-family: var(--mono);
      font-size: 1rem;
      color: var(--muted);
      letter-spacing: 0.05em;
    }}
    
    .slide-category {{
      font-family: var(--sans);
      font-size: 1rem;
      font-weight: 700;
      letter-spacing: 0.15em;
      color: var(--signal);
    }}
    
    .slide-body {{
      margin: auto 0;
    }}
    
    .slide h2 {{
      font-family: var(--serif-text);
      font-size: 3rem;
      font-weight: 500;
      color: var(--ink);
      line-height: 1.1;
      letter-spacing: -0.02em;
      margin-bottom: 24px;
      max-width: 25ch;
    }}
    
    .slide p.summary {{
      font-family: var(--serif-text);
      font-size: 1.6rem;
      line-height: 1.5;
      color: var(--ink-2);
      margin-bottom: 40px;
    }}
    
    /* Ângulo Portugal Box */
    .pt-angle-box {{
      background: var(--cream-dark);
      border-left: 5px solid var(--signal);
      padding: 24px 30px;
      border-radius: 0 8px 8px 0;
    }}
    
    .pt-badge {{
      font-family: var(--sans);
      font-size: 0.85rem;
      font-weight: 700;
      letter-spacing: 0.12em;
      color: var(--signal);
      margin-bottom: 8px;
    }}
    
    .pt-text {{
      font-family: var(--sans);
      font-size: 1.25rem;
      font-weight: 500;
      line-height: 1.45;
      color: var(--ink);
    }}
    
    /* Footers */
    .slide-footer, .cover-footer {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-top: 1px solid var(--rule-3);
      padding-top: 20px;
      font-family: var(--mono);
      font-size: 0.9rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}
    
    .slide-footer {{
      border-color: var(--rule-2);
    }}
    
    .brand-text {{
      font-family: var(--serif);
      font-size: 1.65rem;
      font-weight: 800;
      letter-spacing: 0;
      text-transform: none;
      color: var(--signal);
    }}
    
    .slide.cover .brand-text {{
      color: var(--gold);
    }}
    
    .date-text, .source-text, .tagline-text {{
      color: var(--muted);
    }}
    
    .slide.cover .date-text, .slide.cover .tagline-text {{
      color: var(--cream-dark);
      opacity: 0.7;
    }}
    
    @media print {{
      body {{
        -webkit-print-color-adjust: exact;
        print-color-adjust: exact;
      }}
      .slide {{
        page-break-inside: avoid;
        page-break-after: always;
      }}
    }}
  </style>
</head>
<body>
  {"".join(slides_html)}
</body>
</html>
"""
    with open(HTML_OUT_PATH, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"-> HTML temporário para carrossel gerado em: {HTML_OUT_PATH}")

def run_pdf_render() -> bool:
    print("-> A executar render_carousel_pdf.js com o Playwright...")
    try:
        res = subprocess.run(["node", str(NODE_RENDER_SCRIPT)], capture_output=True, text=True, check=True)
        print(res.stderr)
        out = json.loads(res.stdout)
        if out.get("ok"):
            print(f"Sucesso! PDF gerado em: {out.get('pdf_path')}")
            return True
        else:
            print(f"Falha na geração do PDF: {out.get('error')}")
            return False
    except Exception as e:
        print(f"Erro ao executar Playwright Node script: {e}")
        return False

def main():
    print("=== Gerador de Carrossel de Documentos para o LinkedIn Weekly ===")
    posts = load_recent_posts(limit=4)
    if not posts:
        print("Aviso: Não foram encontrados posts publicados ou agendados recentes. A usar dados genéricos de demonstração.")
        # Minimal mock data to ensure script always works
        posts = [
            {
                "title": "Illinois exige auditorias independentes a IA de fronteira",
                "body": "Illinois tornou-se o primeiro estado nos EUA a forçar auditorias de segurança obrigatórias anuais a modelos e laboratórios de IA. A regulamentação avança do plano teórico e ético para regras de conformidade estrita de engenharia.",
                "scheduled_time": "2026-06-01T09:00:00+00:00"
            },
            {
                "title": "Siemens Portugal: IA industrial ditará a produtividade nacional",
                "body": "Siemens aponta a inteligência artificial industrial como o fator fulcral e insubstituível para elevar a eficiência operacional. O segredo competitividade futura reside em fundir software com o chão de fábrica físico.",
                "scheduled_time": "2026-06-01T13:00:00+00:00"
            },
            {
                "title": "Unbabel lança pipelines modulares baseados no EuroLLM",
                "body": "A Unbabel implementou tradução autónoma configurável com custos e qualidades variáveis por caso de uso. O motor é alimentado pelo modelo europeu soberano e linguístico de alta precisão EuroLLM.",
                "scheduled_time": "2026-06-01T16:00:00+00:00"
            },
            {
                "title": "Halo NeuroAI apoia APELA na reabilitação de voz de doentes",
                "body": "A Halo NeuroAI desenvolveu interfaces neuronais e modelos de IA generativa dedicados a recuperar e simular a voz natural de doentes com Esclerose Lateral Amiotrófica (ELA).",
                "scheduled_time": "2026-06-01T21:00:00+00:00"
            }
        ]
        
    generate_carousel_html(posts)
    success = run_pdf_render()
    if success:
        print("=== Concluído! O PDF está pronto para publicação. ===")
    else:
        print("=== ERRO: Geração do PDF falhou. ===")

if __name__ == "__main__":
    main()

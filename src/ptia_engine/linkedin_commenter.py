from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import sys
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding='utf-8', errors='backslashreplace')
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding='utf-8', errors='backslashreplace')
except Exception:
    pass

from ptia_engine.search_providers import GeminiGroundedSearchProvider
from ptia_engine.models import utc_now_iso

ROOT = Path(__file__).resolve().parents[2]

# Prompt especializado para gerar comentários humanos no LinkedIn com a voz editorial da PTIA
LINKEDIN_COMMENT_PROMPT = """
Atua como editor sénior de negócios e tecnologia da PTIA (ptia.pt).
Escreve um comentário curto de alto valor acrescentado em resposta ao seguinte post de LinkedIn.

O teu objetivo é construir autoridade de marca para o PTIA: sê perspicaz, analítico, otimista com o potencial prático da tecnologia e focado na realidade empresarial de Portugal.
Adota sempre a filosofia do "Sim, e..." (adição construtiva) em vez do "Sim, mas..." (travar o progresso). Em vez de focares em barreiras, ceticismo contrariante ou conjunções adversativas (como "mas", "contudo", "no entanto"), foca-te em somar valor, propor novas ideias, e realçar caminhos impulsionadores de produtividade de forma profissional. Usa expressões e conectores aditivos ("e", "adicionalmente", "em cima disso", "além disso", "abrindo caminho para", "potenciando").

Post original do LinkedIn:
"{post_body}"

Regra de Relevância Absoluta (Filtro Obrigatório):
Antes de escreveres, avalia se o post original está relacionado de alguma forma com inteligência artificial, tecnologia de negócios, software, inovação digital, regulação de tecnologia ou impacto tecnológico na produtividade empresarial. 
Se o post NÃO for de todo relevante para esta linha temática (ex: se for sobre assuntos pessoais, contratações genéricas sem cariz tecnológico, festas de empresa, futebol, política geral, ou opiniões vazias), deves responder ÚNICA e ESTRICTAMENTE com a palavra "REJECT" (sem aspas, sem espaços e sem pontuação).

Regras Editoriais Estritas para o comentário:
1. Escreve exclusivamente em português europeu impecável (PT-PT), seguindo o Acordo Ortográfico de 1990.
   - NÃO traduzas jargões tecnológicos comuns na indústria em Portugal: mantém termos como "cloud" (nunca "nuvem"), "legacy" ou "legacy systems" (nunca "sistemas legados"), "compliance" (nunca "conformidade"), "hype", "pipeline", "framework", "use case", "insights", "prompt" e "roadmap" na sua forma original em inglês.
2. Sê conciso: Máximo de 380 caracteres (cerca de 1 a 2 frases curtas e fortes). O comentário tem de caber sem scroll.
3. Acrescenta valor prático: Não repitas o que está no post. Traz uma reflexão impulsionadora, focada em como capitalizar o facto, e em novas ideias que acelerem a produtividade em Portugal.
4. Filtro absoluto de clichés de IA e bajulação:
   - Proibido saudações vazias como "Excelente partilha!", "Parabéns à equipa!", "Inovador!", "Revolucionário!".
   - Proibido expressões artificiais como "panorama atual", "mergulhar profundamente", "em suma", "essencial recordar", "desbloquear o potencial".
5. Não uses hashtags nem emojis (mantém o tom sóbrio de um editorialista humano).
6. Não assines com o teu nome ou "PTIA" (a conta oficial da empresa já é visível).
7. Escreve de forma declarativa e com ritmo variável (frase curta alternada com frase analítica).


Responde apenas com o comentário final ou a palavra "REJECT", sem aspas e sem explicações adicionais.
"""


def _load_monitor_config() -> dict[str, Any]:
    config_path = ROOT / "config" / "linkedin_monitor.json"
    if config_path.exists():
        try:
            return json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"monitored_profiles": [], "max_comments_per_day": 3, "comment_cool_down_minutes": 180}

def _load_comment_history() -> list[dict[str, Any]]:
    db_path = ROOT / "data" / "linkedin_comments.jsonl"
    history = []
    if db_path.exists():
        for line in db_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    history.append(json.loads(line))
                except Exception:
                    pass
    return history

def _save_comment_record(record: dict[str, Any]) -> None:
    db_path = ROOT / "data" / "linkedin_comments.jsonl"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with open(db_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

def _count_comments_today(history: list[dict[str, Any]]) -> int:
    today_str = datetime.now(timezone.utc).date().isoformat()
    count = 0
    for record in history:
        created_date = record.get("created_at", "")[:10]
        if created_date == today_str and record.get("status") == "commented":
            count += 1
    return count

def _is_recently_commented(history: list[dict[str, Any]], cool_down_minutes: int) -> bool:
    if not history:
        return False
    # Get last comment record
    last_record = history[-1]
    last_time_str = last_record.get("created_at", "")
    if not last_time_str:
        return False
    try:
        last_time = datetime.fromisoformat(last_time_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        diff = (now - last_time).total_seconds() / 60
        return diff < cool_down_minutes
    except Exception:
        return False

def _run_node_command(args: list[str]) -> dict[str, Any]:
    cmd = ["node", str(ROOT / "scripts" / "linkedin_automation.js")] + args
    try:
        result = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=90,
            check=False
        )
        if result.returncode != 0:
            return {"ok": False, "error": result.stderr or result.stdout or f"Exit code {result.returncode}"}
        
        if not result.stdout:
            return {"ok": False, "error": f"result.stdout is empty or None. Stderr: {result.stderr}"}
            
        # Parse last line of stdout as JSON
        output_lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if not output_lines:
            return {"ok": False, "error": "Sem output JSON do script Node"}
        
        try:
            return json.loads(output_lines[-1])
        except json.JSONDecodeError:
            return {"ok": False, "error": f"JSON inválido no output: {output_lines[-1]}"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Timeout expirado ao correr automação do LinkedIn (90s)"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def _is_post_too_old(relative_time: str) -> bool:
    # Filter out posts older than 1 or 2 days
    raw = relative_time.lower().strip()
    if not raw:
        return False
    # If mentions "week", "month", "year", "w", "mo", "yr", it is too old
    for marker in ("week", "month", "year", "semana", "mês", "ano", "dias", "days"):
        if marker in raw:
            # Check if it is e.g. "3 days ago" (which is fine, <= 5 days)
            if "dia" in marker or "day" in marker:
                # Extract first digits
                import re
                match = re.search(r"\d+", raw)
                if match:
                    days = int(match.group(0))
                    if days > 2: # Keep comments strictly to very fresh posts (<= 2 days)
                        return True
                    return False
            return True
    return False

def run_linkedin_comments_pipeline() -> dict[str, Any]:
    print("=== INICIANDO MOTOR DE COMENTÁRIOS AUTOMÁTICOS LINKEDIN ===")
    
    config = _load_monitor_config()
    history = _load_comment_history()
    
    monitored = [p for p in config.get("monitored_profiles", []) if p.get("active")]
    max_per_day = config.get("max_comments_per_day", 3)
    cool_down = config.get("comment_cool_down_minutes", 180)
    
    # 1. Verificar limites diários de segurança
    audit_mode = config.get("audit_mode", False)
    if audit_mode:
        print("-> MODO DE AUDITORIA (DRAFT) ATIVO. O robot não publicará nenhum comentário.")
        
    comments_today = _count_comments_today(history)
    print(f"-> Comentários publicados hoje: {comments_today} / {max_per_day}")
    if not audit_mode and comments_today >= max_per_day:
        print("-> Limite diário de comentários atingido! Cancelando pipeline por segurança.")
        return {"ok": True, "status": "limit_reached", "comments_today": comments_today}
        
    # 2. Verificar cooling down period
    if not audit_mode and _is_recently_commented(history, cool_down):
        print(f"-> Período de arrefecimento ativo (mínimo {cool_down} min entre posts)! Cancelando pipeline por segurança.")
        return {"ok": True, "status": "cooling_down"}

    commented_urns = {record["urn"] for record in history if "urn" in record}
    provider = GeminiGroundedSearchProvider()
    
    if not provider.available:
        print("-> ERRO: GEMINI_API_KEY não configurada! Não consigo gerar comentários.")
        return {"ok": False, "error": "GEMINI_API_KEY_MISSING"}

    success_count = 0
    
    # 3. Processar cada perfil monitorizado
    for profile in monitored:
        if comments_today >= max_per_day:
            break
            
        name = profile.get("name", "Desconhecido")
        url = profile.get("url", "")
        print(f"\n-> A analisar publicações recentes de: {name} ({url})")
        
        # Scrape recent posts
        result = _run_node_command(["scrape-profile", url])
        if not result.get("ok"):
            print(f"   [Falhou] Scraping falhou: {result.get('error')}")
            continue
            
        posts = result.get("posts", [])
        print(f"   Encontradas {len(posts)} publicações.")
        
        # Avaliar cada post
        for post in posts:
            urn = post.get("urn")
            post_url = post.get("url")
            body = post.get("body", "").strip()
            relative_time = post.get("relative_time", "")
            
            if not urn or not body:
                continue
                
            # Verificar se já comentámos esta publicação
            if urn in commented_urns:
                continue
                
            # Verificar se a publicação é demasiado antiga
            if _is_post_too_old(relative_time):
                print(f"   [Ignorado] Publicação demasiado antiga ({relative_time}): {body[:40]}...")
                continue
                
            # 4. Avaliar relevância com Gemini
            print(f"   [Novo Post] {urn} ({relative_time})")
            print(f"   Texto: {body[:120]}...")
            
            # Vamos pedir ao Gemini para gerar o comentário
            prompt = LINKEDIN_COMMENT_PROMPT.format(post_body=body)
            try:
                # Usar o backend REST do Gemini para gerar a resposta
                raw_response = provider._generate_json_response(prompt, temperature=0.72)
                candidate = (raw_response.get("candidates") or [{}])[0]
                parts = ((candidate.get("content") or {}).get("parts") or [])
                generated_comment = "\n".join(str(part.get("text", "")) for part in parts if isinstance(part, dict)).strip()
                
                # Clean up markdown code wrapping if Gemini returned it
                generated_comment = generated_comment.strip().strip('"').strip("'").replace("```json", "").replace("```", "").strip()
            except Exception as e:
                print(f"   [Falhou] Erro ao gerar comentário com Gemini: {e}")
                continue
                
            if not generated_comment:
                print("   [Falhou] Gemini devolveu comentário vazio.")
                continue
                
            if generated_comment.upper().strip() == "REJECT":
                print("   [Ignorado] Gemini classificou o post como irrelevante para a linha editorial (REJECT).")
                # Gravar registo de rejeição para evitar reprocessar
                record = {
                    "urn": urn,
                    "profile_name": name,
                    "post_url": post_url,
                    "post_body": body,
                    "status": "rejected_by_ai",
                    "created_at": utc_now_iso()
                }
                _save_comment_record(record)
                continue
                
            print(f"   [Comentário Gerado] ({len(generated_comment)} chars):\n   \"{generated_comment}\"")
            
            # 5. Executar automação de post de comentário
            if audit_mode:
                print("   [Audit Mode] A chamar Playwright para criar rascunho de comentário...")
                post_result = _run_node_command(["post-comment", post_url, generated_comment, "draft"])
            else:
                print("   A chamar Playwright para submeter comentário ao vivo...")
                post_result = _run_node_command(["post-comment", post_url, generated_comment])
            
            if post_result.get("ok"):
                # Gravar registo de sucesso
                status = "draft" if audit_mode else "commented"
                record = {
                    "urn": urn,
                    "profile_name": name,
                    "post_url": post_url,
                    "post_body": body,
                    "comment_text": generated_comment,
                    "screenshot_path": post_result.get("screenshot", ""),
                    "status": status,
                    "created_at": utc_now_iso()
                }
                _save_comment_record(record)
                commented_urns.add(urn)
                if not audit_mode:
                    comments_today += 1
                success_count += 1
                msg = "Rascunho criado!" if audit_mode else "Comentário publicado!"
                print(f"   [Sucesso] {msg} Limite hoje: {comments_today} / {max_per_day}")
                
                # Cooling down manual de 5 segundos para segurança do browser
                time.sleep(5)
                break # Apenas comentar 1 post por ciclo de execução por perfil para máxima discrição!
            else:
                print(f"   [Falhou] Submissão falhou: {post_result.get('error')}")
                # Registar falha para evitar tentar o mesmo post consecutivamente
                record = {
                    "urn": urn,
                    "profile_name": name,
                    "post_url": post_url,
                    "post_body": body,
                    "status": "failed",
                    "error": post_result.get("error", ""),
                    "created_at": utc_now_iso()
                }
                _save_comment_record(record)
                
    print(f"\n=== MOTOR DE COMENTÁRIOS CONCLUÍDO. {success_count} COMENTÁRIOS PUBLICADOS. ===")
    return {"ok": True, "comments_posted": success_count}

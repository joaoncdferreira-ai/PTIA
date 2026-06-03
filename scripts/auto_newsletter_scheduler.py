import os
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Adjust PYTHONPATH to include 'src'
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from ptia_engine.storage import (
    load_radar_signals,
    load_trend_signals,
    load_final_posts,
    load_content_performance,
    load_newsletter_issues,
)
from ptia_engine.newsletter import generate_weekly_issue, _parse_date

def main():
    print("=== PTIA Automated Weekly Newsletter Scheduler ===")
    
    # Path configuration
    data_dir = ROOT / "data"
    issues_path = data_dir / "newsletter_issues.jsonl"
    radar_path = data_dir / "radar_signals.jsonl"
    trends_path = data_dir / "trend_signals.jsonl"
    final_posts_path = data_dir / "final_posts.jsonl"
    performance_path = data_dir / "content_performance.jsonl"
    
    # Check force flag
    force = "--force" in sys.argv
    
    # 1. Duplicate check (only 1 newsletter per week, i.e. 6 days interval)
    if not force and issues_path.exists():
        try:
            issues = load_newsletter_issues(issues_path)
            if issues:
                # Get the most recent issue
                issues.sort(key=lambda x: _parse_date(x.created_at), reverse=True)
                latest_issue = issues[0]
                latest_date = _parse_date(latest_issue.created_at)
                
                # Check if it was created less than 6 days ago
                elapsed = datetime.now(timezone.utc) - latest_date
                if elapsed < timedelta(days=6):
                    print(f"Aviso: Uma newsletter já foi compilada há {elapsed.days} dias (ID: {latest_issue.issue_id}).")
                    print("Compilação ignorada para evitar duplicações. Usa '--force' para forçar a geração.")
                    return
        except Exception as e:
            print(f"Erro ao validar histórico de newsletters: {e}")
            
    # 2. Load candidates and compile
    print("-> A carregar bases de dados locais...")
    radar_signals = load_radar_signals(radar_path) if radar_path.exists() else []
    trend_signals = load_trend_signals(trends_path) if trends_path.exists() else []
    final_posts = load_final_posts(final_posts_path) if final_posts_path.exists() else []
    performance = load_content_performance(performance_path) if performance_path.exists() else []
    
    print(f"   Radar: {len(radar_signals)} | Trends: {len(trend_signals)} | Posts: {len(final_posts)} | Performance: {len(performance)}")
    
    print("-> A compilar a edição da newsletter semanal...")
    try:
        issue = generate_weekly_issue(
            issues_path,
            radar_signals=radar_signals,
            trend_signals=trend_signals,
            final_posts=final_posts,
            performance=performance,
            limit=5,
        )
        print(f"\nEdição compilada com sucesso!")
        print(f"ID da Issue: {issue.issue_id}")
        print(f"Assunto:    {issue.subject}")
        print(f"Status:     {issue.status} (Rascunho pronto no painel editorial)")
        print(f"Gravado em:  {issues_path}")
        print("\n=== Concluído com Sucesso! ===")
    except Exception as e:
        print(f"\nERRO ao compilar newsletter: {e}")
        print("Certifica-te de que existem sinais ou posts recentes na base de dados.")
        sys.exit(1)

if __name__ == "__main__":
    main()

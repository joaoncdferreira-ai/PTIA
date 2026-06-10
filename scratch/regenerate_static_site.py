import os
from pathlib import Path
import sys

ROOT = Path("c:/Users/joaon/ptia-content-engine")
sys.path.insert(0, str(ROOT / "src"))

def load_dotenv():
    env_path = ROOT / ".env.local"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

load_dotenv()

# Configurar a variável de ambiente para usar a CDN pública do GitHub
os.environ["PTIA_PUBLIC_ASSET_BASE_URL"] = "https://raw.githubusercontent.com/joaoncdferreira-ai/PTIA/main/site"

from ptia_engine.dashboard import DashboardState, _sync_static_site_feed

state = DashboardState(ROOT / "data")
print("Regenerando feed estático e páginas de artigos do site...")
try:
    _sync_static_site_feed(state, git_push=True, deploy=True)
    print("Sucesso: Site estático e feed regenerados e sincronizados com o Git/Vercel.")
except Exception as e:
    print(f"Erro na regeneração: {e}")

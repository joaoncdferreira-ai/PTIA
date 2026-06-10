import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# Load local env
def load_local_env() -> None:
    for filename in (".env", ".env.local"):
        path = ROOT / filename
        if not path.exists():
            continue
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value

try:
    import os
    load_local_env()
    from ptia_engine.dashboard import serve_dashboard
    serve_dashboard(ROOT / "data", port=8765)
except Exception as e:
    with open(str(ROOT / "pythonw_error.txt"), "w") as f:
        f.write(traceback.format_exc())

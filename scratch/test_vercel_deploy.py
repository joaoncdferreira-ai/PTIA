import os
import sys
import subprocess
import shutil
from pathlib import Path

ROOT = Path("c:/Users/joaon/ptia-content-engine")
sys.path.insert(0, str(ROOT / "src"))

from ptia_engine.dashboard import DashboardState, _can_auto_deploy_site

state = DashboardState(ROOT / "data")

print("Can auto deploy:", _can_auto_deploy_site(state))

vercel_cmd = shutil.which("vercel.cmd") or shutil.which("vercel")
print("Vercel CLI path:", vercel_cmd)

if vercel_cmd:
    env = os.environ.copy()
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "GIT_HTTP_PROXY", "GIT_HTTPS_PROXY"):
        env[key] = ""
        
    print("Running vercel deploy...")
    result = subprocess.run(
        [vercel_cmd, "deploy", "--prod", "--yes"],
        cwd=state.site_dir,
        capture_output=True,
        text=True,
        timeout=180,
        env=env,
        check=False,
    )
    print("Return code:", result.returncode)
    print("Stdout:", result.stdout)
    print("Stderr:", result.stderr)
else:
    print("Vercel CLI not found")

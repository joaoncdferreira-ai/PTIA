import subprocess
import os
from pathlib import Path

ROOT = Path(r"c:\Users\joaon\ptia-content-engine")

def main():
    tests_dir = ROOT / "tests"
    tests = sorted([f for f in os.listdir(tests_dir) if f.startswith("test_") and f.endswith(".py")])
    
    print(f"Found {len(tests)} test files. Diagnosing...")
    
    for t in tests:
        print(f"Running {t}...", end=" ", flush=True)
        try:
            res = subprocess.run(
                ["uv", "run", "pytest", f"tests/{t}"],
                capture_output=True,
                text=True,
                timeout=12,
                cwd=str(ROOT),
                env={**os.environ, "PYTHONPATH": str(ROOT / "src")}
            )
            if res.returncode == 0:
                print("SUCCESS")
            else:
                print(f"FAILED (code {res.returncode})")
                print(res.stdout[:500])
                print(res.stderr[:500])
        except subprocess.TimeoutExpired:
            print("HUNG/TIMEOUT")

if __name__ == "__main__":
    main()

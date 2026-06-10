import importlib.util
import os
import sys
from pathlib import Path

ROOT = Path(r"c:\Users\joaon\ptia-content-engine")
sys.path.insert(0, str(ROOT / "src"))

def main():
    tests_dir = ROOT / "tests"
    tests = sorted([f for f in os.listdir(tests_dir) if f.startswith("test_") and f.endswith(".py")])
    
    print(f"Importing {len(tests)} test files in one process...")
    for t in tests:
        print(f"Importing {t}...", flush=True)
        spec = importlib.util.spec_from_file_location(t[:-3], tests_dir / t)
        module = importlib.util.module_from_spec(spec)
        sys.modules[t[:-3]] = module
        spec.loader.exec_module(module)
        print(f"Finished importing {t}", flush=True)
        
    print("All imported successfully!")

if __name__ == "__main__":
    main()

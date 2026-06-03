@echo off
cd /d C:\Users\joaon\ptia-content-engine
set "PYTHONPATH=C:\Users\joaon\ptia-content-engine\src"
start "" /B "C:\Users\joaon\AppData\Local\Programs\Python\Python313\pythonw.exe" -c "import sys; sys.path.insert(0, r'C:\Users\joaon\ptia-content-engine\src'); from pathlib import Path; from ptia_engine.dashboard import serve_dashboard; serve_dashboard(Path(r'C:\Users\joaon\ptia-content-engine\data'), port=8765)"

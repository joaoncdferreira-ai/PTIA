@echo off
cd /d C:\Users\joaon\ptia-content-engine
set "PYTHONPATH=C:\Users\joaon\ptia-content-engine\src"
set "PYTHONUTF8=1"
set "PYTHONUNBUFFERED=1"
echo [%date% %time%] Iniciando execucao do motor de comentarios... >> "C:\Users\joaon\ptia-content-engine\data\linkedin_comments_run.log"
"C:\Users\joaon\AppData\Local\Programs\Python\Python313\python.exe" -u -m ptia_engine.cli linkedin-comments >> "C:\Users\joaon\ptia-content-engine\data\linkedin_comments_run.log" 2>&1
echo [%date% %time%] Execucao concluida. >> "C:\Users\joaon\ptia-content-engine\data\linkedin_comments_run.log"

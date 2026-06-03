# Script de Execução Automatizada do Motor de Comentários PTIA
# Este script fecha processos fantasmas para evitar conflitos de cache e executa o pipeline.

try {
    # 1. Fechar apenas processos do Chromium do Playwright, sem afetar o Google Chrome pessoal do utilizador
    Get-Process -Name "chrome" -ErrorAction SilentlyContinue | Where-Object {
        try {
            $_.Path -like "*ms-playwright*" -or $_.Path -like "*ptia-content-engine*"
        } catch { $false }
    } | Stop-Process -Force -ErrorAction SilentlyContinue
} catch {}

# 2. Navegar para o diretório do projeto
cd "c:\Users\joaon\ptia-content-engine"

# 3. Definir a variável de ambiente PYTHONPATH
$env:PYTHONPATH="src"

# 4. Executar o pipeline operacional de comentários do LinkedIn
python -m ptia_engine.cli linkedin-comments

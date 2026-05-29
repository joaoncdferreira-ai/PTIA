#!/usr/bin/env bash
set -e

# 1. Configurar credenciais globais de Git no container
git config --global user.email "bot@ptia.pt"
git config --global user.name "PTIA Cloud Curation Bot"

# 2. Configurar o remote do Git com o Token de Acesso se disponível
if [ -n "$GITHUB_PAT" ]; then
  echo "-> Configurando remote seguro com GITHUB_PAT..."
  git remote set-url origin "https://${GITHUB_PAT}@github.com/joaoncdferreira-ai/PTIA.git"
else
  echo "-> [AVISO] GITHUB_PAT não configurado. Commits e Pushes do dashboard podem falhar."
fi

# 3. Lançar o dashboard ligando ao host 0.0.0.0 (obrigatório em Cloud) e porto dinâmico do Render
echo "-> Iniciando PTIA Editorial Dashboard no porto $PORT..."
PYTHONPATH=src python -m ptia_engine.cli dashboard --host 0.0.0.0 --port "$PORT"

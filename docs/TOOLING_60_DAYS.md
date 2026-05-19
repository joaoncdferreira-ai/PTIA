# Tooling para os proximos 60 dias

Objetivo: manter o PTIA abaixo de 30 EUR/mes enquanto melhora qualidade editorial e automacao.

## Skills a usar

- `openai-docs`: chamadas OpenAI, structured outputs, modelos e custos.
- `content-strategy`: calendario editorial, pilares e rotina.
- `copywriting`: drafts finais para LinkedIn, Instagram, site e newsletter.
- `copy-editing`: revisao PT-PT, clareza e reducao de hype.
- `social-content`: formatos sociais e adaptacao por canal.
- `ai-seo`: quando o site/newsletter comecar a ganhar arquivo.
- `seo-content`: avaliar qualidade dos artigos evergreen.
- `analytics-tracking`: quando houver publicacoes consistentes.
- `brandkit`: identidade visual e sistema de templates.
- `python-testing`: quando o CLI crescer.

## MCPs/tools disponiveis

### Usar agora

- `n8n MCP` para pesquisar nodes/templates e desenhar workflows futuros.
- `node_repl` para transformacoes pontuais de dados.
- `OpenAI docs` via skill/browser quando mexermos na API.

### Usar depois

- `Browser` quando existir dashboard/site local.
- `code_review_graph` quando o codigo crescer.
- `Firebase MCP` apenas se escolhermos Firebase, o que nao e recomendado no MVP.

## n8n descoberto

Nodes uteis:

- `rssFeedRead`
- `rssFeedReadTrigger`
- `airtable`
- `airtableTrigger`
- `openAi`
- `lmChatOpenAi`
- `httpRequest` para Buffer/Ghost APIs

Templates uteis:

- `3986`: newsletter personalizada com RSS + OpenAI + Gmail.
- `4005`: posts LinkedIn com OpenAI + approval workflow.

Recomendacao: nao usar n8n Cloud enquanto nao houver receita. Usar apenas como referencia ou, se necessario, self-host/local.

## Dependencias Python declaradas

Declaradas em `pyproject.toml`:

- `openai`: chamadas AI oficiais.
- `feedparser`: RSS/Atom robusto.
- `beautifulsoup4`: limpeza HTML.
- `rapidfuzz`: deduplicacao por similaridade melhor que `difflib`.
- `pydantic`: schemas e validacao.
- `pyairtable`: integracao Airtable.
- `requests`: APIs externas como Buffer/Ghost.
- `python-dotenv`: carregar `.env`.
- `pytest` e `ruff` em `dev`.

## Estado da instalacao

Tentativas feitas:

- `python -m venv .venv`: falhou na etapa `ensurepip` por permissao ao copiar wheels temporarias.
- `pip install`: ficou preso apesar de permissao de rede e `PIP_NO_INDEX=0`.
- `uv sync --extra dev`: tambem ficou preso.

Conclusao: o projecto esta preparado para instalar dependencias, mas o ambiente atual bloqueou instaladores. O codigo V0 continua funcional sem dependencias externas.

Quando o instalador estiver destravado, correr:

```powershell
cd C:\Users\joaon\ptia-content-engine
uv sync --extra dev
```

Alternativa:

```powershell
python -m pip install -e ".[dev]"
```

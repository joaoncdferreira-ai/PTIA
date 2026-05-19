# Setup V0

## Requisitos

- Python 3.11+
- Sem dependencias externas na V0
- Acesso a internet para ingestao RSS

## Inicializar

```powershell
cd C:\Users\joaon\ptia-content-engine
$env:PYTHONPATH="src"
python -m ptia_engine.cli init-data
```

## Ingerir fontes

```powershell
$env:PYTHONPATH="src"
python -m ptia_engine.cli ingest --sources config\sources.sample.json --out data\raw_articles.jsonl --limit-per-source 5
```

Resultado validado em 2026-05-14:

- 10 fontes ativas
- 50 artigos recolhidos
- 48 artigos escritos
- 0 erros de fonte

## Gerar briefing

```powershell
$env:PYTHONPATH="src"
python -m ptia_engine.cli briefing --articles data\raw_articles.jsonl --out data\daily_briefing.md --limit 10
```

## Classificar artigos

Modo gratuito/local:

```powershell
$env:PYTHONPATH="src"
python -m ptia_engine.cli classify --mode heuristic --articles data\raw_articles.jsonl --out data\processed_items.jsonl --limit 20
```

Modo OpenAI API:

```powershell
$env:PYTHONPATH="src"
$env:OPENAI_API_KEY="..."
python -m ptia_engine.cli classify --mode openai --articles data\raw_articles.jsonl --out data\processed_items.jsonl --limit 10 --monthly-budget-usd 20
```

Notas:

- O modo `heuristic` custa zero e serve para testar a fila editorial.
- O modo `openai` estima custo antes de chamar a API e escreve em `data\usage_ledger.jsonl`.
- A V0 usa `gpt-4.1-mini` por defeito. Segundo a documentacao oficial da OpenAI, este modelo suporta Chat Completions, Responses e structured outputs.
- O preco oficial visto em 2026-05-14 para `gpt-4.1-mini` era 0.40 USD por 1M input tokens e 1.60 USD por 1M output tokens.

## Gerar fila de revisao

```powershell
$env:PYTHONPATH="src"
python -m ptia_engine.cli review --articles data\raw_articles.jsonl --processed data\processed_items.jsonl --out data\review_queue.md --limit 10
```

Resultado atual validado em 2026-05-14:

- 48 artigos classificados localmente
- 16 candidatos para revisao
- 32 rejeitados pela heuristica
- custo AI: 0 USD

## Gerar drafts template

```powershell
$env:PYTHONPATH="src"
python -m ptia_engine.cli draft --articles data\raw_articles.jsonl --processed data\processed_items.jsonl --out data\content_drafts.jsonl --limit 5
```

Isto gera, para cada candidato, rascunhos para:

- LinkedIn
- Instagram caption
- Instagram carousel
- site
- newsletter

Na V0 estes drafts sao estruturais. Servem para acelerar revisao, nao para publicar sem edicao humana.

Exportar para Markdown:

```powershell
$env:PYTHONPATH="src"
python -m ptia_engine.cli export-drafts --drafts data\content_drafts.jsonl --out data\drafts_review.md --limit 20
```

## Exportar para Airtable

```powershell
$env:PYTHONPATH="src"
python -m ptia_engine.cli export-csv --out-dir data\exports
```

Ficheiros gerados:

- `sources.csv`
- `raw_articles.csv`
- `processed_items.csv`
- `content_drafts.csv`

Importar cada CSV para a tabela correspondente na base `PTIA Editorial Engine`.

## Rotina diaria completa

```powershell
$env:PYTHONPATH="src"
python -m ptia_engine.cli daily-run
```

Este comando corre:

1. `init-data`
2. `ingest`
3. `briefing`
4. `learn`
5. `classify`
6. `review`
7. `draft`
8. `export-drafts`
9. `export-csv`

Outputs principais:

- `data\daily_briefing.md`
- `data\review_queue.md`
- `data\drafts_review.md`
- `data\exports\*.csv`

## Dashboard local

```powershell
$env:PYTHONPATH="src"
python -m ptia_engine.cli dashboard --port 8765
```

Abrir:

```text
http://127.0.0.1:8765
```

A dashboard mostra:

- funil: extracao, classificacao, drafts, scheduling e published
- fila de revisao humana
- drafts por canal
- posts prontos para schedule
- posts published
- formulario de metricas por post
- learnings calculados a partir de likes, comments, shares, saves, clicks e followers

Na V0, as metricas sao inseridas manualmente. Mais tarde podem vir de Buffer/LinkedIn/Instagram APIs.

## Learning loop

Depois de registar métricas de posts publicados:

```powershell
$env:PYTHONPATH="src"
python -m ptia_engine.cli learn --min-samples 3
```

Isto gera:

```text
config\learning_weights.json
```

O classificador local usa estes pesos para ajustar relevancia por fonte e seccao:

```powershell
$env:PYTHONPATH="src"
python -m ptia_engine.cli classify --mode heuristic --learning-weights config\learning_weights.json
```

Regra editorial: com pouca amostra, o sistema recomenda mas nao altera pesos. Isto evita aprender conclusoes falsas a partir de 1 ou 2 posts.

## Trend Radar

Buscar sinais de engagement fora de Portugal:

```powershell
$env:PYTHONPATH="src"
python -m ptia_engine.cli trend-radar
```

Outputs:

- `data\trend_signals.jsonl`
- `data\trend_radar.md`

Na V0, o radar usa Hacker News porque tem API publica limpa e e uma boa proxy para builders e early adopters. Isto nao serve para copiar posts virais. Serve para perceber:

- que temas tiveram interesse;
- que tensao ou curiosidade gerou comentarios;
- que formato pode ser traduzido para PTIA;
- que angulo portugues faz sentido.

## Drafts finais com provider LLM

Depois de aprovar items na dashboard:

```powershell
$env:PYTHONPATH="src"
python -m ptia_engine.cli ai-drafts --provider template --limit 3
```

Opcoes:

- `template`: custo zero, local, qualidade estrutural.
- `gemini`: usar com `GEMINI_API_KEY`, primeira opcao externa para testar custo baixo.
- `ollama`: local/open source, requer Ollama a correr em `OLLAMA_BASE_URL`.
- `openai`: opcional, usar com `OPENAI_API_KEY` e limite mensal.

Exemplos:

```powershell
$env:PYTHONPATH="src"
$env:GEMINI_API_KEY="..."
python -m ptia_engine.cli ai-drafts --provider gemini --limit 3

$env:PYTHONPATH="src"
$env:OLLAMA_MODEL="llama3.1"
python -m ptia_engine.cli ai-drafts --provider ollama --limit 3

$env:PYTHONPATH="src"
$env:OPENAI_API_KEY="..."
python -m ptia_engine.cli ai-drafts --provider openai --limit 3 --monthly-budget-usd 20
```

Regras:

- so gera drafts para items com `approved_for_draft` por defeito;
- escreve drafts com estado `needs_edit`;
- regista uso em `data\usage_ledger.jsonl`;
- muda o item para `draft_ready`;
- nao publica nada.

Decisao de produto: enquanto nao houver receita, a rotina diaria deve funcionar com `template`, `gemini` free tier ou `ollama`. OpenAI fica como benchmark pago, nao como dependencia obrigatoria.

Mais detalhe: `docs\LLM_PROVIDERS.md`.

## Asset Factory

Gerar SVGs PTIA para posts e carrosseis:

```powershell
$env:PYTHONPATH="src"
python -m ptia_engine.cli assets --limit 12
```

Outputs:

- SVGs em `data\assets`
- ledger em `data\content_assets.jsonl`
- tab `Assets` na dashboard

Na V0 usamos SVGs de template para manter consistencia e custo zero. Imagens generativas ficam para evergreen, reports ou posts especiais.

## Aprovar/rejeitar localmente

Aprovar item para draft:

```powershell
$env:PYTHONPATH="src"
python -m ptia_engine.cli item-status --item-id item_xxx --status approved_for_draft --notes "Bom angulo para builders."
```

Rejeitar item:

```powershell
$env:PYTHONPATH="src"
python -m ptia_engine.cli item-status --item-id item_xxx --status rejected --notes "Sem impacto claro para PTIA."
```

Aprovar draft para scheduling:

```powershell
$env:PYTHONPATH="src"
python -m ptia_engine.cli draft-status --draft-id draft_xxx_linkedin --status approved --scheduled-time "2026-05-15T08:30:00+01:00"
```

Exportar fila para scheduling manual/Buffer:

```powershell
$env:PYTHONPATH="src"
python -m ptia_engine.cli export-schedule --out data\scheduling_queue.csv
```

## Testes

```powershell
$env:PYTHONPATH="src"
python -m unittest discover -s tests
```

## Fontes candidatas a rever

Estas fontes estao no ficheiro de configuracao mas inativas:

- Anthropic News: sem RSS publico obvio; considerar scraping permitido ou fonte secundaria.
- LangChain Blog: feed atual falha no parser XML leve; rever com `feedparser` se aceitarmos dependencia.
- European Commission Digital Strategy AI: feed amplo e XML problematico; rever com parser mais tolerante.
- Portugal Digital, AMA, CNPD: confirmar RSS ou processo manual.

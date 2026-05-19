# PTIA Content Engine

Motor editorial semi-automatico para curadoria portuguesa sobre Inteligencia Artificial.

Objetivo da V0:

```text
fontes -> artigos brutos -> deduplicacao -> candidatos -> drafts -> revisao humana -> publicacao
```

Nada deve ser publicado sem aprovacao humana.

## Orçamento

A primeira versao foi desenhada para ficar abaixo de 30 EUR/mes:

- Airtable Free ou ficheiros locais enquanto o schema estabiliza
- Python para jobs e ingestao
- Drafts gratuitos por defeito; Gemini/Ollama/OpenAI opcionais por provider
- Buffer Free ou publicacao manual no inicio
- Substack para site/newsletter inicial
- Canva Free

## Estrutura

```text
config/
  sources.sample.json       Fontes RSS iniciais
data/
  .gitkeep                  Dados locais de desenvolvimento
docs/
  AIRTABLE_SCHEMA.md        Schema editorial
  EDITORIAL_GUIDE.md        Voz, regras e criterios
  IMPLEMENTATION_ROADMAP.md Roadmap de execucao
prompts/
  classification.md         Prompt de classificacao
  editorial_draft.md        Prompt de resumo e drafts
  risk_check.md             Prompt de verificacao editorial
src/ptia_engine/
  cli.py                    Comandos locais
  dedupe.py                 Deduplicacao por URL/titulo
  llm_providers.py          Providers template, Gemini, Ollama e OpenAI
  models.py                 Modelos internos
  rss.py                    Ingestao RSS/Atom
```

## Comandos

Entrar na pasta:

```powershell
cd C:\Users\joaon\ptia-content-engine
$env:PYTHONPATH="src"
```

Criar ficheiros locais de dados:

```powershell
python -m ptia_engine.cli init-data
```

Ingerir RSS para `data/raw_articles.jsonl`:

```powershell
python -m ptia_engine.cli ingest --sources config/sources.sample.json --out data/raw_articles.jsonl
```

Gerar briefing local simples:

```powershell
python -m ptia_engine.cli briefing --articles data/raw_articles.jsonl --out data/daily_briefing.md
```

Classificar artigos sem custo, usando heuristica local:

```powershell
python -m ptia_engine.cli classify --mode heuristic --articles data/raw_articles.jsonl --out data/processed_items.jsonl --limit 20
```

Classificar com OpenAI API, respeitando limite mensal:

```powershell
$env:OPENAI_API_KEY="..."
python -m ptia_engine.cli classify --mode openai --articles data/raw_articles.jsonl --out data/processed_items.jsonl --limit 10 --monthly-budget-usd 20
```

Gerar fila de revisao humana:

```powershell
python -m ptia_engine.cli review --articles data/raw_articles.jsonl --processed data/processed_items.jsonl --out data/review_queue.md
```

Gerar drafts template para os candidatos:

```powershell
python -m ptia_engine.cli draft --articles data/raw_articles.jsonl --processed data/processed_items.jsonl --out data/content_drafts.jsonl --limit 5
```

Exportar drafts para Markdown:

```powershell
python -m ptia_engine.cli export-drafts --drafts data/content_drafts.jsonl --out data/drafts_review.md
```

Exportar CSVs para importar no Airtable:

```powershell
python -m ptia_engine.cli export-csv --out-dir data/exports
```

Executar a rotina diaria local completa:

```powershell
python -m ptia_engine.cli daily-run
```

Gerar pesos de aprendizagem a partir das métricas:

```powershell
python -m ptia_engine.cli learn --min-samples 3
```

Gerar drafts editoriais finais, apenas para items aprovados:

```powershell
python -m ptia_engine.cli ai-drafts --provider template --limit 3
python -m ptia_engine.cli ai-drafts --provider gemini --limit 3
python -m ptia_engine.cli ai-drafts --provider ollama --limit 3
python -m ptia_engine.cli ai-drafts --provider openai --limit 3 --monthly-budget-usd 20
```

Gerar assets SVG para LinkedIn/Instagram:

```powershell
python -m ptia_engine.cli assets --limit 12
```

Buscar sinais de engagement AI no Hacker News:

```powershell
python -m ptia_engine.cli trend-radar
```

Abrir dashboard local:

```powershell
python -m ptia_engine.cli dashboard --port 8765
```

Depois abrir:

```text
http://127.0.0.1:8765
```

Aprovar/rejeitar um item:

```powershell
python -m ptia_engine.cli item-status --item-id item_xxx --status approved_for_draft --notes "Bom angulo para builders."
python -m ptia_engine.cli item-status --item-id item_xxx --status rejected --notes "Sem impacto claro."
```

Aprovar um draft e exportar fila de scheduling:

```powershell
python -m ptia_engine.cli draft-status --draft-id draft_xxx_linkedin --status approved --scheduled-time "2026-05-15T08:30:00+01:00"
python -m ptia_engine.cli export-schedule --out data/scheduling_queue.csv
```

Executar testes:

```powershell
python -m unittest discover -s tests
```

## Proximos passos

1. Confirmar dominio e nome final.
2. Criar base Airtable com o schema em `docs/AIRTABLE_SCHEMA.md`.
3. Testar 10 fontes RSS durante 7 dias.
4. Ligar classificacao AI apenas depois de a ingestao estar estavel.
5. Rever manualmente os candidatos diarios antes de qualquer agendamento.

Ver tambem `docs/LLM_PROVIDERS.md` para a politica de custo/qualidade dos modelos.

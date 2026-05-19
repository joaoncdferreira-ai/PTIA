# LLM Providers

Objetivo: manter a PTIA abaixo de 30 EUR/mes enquanto validamos a rotina editorial.

## Recomendacao V0

Usar por esta ordem:

1. `template`: custo zero, bom para testar o fluxo todo.
2. `gemini`: primeira opcao externa para melhorar texto mantendo custo baixo enquanto houver free tier aplicavel.
3. `ollama`: opcao local/open source, sem custo API, mas depende da maquina e normalmente exige mais edicao.
4. `openai`: opcional, so se a qualidade poupar tempo suficiente para justificar custo.

Pushback honesto: nenhuma opcao gratuita entrega sempre "o mesmo output" que um modelo pago bem configurado. O que nos interessa medir nao e benchmark abstrato; e tempo de edicao por post aprovado.

## Comando

```powershell
$env:PYTHONPATH="src"
python -m ptia_engine.cli ai-drafts --provider template --limit 3
```

Gemini:

```powershell
$env:PYTHONPATH="src"
$env:GEMINI_API_KEY="..."
python -m ptia_engine.cli ai-drafts --provider gemini --limit 3
```

Gemini Scout com Google Search grounding:

```powershell
$env:PYTHONPATH="src"
$env:GEMINI_API_KEY="..."
python -m ptia_engine.cli gemini-scout --limit 8
```

Este comando usa o Gemini apenas como radar de candidatos. A PTIA volta a validar domínio credível e data dos últimos 5 dias antes de gravar qualquer sinal em `Verified Selection`.

Ollama/local:

```powershell
$env:PYTHONPATH="src"
$env:OLLAMA_MODEL="llama3.1"
python -m ptia_engine.cli ai-drafts --provider ollama --limit 3
```

OpenAI:

```powershell
$env:PYTHONPATH="src"
$env:OPENAI_API_KEY="..."
python -m ptia_engine.cli ai-drafts --provider openai --limit 3 --monthly-budget-usd 20
```

## Variaveis

```text
PTIA_LLM_PROVIDER=template

GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.5-flash
GEMINI_SEARCH_MODEL=gemini-2.5-flash

OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=llama3.1

OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini
OPENAI_MONTHLY_BUDGET_USD=20
```

## Regra de decisao

Durante 7 dias, guardar uma nota simples por draft:

- `0`: inutilizavel
- `1`: precisa de reescrita pesada
- `2`: bom com edicao normal
- `3`: quase pronto

Se Gemini ou Ollama entregarem media >= 2, ficamos com essa opcao. Se ficarem abaixo disso e OpenAI poupar mais de 15 minutos por dia, ai sim faz sentido pagar.

## Privacidade e risco

- `template`: nada sai da maquina.
- `ollama`: nada sai da maquina, desde que o modelo esteja mesmo local.
- `gemini`/`openai`: o texto enviado vai para um fornecedor externo. Enviar apenas excertos e metadados, nunca dados privados.
- Nenhum provider publica nada. Todos geram drafts com estado `needs_edit`.

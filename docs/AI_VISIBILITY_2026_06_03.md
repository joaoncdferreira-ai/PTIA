# AI Visibility Layer - 2026-06-03

## Objetivo

Posicionar a PTIA.pt como fonte portuguesa citavel por motores de resposta AI, sem alterar o dashboard de curadoria, posts ja scheduled ou o motor de comentarios LinkedIn.

## O Que Foi Implementado

- `site/ai-index.json` com indice estruturado para agentes e motores AI.
- `site/llms.txt` reescrito com instrucoes claras de citacao, paginas canonicas, temas, guias e ficheiros estruturados.
- `site/robots.txt` passa a declarar explicitamente crawlers relevantes:
  - `Googlebot`
  - `Bingbot`
  - `OAI-SearchBot`
  - `ChatGPT-User`
  - `GPTBot`
  - `PerplexityBot`
  - `ClaudeBot`
  - `anthropic-ai`
  - `Google-Extended`
- Sete paginas canonicas em `/perguntas/`, desenhadas para respostas AI:
  - AI Act para empresas portuguesas
  - IA numa PME portuguesa
  - empresas de IA em Portugal
  - agentes de IA nas empresas
  - ChatGPT no trabalho sem expor dados
  - impacto da IA no emprego em Portugal
  - ferramentas de IA para empresas
- Quatro paginas de autoridade editorial:
  - `/sobre/`
  - `/autor/joao-ferreira/`
  - `/metodologia-editorial/`
  - `/fontes-e-criterios/`
- Artigos publicos passam a ligar para perguntas canonicas relevantes.
- Novo comando read-only:

```bash
python -m ptia_engine.cli ai-visibility-report
```

## Garantias

- Sem chamadas a Buffer, Git, Vercel ou APIs externas.
- Sem alteracao ao frontend do dashboard.
- Sem alteracao intencional a `data/final_posts.jsonl`.
- Sem alteracao ao engine de comentarios LinkedIn.
- Geracao executada a partir de `site/site-feed.json` para evitar mexer nos ledgers editoriais.
- O gerador continua a ignorar posts futuros/nao publicos para nao antecipar conteudo scheduled.

## Validacao

- `ai-visibility-report`: `100/100`.
- `site/sitemap.xml`, `site/news-sitemap.xml` e `site/rss.xml` parseiam como XML valido.
- `site/ai-index.json` parseia como JSON valido e inclui 7 paginas de resposta.
- Foram geradas 7 paginas em `/perguntas/` e 4 paginas de autoridade editorial.
- 52 de 54 artigos estaticos atuais ligam para paginas canonicas em `/perguntas/`.

# Growth Loop Foundation - 2026-06-03

## Objetivo

Criar a primeira camada invisivel de growth/performance para o PTIA Content Engine sem alterar o fluxo de curadoria, o dashboard visual, os posts ja scheduled ou o motor de comentarios LinkedIn.

## O Que Foi Implementado

- `src/ptia_engine/growth.py`: modulo isolado para UTMs, scoring de growth e relatorio agregado.
- `python -m ptia_engine.cli growth-report`: comando read-only para resumir metricas e recomendacoes.
- Campos opcionais em `ContentPerformance` para dados de site/newsletter:
  - `site_views`
  - `unique_visitors`
  - `newsletter_signups`
  - `utm_source`
  - `utm_medium`
  - `utm_campaign`
  - `utm_content`
  - `page_url`
  - `referrer`
- Scheduler passa a incluir `article_url` com UTM no execution plan de LinkedIn/X para posts futuros.
- Scheduling real de LinkedIn/X passa a montar backlinks para o artigo com UTM quando gerar texto novo para Buffer.

## Garantias

- Nao existe migracao retroativa de `data/final_posts.jsonl`.
- Posts ja scheduled nao sao alterados.
- O dashboard/fluxo de curadoria nao recebeu novos passos, botoes ou campos obrigatorios.
- O motor de comentarios LinkedIn nao foi alterado.
- O comando `growth-report` so le ficheiros por defeito. Apenas escreve se for passado `--out`.

## Comandos

Relatorio em texto:

```powershell
$env:PYTHONPATH="src"; python -m ptia_engine.cli growth-report
```

Relatorio JSON:

```powershell
$env:PYTHONPATH="src"; python -m ptia_engine.cli growth-report --json
```

Guardar relatorio:

```powershell
$env:PYTHONPATH="src"; python -m ptia_engine.cli growth-report --out data/growth_report.md
```

## Estado Atual Dos Dados

`data/content_performance.jsonl` ainda esta sem metricas reais. Por isso o relatorio devolve recomendacoes conservadoras:

- recolher metricas antes de alterar prioridades editoriais;
- usar UTMs em posts futuros;
- importar clicks/views/newsletter signups para o ledger de performance.

## O Que Fica Para A Proxima Fase

- Importador de dados de Search Console/analytics ou export manual normalizado.
- Agregacao de clicks reais por `utm_source`, `utm_campaign` e `utm_content`.
- Ligacao entre subscricoes MailerLite e artigo/campanha de origem, sem guardar PII.
- Google News sitemap e paginas por tema.
- Relatorio semanal com sugestoes de follow-up, evergreen e newsletter.

## Validacao

Validado com:

```text
Ran 120 tests
OK
```

`compileall` em `src` e `tests` sem erros.

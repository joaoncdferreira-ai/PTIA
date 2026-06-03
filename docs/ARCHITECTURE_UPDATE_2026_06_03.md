# Architecture Update - 2026-06-03

Este documento regista o refactor de backend feito em 2026-06-03 para tornar o
PTIA Content Engine mais simples, testavel e seguro, sem alterar o fluxo de
utilizacao do dashboard.

## Estado Depois Do Refactor

Nivel honesto atual: 82/100.

O projeto saiu de um estado muito artesanal para uma base mais madura:

- scheduling diario passou a ter um nucleo central testavel;
- regras editoriais e media deixaram de viver apenas no monolito do dashboard;
- rotas HTTP foram separadas do `DashboardHandler`;
- o dispatch de rotas foi dividido por dominio em `src/ptia_engine/routes/`;
- o fluxo editorial tem repositories e use cases dedicados;
- execucao real de scheduling ficou protegida por confirmacao e flags explicitas;
- cobertura de testes subiu para 113 testes;
- JSONL reais foram validados sem erros.

Ainda nao e 90+ porque alguns route handlers ainda chamam helpers privados do
`dashboard.py`. O proximo nivel e mover essa logica restante para use cases e
services pequenos.

## Garantias De Nao Impacto

Durante este refactor:

- nao foi alterado o HTML/CSS/JS do dashboard;
- nao foi alterado o fluxo visual ou operacional do utilizador;
- nao foram chamados Buffer, Git, Vercel ou APIs externas de publicacao;
- o codigo do refactor nao escreve em `data/final_posts.jsonl`;
- o codigo do refactor nao escreve em `data/linkedin_comments.jsonl`;
- nao foi trabalhado o engine de comentarios LinkedIn.

Nota operacional: `data/linkedin_comments.jsonl` e um ficheiro vivo se houver
automacoes LinkedIn em background. Para refactors futuros, comparar hash
imediatamente antes/depois da validacao ou pausar essas automacoes.

Hashes confirmados durante as validacoes noop do scheduler:

- `data/final_posts.jsonl`: sem alteracao durante as simulacoes noop;
- `data/linkedin_comments.jsonl`: sem alteracao durante as simulacoes noop quando medido em janela atomica.

## Novos Modulos

### `src/ptia_engine/scheduler.py`

Motor central para planeamento de agendamento.

Responsabilidades:

- ler posts finais agendaveis;
- validar pacotes por dia;
- detetar canais em falta;
- tratar posts ja agendados como `skipped`;
- criar execution plans sem efeitos externos;
- agrupar Instagram como carrossel unico quando aplicavel;
- bloquear estados mistos, por exemplo Instagram parcialmente scheduled.

Funcoes principais:

- `build_schedule_day_plan(...)`
- `build_schedule_execution_plan(...)`
- `execute_schedule_plan(...)`
- `format_schedule_plan(...)`
- `format_execution_plan(...)`

### `src/ptia_engine/dashboard_routes.py`

Substituido pela estrutura `src/ptia_engine/routes/`.

O `DashboardHandler` em `dashboard.py` ficou responsavel apenas por:

- ler JSON;
- enviar JSON/HTML/ficheiros;
- delegar `do_GET` e `do_POST` para `ptia_engine.routes`.

Isto nao muda URLs, payloads ou respostas esperadas.

### `src/ptia_engine/routes/`

Contem o dispatch HTTP por dominio:

- `static.py`: GETs, assets locais e site preview;
- `editorial.py`: item status, draft status e performance;
- `signals.py`: sinais, quick capture, scouts e reverificacao;
- `topics.py`: topicos e aprovacao de pacote;
- `posts.py`: final posts, build pack, rewrite e polish;
- `media.py`: imagem final, upload, prompts e titulos visuais;
- `scheduling.py`: Buffer discover e scheduling via dashboard;
- `newsletter.py`: gerar e atualizar estado da newsletter;
- `common.py`: helpers partilhados de resposta/serializacao.

### `src/ptia_engine/services/`

Pacote de servicos pequenos e testaveis:

- `channels.py`: configuracao de canais, canais desativados e IDs Buffer;
- `editorial_hygiene.py`: hashtags, regras editoriais e validacao de copy;
- `gemini.py`: polish editorial com provider injetado e fallback seguro;
- `media.py`: paths e URLs publicos de imagens;
- `site.py`: slugs, URLs de artigos, excertos e visibilidade de artigos;
- `social_text.py`: fitting e validacao de copy para X;
- `schedule_backend.py`: adapter real de scheduling protegido por capacidades.

## CLI Novo

Comando seguro de preflight:

```powershell
$env:PYTHONPATH="src"; python -m ptia_engine.cli schedule-day --date 2026-06-03
```

Ver plano de execucao sem efeitos externos:

```powershell
$env:PYTHONPATH="src"; python -m ptia_engine.cli schedule-day --date 2026-06-03 --execution-plan
```

Simular execucao sem Buffer/Git/Vercel:

```powershell
$env:PYTHONPATH="src"; python -m ptia_engine.cli schedule-day --date 2026-06-03 --execution-plan --simulate-execute --confirm 2026-06-03
```

Execucao real existe mas esta bloqueada por desenho:

```powershell
$env:PYTHONPATH="src"; python -m ptia_engine.cli schedule-day --date 2026-06-03 --execute-real --confirm 2026-06-03 --publish-assets --send-buffer --write-site-feed
```

Nao usar `--execute-real` sem uma revisao humana do plano.

## Safety Gates

`--execute-real` exige:

- `--confirm YYYY-MM-DD`;
- `--publish-assets` se houver preparacao/publicacao de assets;
- `--send-buffer` se houver criacao de posts Buffer;
- `--write-site-feed` se houver escrita/sync de feed do site.

Sem estas flags, o comando falha antes de chamar qualquer backend real.

## Testes Adicionados

Novos testes cobrem:

- plano diario de scheduling;
- agendamento idempotente de posts ja scheduled;
- carrossel Instagram unico;
- bloqueio de Instagram parcialmente scheduled;
- simulacao noop;
- capability gates do adapter real;
- CLI `schedule-day`;
- separacao de rotas do dashboard;
- servicos de media, canais, site, Gemini, copy editorial e X.

Validacao final:

```text
Ran 113 tests in 7.211s
OK
```

Validacao JSONL:

```text
bad_count = 0
```

## Estado Dos Dias Agendados

Dry-run de 2026-06-03:

- status READY;
- 13 actions;
- todas as actions eram `skipped` porque os posts ja estavam scheduled;
- Instagram aparece como `skip_instagram_carousel_already_scheduled`.

Dry-run de 2026-06-04:

- status READY;
- 0 actions;
- aviso: `no schedulable posts found for date`.

## O Que Falta Para 90+

Para subir de 82/100 para cerca de 90/100:

- reduzir imports residuais de helpers privados do `dashboard.py` dentro dos route handlers;
- tirar mais logica editorial de `routes/posts.py` para use cases pequenos;
- cobrir endpoints de newsletter/performance com testes diretos;
- documentar ownership dos dados JSONL.

Para 95+:

- CI automatico;
- lint/format/type checking obrigatorio;
- limpeza do worktree e dos scripts orfaos;
- matriz clara de comandos seguros vs comandos com efeitos externos;
- reduzir dependencias implicitas entre dashboard, scheduler e scripts.

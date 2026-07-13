# PTIA Knowledge Index v2

## Objetivo

O PTIA Knowledge Index sustenta quatro recursos editoriais:

- pessoas e empresas com impacto público na IA em Portugal;
- ferramentas comparadas por caso de uso;
- biblioteca de prompts selecionados pela PTIA;
- glossário português de Inteligência Artificial.

O Hub em /recursos/ apresenta o que merece atenção, o grau de confiança e as alterações de estado. Não publica uma pontuação absoluta nem transforma cobertura mediática em prova de liderança.

## Princípio central

O estado vem antes da pontuação.

Uma entidade marcada como “acquired”, “insolvent”, “liquidated” ou “inactive” sai imediatamente do índice ativo e passa para “entity_archive”, com motivo, data de verificação e fontes. A alteração não é tratada como uma descida gradual.

A elegibilidade tem quatro estados:

- “eligible”: entidade ativa, verificada nos últimos 45 dias e sustentada por pelo menos duas fontes HTTPS independentes;
- “provisional”: entidade histórica ainda sem verificação recente suficiente;
- “watchlist”: entrada suspensa para revisão;
- “ineligible”: entidade fora do índice ativo.

Durante a migração inicial, entradas históricas sem duas fontes são publicadas como provisórias. A sua ordem editorial anterior é preservada; sinais noticiosos não podem empurrar uma entrada provisória para o topo. Só entidades plenamente elegíveis competem pela avaliação multidimensional.

## Metodologia

### Empresas

A avaliação de entidades elegíveis pondera:

- impacto demonstrável: 30%;
- momentum dos últimos 84 dias: 25%;
- inovação: 20%;
- relevância para Portugal: 15%;
- contribuição para o ecossistema: 10%.

### Pessoas

A avaliação de entidades elegíveis pondera:

- trabalho publicado ou executado: 35%;
- reconhecimento independente: 25%;
- contribuição para o ecossistema: 20%;
- atualidade: 10%;
- ligação a Portugal: 10%.

A interface publica faixas, confiança, explicação e fontes. O valor decimal permanece nos dados estruturados para ordenação e auditoria, mas não é apresentado como uma medição científica.

### Ferramentas

Cada finalidade tem uma comparação independente com quatro componentes:

- capacidade;
- adoção observável;
- adequação à tarefa;
- acesso e valor.

Cada componente tem fonte e peso próprios em “tool_category_evidence”. A página mostra a confiança da evidência como “alta”, “média” ou “editorial”. O resumo global é a média das categorias em que a ferramenta participa, não o seu melhor resultado isolado e não um “vencedor universal”.

### Prompts

Os prompts são curadoria editorial, ordenada por clareza, reutilização e utilidade do template. Menções nos artigos PTIA servem apenas de contexto e não alteram a pontuação.

Enquanto não existirem dados reais de utilização, a página declara “utilização ainda não medida” e não apresenta a biblioteca como tendência semanal ou ranking de popularidade.

### Glossário

As definições são versionadas. A automação pode alterar a ordem de destaque segundo as menções PTIA, mas não reescreve silenciosamente conceitos técnicos.

## Automação de estado

A pesquisa semanal procura primeiro insolvência, liquidação, encerramento, aquisição e inatividade. Uma proposta “entity_status_update” só pode ser aplicada automaticamente quando:

- a confiança é pelo menos 92%;
- existem duas fontes HTTPS independentes e grounded;
- pelo menos uma fonte pertence à lista de referência;
- o motivo e a data de verificação são válidos;
- o catálogo completo continua válido após a alteração.

Novas entidades continuam a exigir revisão editorial.

## LinkedIn

A série de Recursos gera uma peça semanal para revisão: um carrossel nativo “Radar PTIA — o que mudou e porquê”.

A estrutura recomendada é:

1. mudança verificável como gancho;
2. explicação do gate de estado;
3. empresa em destaque;
4. pessoa em destaque;
5. ferramentas por finalidade;
6. entidade retirada do índice ativo, quando exista;
7. fontes, metodologia e pergunta aberta.

O rascunho inclui os URLs externos usados pelo engine. Não é publicado nem enviado para o Buffer sem revisão.

## Comando

    $env:PYTHONPATH="src"
    python -m ptia_engine.cli knowledge-update --json

O comando lê:

- config/ptia_knowledge.json;
- site/assets/quem-e-quem.json;
- site/site-feed.json;
- a edição anterior em site/assets/ptia-index/latest.json, quando existe.

## Saídas

- site/recursos/index.html
- site/ia-em-portugal/index.html
- site/ferramentas/index.html
- site/prompts/index.html
- site/glossario/index.html
- site/metodologia-indice/index.html
- site/assets/ptia-index/latest.json
- site/assets/ptia-index/archive/YYYY-Www.json

As páginas são pré-renderizadas e funcionam sem JavaScript. Os dados usam “schema_version: 2” e cada edição fica arquivada.

## Segurança e limites

- A geração valida IDs, estados, elegibilidade, categorias, URLs e conteúdo antes de escrever.
- As escritas são atómicas; uma edição inválida não substitui a última versão pública.
- Artigos futuros não contam como sinais.
- Popularidade e frequência de cobertura não são provas isoladas de qualidade ou impacto.
- Uma fonte isolada nunca concede elegibilidade plena.
- Correções devem indicar o registo, a afirmação contestada e uma fonte verificável.
- O índice é uma avaliação editorial auditável, não uma medição absoluta de influência.

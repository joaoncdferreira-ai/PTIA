# Roadmap de Implementacao PTIA

Restricao inicial: nao ultrapassar 30 EUR/mes enquanto o projecto nao gerar receita.

## V0 - Motor editorial local

Objetivo: provar a rotina diaria sem dependencias pagas.

Entregaveis:

- estrutura do projecto
- schema editorial
- fontes RSS iniciais
- ingestao RSS
- deduplicacao basica
- briefing local simples
- prompts editoriais

Pronto quando:

- 10 fontes geram artigos em `Raw Articles`
- duplicados obvios sao marcados
- o briefing diario mostra uma lista curta para revisao

## V1 - Base editorial Airtable

Objetivo: transformar os dados locais numa fila editorial facil de rever.

Entregaveis:

- base `PTIA Editorial Engine`
- tabelas principais
- views de revisao
- import/export local para Airtable

Pronto quando:

- um artigo entra em `Raw Articles`
- um item chega a `Content Drafts`
- o Joao consegue aprovar/rejeitar em menos de 30 minutos por dia

## V2 - Classificacao AI

Objetivo: reduzir ruido sem gastar demasiado em tokens.

Entregaveis:

- classificacao JSON estruturada
- scores editoriais
- budget guard mensal
- logs de custo estimado

Pronto quando:

- 30-50 artigos brutos viram 5-10 candidatos uteis
- o custo diario fica previsivel
- falsos positivos e falsos negativos sao revistos semanalmente

## V3 - Draft generation

Objetivo: gerar conteudo editavel em portugues europeu.

Entregaveis:

- resumo PT-PT
- porque importa
- angulo Portugal
- LinkedIn post
- Instagram caption
- estrutura de carrossel
- entrada curta para site/newsletter

Pronto quando:

- os drafts precisam apenas de edicao humana leve
- nenhuma peca copia ou traduz artigos completos
- todas incluem fonte original

## V4 - Publicacao semi-automatica

Objetivo: publicar com controlo humano.

Entregaveis:

- export para Buffer/manual scheduling
- campos `approved_for_schedule`, `scheduled`, `published`
- `published_url`

Pronto quando:

- posts aprovados sao agendados sem confusao
- nada publica sem aprovacao explicita

## V5 - Newsletter semanal

Objetivo: transformar o arquivo semanal num produto recorrente.

Entregaveis:

- top 5 noticias
- destaque Portugal
- destaque builders
- destaque regulacao
- sinal vs ruido

Pronto quando:

- a newsletter fica pronta para revisao em menos de 45 minutos

## V6 - Automatizacoes pagas apenas com receita

So considerar quando houver receita ou tracao clara:

- Buffer pago
- Ghost pago
- n8n Cloud
- Canva Pro
- analytics automaticos
- carrosseis gerados automaticamente

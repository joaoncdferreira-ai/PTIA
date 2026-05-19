# Schema Editorial

Base: `PTIA Editorial Engine`

## Sources

Fontes acompanhadas pelo motor editorial.

| Campo | Tipo | Notas |
|---|---|---|
| source_id | texto | slug unico |
| name | texto | nome publico da fonte |
| url | url | pagina principal |
| rss_url | url | feed RSS/Atom |
| type | single select | official_company_blog, news_media, research, regulation, newsletter, developer_source, portugal_source |
| category | single select | world_ai, portugal_ai, builders, business, regulation, tools, research |
| language | single select | en, pt, multi |
| country | texto | US, UK, EU, PT, etc. |
| trust_score | numero | 1-10 |
| active | checkbox | fonte ativa |
| usage_policy | texto longo | notas de copyright/licenca |
| paywalled | checkbox | conteudo pago |
| notes | texto longo | observacoes editoriais |

## Raw Articles

Artigos encontrados antes de curadoria.

| Campo | Tipo | Notas |
|---|---|---|
| article_id | texto | hash estavel |
| source_id | link Sources | origem |
| title_original | texto | titulo original |
| url | url | URL final/canonica se disponivel |
| author | texto | opcional |
| published_at | data/hora | data da fonte |
| fetched_at | data/hora | data da ingestao |
| language | single select | en, pt, multi, unknown |
| country | texto | herdado da fonte se aplicavel |
| raw_excerpt | texto longo | excerto curto, nao artigo completo |
| image_url | url | opcional |
| status | single select | new, processed, duplicate, rejected, error |
| duplicate_of | link Raw Articles | artigo original |
| content_hash | texto | dedupe auxiliar |

## Story Clusters

Agrupa varios artigos sobre a mesma historia.

| Campo | Tipo | Notas |
|---|---|---|
| story_id | texto | id unico |
| canonical_title | texto | titulo editorial interno |
| primary_article | link Raw Articles | fonte principal |
| related_articles | link Raw Articles | fontes secundarias |
| section | single select | world_ai, portugal_ai, builders, business, regulation, tools, research |
| status | single select | new, candidate, rejected, processed |
| notes | texto longo | contexto editorial |

## Processed Items

Itens candidatos depois de classificacao.

| Campo | Tipo | Notas |
|---|---|---|
| item_id | texto | id unico |
| story_id | link Story Clusters | historia |
| article_id | link Raw Articles | compatibilidade V0 |
| section | single select | categorias editoriais |
| relevance_score | numero | 1-10 |
| hype_score | numero | 1-10 |
| portugal_relevance_score | numero | 1-10 |
| builder_relevance_score | numero | 1-10 |
| business_relevance_score | numero | 1-10 |
| summary_pt | texto longo | resumo proprio |
| why_it_matters_pt | texto longo | impacto |
| portugal_angle_pt | texto longo | angulo portugues |
| key_takeaways | texto longo | bullets |
| source_url | url | fonte original |
| ai_confidence | numero | 1-10 |
| editorial_status | single select | needs_review, needs_source_check, approved_for_draft, draft_ready, approved_for_schedule, scheduled, published, rejected |
| risk_notes | texto longo | riscos e duvidas |
| editor_notes | texto longo | notas humanas |

## Content Drafts

Drafts por canal.

| Campo | Tipo | Notas |
|---|---|---|
| draft_id | texto | id unico |
| item_id | link Processed Items | item base |
| channel | single select | linkedin, instagram, site, newsletter |
| format | single select | linkedin_post, instagram_caption, instagram_carousel, site_short_article, newsletter_item |
| title | texto | titulo |
| body | texto longo | corpo |
| caption | texto longo | legenda |
| hashtags | texto | 3-5 hashtags |
| cta | texto | chamada para acao |
| image_prompt | texto longo | opcional |
| carousel_outline | texto longo | 5-7 slides |
| scheduled_time | data/hora | data de agendamento |
| status | single select | draft, needs_edit, approved, scheduled, published, rejected |
| buffer_post_id | texto | quando existir |
| published_url | url | link publico |

## Daily Briefing

Resumo operacional diario.

| Campo | Tipo | Notas |
|---|---|---|
| date | data | dia |
| top_world_ai | link Processed Items | top mundo |
| top_portugal_ai | link Processed Items | top Portugal |
| top_builders | link Processed Items | top builders |
| top_business | link Processed Items | top empresas |
| top_regulation | link Processed Items | top regulacao |
| recommended_posts | texto longo | agenda sugerida |
| editorial_notes | texto longo | notas humanas |
| status | single select | generated, reviewed, actioned |

## Content Performance

Metricas semanais manuais na V0.

| Campo | Tipo | Notas |
|---|---|---|
| post_id | texto | id interno ou Buffer |
| draft_id | link Content Drafts | draft publicado |
| channel | single select | linkedin, instagram, site, newsletter |
| published_at | data/hora | data publicada |
| topic | texto | tema |
| section | single select | categoria |
| impressions | numero | manual |
| likes | numero | manual |
| comments | numero | manual |
| shares | numero | manual |
| saves | numero | manual |
| clicks | numero | manual |
| followers_gained | numero | manual |
| notes | texto longo | aprendizagens |

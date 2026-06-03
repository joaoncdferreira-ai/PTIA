# SEO Discovery Layer - 2026-06-03

## Objetivo

Melhorar a descoberta organica do PTIA.pt sem alterar o dashboard de curadoria, os posts ja scheduled ou o motor de comentarios LinkedIn.

## O Que Foi Implementado

- `site/news-sitemap.xml` com namespace Google News.
- `site/robots.txt` agora anuncia:
  - `https://ptia.pt/sitemap.xml`
  - `https://ptia.pt/news-sitemap.xml`
- `site/sitemap.xml` inclui paginas tematicas indexaveis.
- `site/llms.txt` inclui o News sitemap e as paginas de temas.
- Gerador do site estatico em `src/ptia_engine/dashboard.py` passou a escrever estes artefactos sempre que o feed estatico for sincronizado.
- Artigos publicos passam a incluir links internos contextuais para temas e guias PTIA existentes, com JSON-LD `about`.
- O gerador de artigos estaticos ignora posts nao publicos/futuros, evitando materializar conteudo ja curado mas ainda nao publicado.

## Paginas Tematicas Geradas

- `https://ptia.pt/temas/ia-em-portugal/`
- `https://ptia.pt/temas/ia-para-pme/`
- `https://ptia.pt/temas/ai-act/`
- `https://ptia.pt/temas/agentes-de-ia/`
- `https://ptia.pt/temas/trabalho-e-produtividade/`

Estas paginas agregam artigos existentes por tema, criando uma camada de autoridade semantica acima do feed diario.

## Google News Sitemap

O News sitemap inclui apenas artigos publicos recentes, com:

- `news:publication`
- `news:publication_date`
- `news:title`
- `loc`

O limite temporal segue a regra operacional de noticias recentes: apenas posts publicos dos ultimos 2 dias entram no ficheiro.

## Garantias

- Sem chamadas a Buffer, Git, Vercel ou APIs externas.
- Sem alteracao ao frontend do dashboard.
- Sem alteracao intencional a `data/final_posts.jsonl`.
- Sem alteracao ao engine de comentarios LinkedIn.
- Geracao executada a partir de `site/site-feed.json` para evitar mexer nos ledgers editoriais.
- Links internos apontam apenas para paginas tematicas e guias ja presentes no site.
- Posts futuros/scheduled nao sao escritos como paginas estaticas antes de ficarem publicos no feed.

## Validacao

- `site/sitemap.xml`, `site/news-sitemap.xml` e `site/rss.xml` parseiam como XML valido.
- Teste automatizado cobre geracao de News sitemap, robots e paginas de tema.
- Suite completa validada com `Ran 120 tests`, `OK`.

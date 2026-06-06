# Traffic Analytics – PTIA.pt

**Data de ativação:** 2026-06-05  
**Responsável:** joaoncdferreira-ai  
**Estado:** Ativo (snippet injetado, dados a acumular)

---

## O que foi ativado

Foi implementada a camada mínima de analytics para o site estático `ptia.pt` usando **Plausible Analytics** (privacy-friendly, sem cookies, GDPR-compliant por design).

### Ficheiros alterados/criados

| Ficheiro | Tipo | O que faz |
|---|---|---|
| `src/ptia_engine/traffic.py` | **Novo** | Módulo Python com lógica de analytics: geração do snippet, injeção idempotente em HTMLs, listagem de páginas rastreáveis, relatório read-only |
| `tests/test_traffic_analytics.py` | **Novo** | 4 testes: homepage, artigos estáticos, integridade editorial, provider=none |
| `docs/TRAFFIC_ANALYTICS_2026_06_05.md` | **Novo** | Este ficheiro de documentação |
| `site/index.html` | **Editado** | Snippet Plausible injetado antes de `</head>` |
| `src/ptia_engine/cli.py` | **Editado** | Comando `traffic-report` adicionado (read-only stub) |

### Snippet injetado

```html
<!-- ptia-analytics -->
<script defer data-domain="ptia.pt" src="https://plausible.io/js/script.tagged-events.js"></script>
<!-- /ptia-analytics -->
```

O snippet usa o marcador `<!-- ptia-analytics -->` para ser detetável e idempotente (não é inserido duas vezes).

### Configuração via ambiente

Variáveis de ambiente (`.env` local, sem commit):

```bash
PTIA_ANALYTICS_PROVIDER=plausible  # default
PTIA_ANALYTICS_DOMAIN=ptia.pt       # default
```

Para desativar: `PTIA_ANALYTICS_PROVIDER=none`

---

## Onde ver os dados

1. **Dashboard Plausible:** https://plausible.io/ptia.pt  
   (requer conta Plausible com o domínio `ptia.pt` configurado)

2. **Dados que serão recolhidos automaticamente:**
   - Visitas totais e visitantes únicos
   - Páginas mais visitadas (artigos, homepage, guias, temas, perguntas)
   - Origem do tráfego (referrer: LinkedIn, X/Twitter, Google, direto)
   - UTMs de links sociais já gerados pelo engine (utm_source, utm_medium, utm_campaign)
   - Cliques em eventos (se usar `script.tagged-events.js`)

3. **CLI read-only:**
   ```bash
   python -m ptia_engine.cli traffic-report --site-dir site
   ```
   Valida se o snippet está instalado e lista páginas rastreáveis.

---

## Limitações atuais

1. **Dados históricos:** O Plausible só recolhe dados a partir do momento em que o snippet está ativo no site publicado (ptia.pt). Não há dados retroativos.

2. **Artigos estáticos gerados:** O snippet foi injetado na `site/index.html`. Para artigos futuros gerados pelo engine Python, o gerador deve chamar `inject_snippet_into_file()` de `traffic.py` após criar cada `site/artigos/*/index.html`.

3. **Dashboard de analytics separado:** O Plausible tem o seu próprio dashboard em plausible.io. Não está integrado no dashboard editorial PTIA por agora.

4. **Sem dados no `content_performance.jsonl` ainda:** A pipeline de importação (Plausible API → `content_performance.jsonl`) ainda não está implementada (ver próximos passos).

5. **Vercel Analytics:** Não foi ativado porque requer configuração no projeto Vercel. O Plausible funciona com qualquer host estático via CDN externo.

---

## Próximos passos – Importar métricas para content_performance.jsonl

Para fechar o loop editorial (escrever → publicar → medir → aprender):

### Passo 1: Configurar conta Plausible
- Criar conta em https://plausible.io
- Adicionar domínio `ptia.pt`
- Verificar que o snippet está a receber dados (após deploy)

### Passo 2: Ativar Plausible API
- Gerar API token em https://plausible.io/settings (Settings → API keys)
- Adicionar ao `.env`: `PLAUSIBLE_API_KEY=<token>`

### Passo 3: Criar `src/ptia_engine/performance_import.py` (já existe parcialmente)
Expandir com importação do Plausible:
```python
# Endpoint: https://plausible.io/api/v1/stats/breakdown
# Params: site_id=ptia.pt, period=30d, property=event:page, metrics=visitors,pageviews
# Mapear page → artigo → content_performance.jsonl
```

### Passo 4: Adicionar ao CLI
```bash
python -m ptia_engine.cli traffic-import
```

### Passo 5: Integrar com growth-report
O `growth-report` já lê `content_performance.jsonl`. Com dados reais do Plausible importados, o relatório passa a mostrar métricas de tráfego reais.

---

## Reversibilidade

Para remover o analytics:
1. Remover as linhas entre `<!-- ptia-analytics -->` e `<!-- /ptia-analytics -->` nos HTMLs.
2. Definir `PTIA_ANALYTICS_PROVIDER=none` no `.env`.
3. O módulo `traffic.py` pode ser mantido sem efeito.

---

## O que NÃO foi tocado

- `data/final_posts.jsonl` — intacto
- `data/linkedin_comments.jsonl` — intacto
- `data/content_performance.jsonl` — intacto (vazio)
- Motor de comentários LinkedIn — intacto
- Posts scheduled no Buffer — intacto
- Dashboard editorial — intacto
- Fluxo de curadoria — intacto

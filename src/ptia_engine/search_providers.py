from __future__ import annotations

import json
import os
import re
import urllib.request
from urllib.error import HTTPError, URLError
from dataclasses import dataclass
from datetime import date
from typing import Any

from ptia_engine.http_client import urlopen_direct


@dataclass(slots=True)
class SearchCandidate:
    title: str
    url: str
    source_name: str = ""
    published_at: str = ""
    summary: str = ""
    why_it_matters: str = ""
    confidence: float = 0.0
    trend_score: int = 0
    trend_evidence: str = ""
    query: str = ""


@dataclass(slots=True)
class RewriteResult:
    title: str
    body: str
    hashtags: str = ""
    rationale: str = ""


def _extract_json(text: str) -> Any:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    starts = [idx for idx in (cleaned.find("["), cleaned.find("{")) if idx >= 0]
    if starts:
        cleaned = cleaned[min(starts) :]
    return json.loads(cleaned)


def _candidate_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("candidates", "results", "news", "items", "topics"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _candidate_from_record(record: dict[str, Any], query: str = "") -> SearchCandidate:
    url = str(
        record.get("source_url")
        or record.get("url")
        or record.get("link")
        or record.get("uri")
        or ""
    )
    source_name = str(record.get("source_name") or record.get("source") or "")
    return SearchCandidate(
        title=str(record.get("title") or record.get("topic") or record.get("claim") or url),
        url=url,
        source_name=source_name,
        published_at=str(record.get("published_at") or record.get("date") or ""),
        summary=str(record.get("summary") or record.get("claim") or ""),
        why_it_matters=str(record.get("why_it_matters") or record.get("why") or ""),
        confidence=float(record.get("confidence") or 0.0),
        trend_score=max(
            0,
            min(100, int(float(record.get("trend_score") or record.get("momentum_score") or 0))),
        ),
        trend_evidence=str(record.get("trend_evidence") or record.get("momentum_evidence") or ""),
        query=query,
    )


def _rewrite_from_record(record: dict[str, Any]) -> RewriteResult:
    return RewriteResult(
        title=str(record.get("title") or ""),
        body=str(record.get("body") or record.get("text") or ""),
        hashtags=str(record.get("hashtags") or ""),
        rationale=str(record.get("rationale") or record.get("reason") or ""),
    )


def _image_title_suggestions_from_record(payload: Any) -> list[dict[str, str]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("suggestions"), list):
        return []

    suggestions: list[dict[str, str]] = []
    for row in payload["suggestions"]:
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or "").strip()
        if not title:
            continue
        suggestions.append(
            {
                "tone": str(row.get("tone") or "editorial").strip() or "editorial",
                "title": title,
            }
        )
    return suggestions[:2]


PTIA_COPY_STYLE_REFERENCES = """
Exemplos PTIA de tom e decisao editorial. Usa-os como referencia de ritmo e criterio,
nunca como factos para copiar.

<example channel="linkedin">
Facto primeiro:
"A empresa abriu o acesso ao novo modelo a equipas que ja usam a sua cloud."
Leitura PTIA:
"A noticia nao e apenas mais um modelo no mercado. Se a empresa esta a distribuir a
capacidade dentro do produto que ja domina, a vantagem passa a estar no ponto de
entrada: quem controla o habito diario controla tambem a adopcao da IA."
</example>

<example channel="instagram">
"Tres leituras para guardar:
- o anuncio muda a distribuicao, nao apenas a tecnologia;
- a vantagem esta no produto onde o utilizador ja trabalha;
- o concorrente que parece melhor pode chegar tarde se nao tiver o canal.

Fonte: entidade original"
</example>

<example channel="site">
"O detalhe importante esta na forma como a capacidade chega ao mercado. Quando a IA
deixa de ser uma ferramenta separada e passa a aparecer no software que a equipa ja
usa, a pergunta comercial muda: nao e quem tem o melhor modelo, e quem consegue
tornar o modelo inevitavel sem pedir uma nova rotina."
</example>
""".strip()


PTIA_HUMAN_EDITORIAL_ARTICLE_PROMPT = """
Role & Editorial Authority:
You are a Senior Tech Journalist and Editorial Writer for a prestigious Portuguese media brand focusing on Artificial Intelligence.
Write exclusively in flawless European Portuguese, following the Acordo Ortografico de 1990.

Core Directive: Absolute Humanization.
Actively remove linguistic and structural markers typical of AI-generated content. The text must have human burstiness: varied rhythm, nuanced vocabulary, and analytical structure.

Style:
- Cultured, analytical, sophisticated, but accessible to a tech-forward audience.
- Prefer European Portuguese phrasing: "esta a fazer", "ecra", "utilizador", "equipa", "decisor".
- NAO traduzas jargoes tecnologicos comuns na industria: mantem termos como "cloud" (nunca "nuvem"), "legacy" ou "legacy systems" (nunca "sistemas legados"), "compliance" (nunca "conformidade"), "hype", "pipeline", "framework", "use case", "insights", "prompt" e "roadmap" na sua forma original em ingles, escrevendo-os sempre em italico HTML (ex: <i>framework</i>, <i>compliance</i>, <i>pipeline</i>).
- Alternate short, sharp sentences with longer analytical clauses.
- Show, do not tell. Present the data, tension or paradox; do not announce that something is "fascinating" or "revolutionary".

Strict AI Cliche Filter:
- Forbidden: "Em suma", "Em resumo", "No panorama atual", "O impacto de [X] nao pode ser subestimado", "E fundamental recordar", "Desbloquear o potencial", "Revolucionar", "Mergulhar profundamente", "A verdade e que", "Crucial", "Vital", "Essencial".
- Never start a paragraph with "Alem disso", "Por outro lado", "Adicionalmente" or "Consequentemente".
- Do not end with a neat moral summary. End with a concrete paradox, a near-future tension, a sharp closing sentence or a question that would bother a decision-maker.

Article workflow:
1. Title: subtle, compelling, professional. No clickbait formulas.
2. Lead: start in media res, with a scene, overlooked data, structural tension or contradiction.
3. Core: analysis without predictable listicle scaffolding. Weave technical concepts into business, political, social or philosophical reality.
4. Close: leave the reader thinking. No summary paragraph.
""".strip()


PTIA_SPECIFIC_ANGLE_PROMPT = """
Disciplina de angulo especifico:
- Antes de escrever, identifica silenciosamente: facto novo, actor principal, incentivo, conflito e consequencia concreta.
- Formula uma tese editorial numa frase. Essa tese tem de nascer dos detalhes desta noticia, nao de uma opiniao geral sobre IA.
- Se a tese pudesse servir para dez outras noticias de IA, rejeita-a e escolhe outra.
- Nao uses por defeito os angulos "execucao", "Portugal", "custo/risco/dependencia", "quem consegue executar", "primeiro passo" ou "vantagem competitiva" se a noticia nao os justificar.
- Evita perguntas gerais. Prefere opiniao declarativa, verificavel e ligada ao facto.
- Uma boa leitura PTIA deve parecer uma posicao editorial: discutivel, concreta e sustentada pela fonte.
""".strip()


PTIA_ANTI_ASSISTANT_PASS = """
Passagem anti-assistente antes de devolver:
- Escolhe a frase mais generica e corta-a ou torna-a concreta.
- Nao organizes tudo com a mesma cadencia; deixa uma frase curta quando ela carrega a tese.
- Evita construcoes repetidas como "nao e X, e Y" se nao houver tensao editorial real.
- Remove headings performativos, excesso de negrito, listas decorativas e fechos de assistente.
- Se a leitura editorial nao muda uma decisao, reduz a leitura e mantem o facto.
- Para artigos de site, usa o workflow de artigo humano: titulo discreto, lead em tensao, analise com ritmo variavel e fecho sem moral arrumada.
- Elimina perguntas genericas de fecho. Se fechares com pergunta, ela tem de nascer de um detalhe factual da noticia.
""".strip()


class GeminiGroundedSearchProvider:
    """Small REST client for Gemini Grounding with Google Search.

    It intentionally returns candidates only. PTIA still validates domains and dates
    locally before anything reaches Verified Selection.
    """

    partitioned_research = True

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: int = 30,
    ) -> None:
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.model = model or os.getenv("GEMINI_SEARCH_MODEL", "gemini-2.5-flash")
        self.timeout_seconds = timeout_seconds

    @property
    def available(self) -> bool:
        return bool(self.api_key.strip())

    def search_for_link(
        self,
        *,
        submitted_url: str,
        page_title: str = "",
        page_summary: str = "",
        thought: str = "",
        limit: int = 5,
    ) -> list[SearchCandidate]:
        prompt = f"""
És o radar de fontes do PTIA. O utilizador colou um link, mas esse link pode ser
social, secundário ou pouco credível. Pesquisa a notícia por trás do link e encontra
fontes credíveis/primárias publicadas nos últimos 5 dias.

Link submetido: {submitted_url}
Título detectado: {page_title or "desconhecido"}
Resumo detectado: {page_summary or "desconhecido"}
Notas do utilizador: {thought or "nenhuma"}
Data de hoje: {date.today().isoformat()}

Responde apenas em JSON válido, sem markdown, com no máximo {limit} candidatos:
{{
  "candidates": [
    {{
      "title": "título da notícia",
      "source_url": "https://...",
      "source_name": "nome da fonte",
      "published_at": "YYYY-MM-DD",
      "summary": "1 frase factual",
      "why_it_matters": "1 frase sobre relevância para PTIA",
      "confidence": 0.0
    }}
  ]
}}

Regras:
- Preferir fonte primária, Reuters/AP/Bloomberg/FT, media tecnológico credível,
  regulador, universidade ou empresa original.
- Se o link submetido for The Rundown AI/rundown.ai/therundown.ai, usa-o apenas como
  pista editorial: devolve as fontes originais citadas no artigo, nÃ£o o prÃ³prio Rundown.
- Não inventar datas nem URLs.
- Se não encontrares fonte credível, devolve candidates vazio.
""".strip()
        return self._generate_candidates(prompt, query=f"source-for-link:{submitted_url}", limit=limit)

    def scout_today_ai_news(self, *, limit: int = 8) -> list[SearchCandidate]:
        prompt = f"""
Age como editor de breaking news de Inteligência Artificial para a PTIA. Pesquisa na
web as notícias de IA com maior momentum real publicadas hoje. Só admite uma notícia
do dia anterior quando continuar a ganhar cobertura ou impacto material hoje.
Não quero uma lista genérica das notícias mais recentes: quero acontecimentos que
estejam a ganhar cobertura, discussão ou impacto material agora.

Data de hoje: {date.today().isoformat()}.

Responde apenas em JSON válido, sem markdown, com no máximo {limit} candidatos,
ordenados do maior para o menor momentum:
{{
  "candidates": [
    {{
      "title": "título factual do acontecimento",
      "source_url": "URL exato do artigo individual ou anúncio original",
      "source_name": "nome da fonte original ou media credível",
      "published_at": "YYYY-MM-DD",
      "summary": "2 frases factuais com ator, ação e dado concreto",
      "why_it_matters": "consequência específica para empresas, profissionais, builders, regulação ou Portugal",
      "trend_score": 0,
      "trend_evidence": "sinal concreto de momentum: cobertura independente, anúncio material, discussão pública ou adoção",
      "confidence": 0.0
    }}
  ]
}}

Regras de seleção:
- Momentum não é clickbait. Pontua alto quando existe cobertura por pelo menos duas
  fontes independentes, anúncio oficial material, forte discussão pública verificável,
  adoção relevante, benchmark credível, investimento, regulação ou impacto operacional.
- Privilegia notícias que mudem uma decisão ou expliquem uma mudança real. Penaliza
  opinião genérica, previsões vagas, listas, tutoriais, páginas evergreen e press releases
  sem consequência material.
- Devolve sempre o URL de um artigo individual ou da fonte primária. Nunca devolvas
  homepage, página de categoria, tag, pesquisa, arquivo ou página "últimas notícias".
- Não repitas o mesmo acontecimento através de URLs ou fontes diferentes.
- Prioriza publicações com a data de hoje. Uma publicação do dia anterior só pode
  entrar se trend_evidence explicar concretamente por que continua trending hoje.
- Inclui Portugal quando existir uma notícia portuguesa forte; não inventes nem forces
  um ângulo português numa notícia global.
- Não incluir rumores sem confirmação, nem inventar datas, scores, evidência ou URLs.
- confidence mede confiança factual na fonte e data. trend_score mede momentum editorial.
""".strip()
        return self._generate_candidates(prompt, query="gemini-trending-ai-news", limit=limit)

    def scout_discovery_source(
        self,
        *,
        source_name: str,
        source_url: str,
        limit: int = 8,
        focus: str = "",
    ) -> list[SearchCandidate]:
        prompt = f"""
Usa {source_name} apenas como fonte de descoberta de temas de InteligÃªncia Artificial.
Encontra os temas/notÃ­cias mais recentes publicados ou destacados por essa fonte, mas
devolve sempre a fonte original/primÃ¡ria que suporta cada notÃ­cia.

Fonte de descoberta: {source_name}
URL: {source_url}
Foco editorial: {focus or "IA global, Portugal, empresas, builders e regulaÃ§Ã£o"}
Data de hoje: {date.today().isoformat()}

Responde apenas em JSON vÃ¡lido, sem markdown, com no mÃ¡ximo {limit} candidatos:
{{
  "candidates": [
    {{
      "title": "tÃ­tulo da notÃ­cia",
      "source_url": "https://...",
      "source_name": "fonte original/primÃ¡ria",
      "published_at": "YYYY-MM-DD",
      "summary": "1 frase factual",
      "why_it_matters": "1 frase sobre relevÃ¢ncia para PTIA",
      "confidence": 0.0
    }}
  ]
}}

Regras:
- NÃ£o devolvas {source_name} como fonte final, excepto se for a Ãºnica entidade original.
- Preferir empresa original, regulador, universidade, Reuters/AP/Bloomberg/FT ou media tecnolÃ³gico credÃ­vel.
- Apenas Ãºltimos 5 dias.
- NÃ£o inventar datas nem URLs.
""".strip()
        query = f"discovery-source:{source_name}:{source_url}"
        return self._generate_candidates(prompt, query=query, limit=limit)

    def grounded_json(self, prompt: str, *, temperature: float = 0.1) -> dict[str, Any]:
        """Return structured JSON backed by Google Search grounding."""
        if not self.available:
            raise RuntimeError("GEMINI_API_KEY não está configurada.")
        response_data = self._generate_json_response(
            prompt,
            temperature=temperature,
            tools=[{"google_search": {}}],
        )
        candidate = (response_data.get("candidates") or [{}])[0]
        parts = ((candidate.get("content") or {}).get("parts") or [])
        text = "\n".join(str(part.get("text", "")) for part in parts if isinstance(part, dict))
        parsed = _extract_json(text)
        if not isinstance(parsed, dict):
            raise RuntimeError("Gemini devolveu uma resposta estruturada inválida.")
        parsed["_grounding_sources"] = self._grounding_sources(candidate)
        return parsed

    def grounded_research(self, prompt: str, *, temperature: float = 0.1) -> dict[str, Any]:
        """Research with Google Search while keeping the response format unconstrained."""
        if not self.available:
            raise RuntimeError("GEMINI_API_KEY não está configurada.")
        response_data = self._generate_json_response(
            prompt,
            temperature=temperature,
            tools=[{"google_search": {}}],
        )
        candidate = (response_data.get("candidates") or [{}])[0]
        parts = ((candidate.get("content") or {}).get("parts") or [])
        text = "\n".join(str(part.get("text", "")) for part in parts if isinstance(part, dict))
        if not text.strip():
            finish_reason = str(candidate.get("finishReason") or "sem conteúdo")
            raise RuntimeError(f"Gemini não devolveu pesquisa utilizável: {finish_reason}.")
        return {
            "text": text,
            "sources": self._grounding_sources(candidate),
        }

    def structured_json(self, prompt: str, *, temperature: float = 0.1) -> dict[str, Any]:
        """Convert supplied evidence into strict JSON without performing another search."""
        if not self.available:
            raise RuntimeError("GEMINI_API_KEY não está configurada.")
        response_data = self._generate_json_response(
            prompt,
            temperature=temperature,
            response_mime_type="application/json",
        )
        candidate = (response_data.get("candidates") or [{}])[0]
        parts = ((candidate.get("content") or {}).get("parts") or [])
        text = "\n".join(str(part.get("text", "")) for part in parts if isinstance(part, dict))
        parsed = _extract_json(text)
        if not isinstance(parsed, dict):
            raise RuntimeError("Gemini devolveu JSON estruturado inválido.")
        return parsed

    @staticmethod
    def _grounding_sources(candidate: dict[str, Any]) -> list[dict[str, str]]:
        metadata = candidate.get("groundingMetadata") or {}
        grounding_sources = []
        seen_urls: set[str] = set()
        for chunk in metadata.get("groundingChunks") or []:
            web = chunk.get("web") or {}
            url = str(web.get("uri") or "").strip()
            if not url or url in seen_urls:
                continue
            grounding_sources.append(
                {
                    "label": str(web.get("title") or url).strip(),
                    "url": url,
                }
            )
            seen_urls.add(url)
        return grounding_sources

    def rewrite_final_post(
        self,
        *,
        channel: str,
        title: str,
        body: str,
        hashtags: str,
        source_urls: list[str],
        feedback: str,
    ) -> RewriteResult:
        prompt = f"""
És editor sénior do PTIA. Reescreve apenas o draft do canal indicado, usando o
feedback do editor humano.

Persona editorial fixa:
- Jornalista/editor português de tecnologia e negócios.
- Focado em aplicação prática, produtividade, regulação e competitividade ativa na era da IA.
- Adota sempre a filosofia do "Sim, e..." (adição construtiva e impulsionadora) em vez de "Sim, mas..." (travar o progresso com contrariedades). Evita conjunções adversativas (como "mas", "contudo", "no entanto") para desvalorizar a notícia. Foca-te em somar valor prático, propor caminhos de execução e ideias de crescimento.
- Escreve para decisores, founders, profissionais e builders em Portugal.
- Tem ponto de vista, mas separa facto de leitura editorial.
- A primeira parte deve soar a notícia normal; a segunda deve ser a leitura PTIA (adição booster).

Canal: {channel}
Título atual: {title}
Texto atual:
{body}

Hashtags atuais:
{hashtags}

Fontes:
{chr(10).join(source_urls)}

Feedback do editor:
{feedback}

{PTIA_HUMAN_EDITORIAL_ARTICLE_PROMPT}

{PTIA_SPECIFIC_ANGLE_PROMPT}

{PTIA_COPY_STYLE_REFERENCES}

{PTIA_ANTI_ASSISTANT_PASS}

Regra reforcada para o canal site:
- Escreve como artigo editorial curado, nao como resumo de assistente.
- Usa lead forte, analise em 4 a 7 paragrafos e fecho memoravel.
- A fonte original fica visivel no fim.

Regras:
- Português europeu.
- Voz PTIA: clara, sóbria, inteligente, útil, sem hype.
- Não inventar factos, números ou claims.
- Manter referência à fonte original.
- Promessa editorial PTIA: "os sinais de IA que importam para quem decide, constrói e trabalha em Portugal".
- Usa esta sequência internamente: facto primeiro, tese específica depois, implicação concreta no fim.
- Não imprimas rótulos como "A notícia", "A leitura PTIA", "O que observar agora" ou "Porque importa".
- LinkedIn: tese clara, consequência concreta e fonte. Só acaba com pergunta se for específica e difícil de ignorar.
- Instagram: legenda curta, guardável, com 3 impactos concretos e fonte. Não usar tom de artigo longo.
- X: post curto, factual e com fonte; hook forte e leitura PTIA curta. Respeita o limite de 280 caracteres incluindo hashtags e link.
- Site: artigo editorial curado, arquivável, com fonte/data/categoria quando disponíveis. Lead forte, 4 a 7 parágrafos se houver material e sem CTA social.
- Não uses markdown pesado.
- Não acabar com perguntas genéricas sobre prioridades, opinião ou "o que achas".
- Evita títulos com "o que significa para Portugal?" quando o ângulo forçado não é material.
- Evita linguagem de IA e frases gastas: "sinal relevante", "separar sinal de ruído",
  "impacto prático", "merece atenção", "no contexto português", "workflows reais",
  "pode mudar tudo", "next-gen", "revolucionário", "O entusiasmo é compreensível",
  "quem consegue executar", "primeiro passo", "custo, risco e dependência".
- Prefere frases específicas, humanas e com tensão editorial.

Responde apenas em JSON válido:
{{
  "title": "título final",
  "body": "texto final reescrito",
  "hashtags": "hashtags finais se fizer sentido",
  "rationale": "1 frase sobre o que melhoraste"
}}
""".strip()
        return self._generate_rewrite(prompt, temperature=0.72)

    def polish_final_post(
        self,
        *,
        channel: str,
        title: str,
        body: str,
        hashtags: str,
        source_urls: list[str],
    ) -> RewriteResult:
        prompt = f"""
Actua como editor final PT-PT do PTIA, não como corrector gramatical.

Objectivo:
Transformar o texto num draft que soe escrito por uma pessoa: primeiro notícia factual,
depois uma tese editorial específica sobre aquela notícia (somando valor e novas ideias), depois uma consequência impulsionadora.

Persona editorial fixa:
- Jornalista/editor português de tecnologia e negócios.
- Focado em produtividade, regulação, competitividade e adoção ativa de tecnologia em Portugal.
- Adota sempre a filosofia do "Sim, e..." (adição construtiva e impulsionadora) em vez de "Sim, mas..." (travar o progresso com contrariedades). Evita conjunções adversativas (como "mas", "contudo", "no entanto") para desvalorizar a notícia. Foca-se em somar valor prático, propor caminhos de execução e ideias de crescimento.
- Escreve para decisores, founders, profissionais e builders.
- Não tenta ser neutro em tudo; tenta ser útil e honesto.
- Separa facto de interpretação.

Canal: {channel}
Título atual: {title}
Texto atual:
{body}

Hashtags atuais:
{hashtags}

Fontes:
{chr(10).join(source_urls)}

{PTIA_HUMAN_EDITORIAL_ARTICLE_PROMPT}

{PTIA_SPECIFIC_ANGLE_PROMPT}

{PTIA_COPY_STYLE_REFERENCES}

{PTIA_ANTI_ASSISTANT_PASS}

Regra reforcada para o canal site:
- Escreve como artigo editorial curado, nao como resumo de assistente.
- Usa lead forte, analise em 4 a 7 paragrafos e fecho memoravel.
- A fonte original fica visivel no fim.

Regras:
- Português europeu, sem brasileirismos.
- Mantém a notícia factual no início, sem opinião nem adornos.
- Depois acrescenta uma tese editorial concreta, sem a rotular explicitamente. A tese tem de depender dos factos desta notícia.
- Não imprimas headings ou rótulos como "A notícia", "A leitura PTIA", "O que observar agora" ou "Porque importa".
- Não inventar factos, números, datas, empresas ou conclusões.
- Não tornar o texto mais longo sem necessidade.
- Corrigir frases duras, traduções literais, inglês residual e tom genérico.
- Manter a fonte original visível.
- LinkedIn: tese clara, consequência concreta e fonte. Pergunta final só se for específica e não genérica.
- Instagram: legenda curta, guardável, com 3 impactos concretos e fonte.
- X: post curto, factual e com fonte; hook forte e leitura PTIA curta. Respeita o limite de 280 caracteres incluindo hashtags e link.
- Site: artigo editorial curado, arquivável, com fonte/data/categoria quando disponíveis. Lead forte, 4 a 7 parágrafos se houver material e sem CTA social.
- Não uses markdown pesado.
- Não terminar com perguntas genéricas sobre prioridades ou "o que achas".
- Evita títulos com "o que significa para Portugal?" quando o ângulo forçado não é material.
- Corta ou substitui estas expressões quando aparecerem: "sinal relevante",
  "separar sinal de ruído", "impacto prático", "merece atenção", "workflows reais",
  "no contexto português", "acompanhar de perto", "a próxima geração",
  "O entusiasmo é compreensível", "quem consegue executar", "primeiro passo",
  "custo, risco e dependência".
- O texto deve parecer editado por alguém com critério, não gerado por um assistente.

Responde apenas em JSON válido:
{{
  "title": "título polido",
  "body": "texto polido",
  "hashtags": "hashtags finais",
  "rationale": "1 frase curta sobre o que foi melhorado"
}}
""".strip()
        return self._generate_rewrite(prompt, temperature=0.7)

    def suggest_visual_image_titles(
        self,
        *,
        title: str,
        body: str,
        source_urls: list[str],
    ) -> list[dict[str, str]]:
        prompt = f"""
És editor sénior do PTIA. Sugere dois títulos visuais curtos para aparecerem
dentro de uma imagem de Instagram e X.

Tema:
{title}

Texto editorial:
{body}

Fontes:
{chr(10).join(source_urls)}

Objectivo:
- Criar uma frase que pare o scroll e deixe curiosidade para ler a legenda.
- Manter o tom PTIA: inteligente, editorial, português, crítico quando fizer sentido.
- Ser provocatório sem clickbait vazio, sensacionalismo ou tom de tabloide.

Regras:
- Sugere exactamente 2 títulos.
- O primeiro deve ser mais bait/provocatório.
- O segundo deve ser mais sóbrio/editorial.
- Cada título deve ter preferencialmente 6 a 10 palavras.
- Não inventes factos, números, promessas ou conclusões ausentes do texto.
- Não uses emojis, hashtags, aspas decorativas nem pontuação gritante.
- Escreve em português europeu.

Responde apenas em JSON válido:
{{
  "suggestions": [
    {{"tone": "provocatorio", "title": "titulo visual"}},
    {{"tone": "editorial", "title": "titulo visual"}}
  ]
}}
""".strip()
        response = self._generate_json_response(prompt, temperature=0.78)
        candidate = (response.get("candidates") or [{}])[0]
        parts = ((candidate.get("content") or {}).get("parts") or [])
        text = "\n".join(str(part.get("text", "")) for part in parts if isinstance(part, dict))
        return _image_title_suggestions_from_record(_extract_json(text))

    def _generate_candidates(self, prompt: str, *, query: str, limit: int) -> list[SearchCandidate]:
        if not self.available:
            raise RuntimeError("GEMINI_API_KEY não está configurada.")

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "tools": [{"google_search": {}}],
            "generationConfig": {
                "temperature": 0.2,
                "thinkingConfig": {"thinkingBudget": 0},
            },
        }
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.api_key,
            },
            method="POST",
        )
        try:
            with urlopen_direct(request, timeout=self.timeout_seconds) as response:
                response_data = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Gemini API HTTP {exc.code}: {body[:800]}") from exc
        except URLError as exc:
            raise RuntimeError(f"Gemini API indisponível: {exc.reason}") from exc

        candidates = self._candidates_from_response(response_data, query=query)
        return candidates[:limit]

    def _generate_rewrite(self, prompt: str, *, temperature: float = 0.55) -> RewriteResult:
        return self._generate_rewrite_from_response(
            self._generate_json_response(prompt, temperature=temperature)
        )

    def _generate_json_response(
        self,
        prompt: str,
        *,
        temperature: float,
        tools: list[dict[str, Any]] | None = None,
        response_mime_type: str = "",
    ) -> dict[str, Any]:
        if not self.available:
            raise RuntimeError("GEMINI_API_KEY não está configurada.")

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "thinkingConfig": {"thinkingBudget": 0},
            },
        }
        if tools:
            payload["tools"] = tools
        if response_mime_type:
            payload["generationConfig"]["responseMimeType"] = response_mime_type
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.api_key,
            },
            method="POST",
        )
        try:
            with urlopen_direct(request, timeout=self.timeout_seconds) as response:
                response_data = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Gemini API HTTP {exc.code}: {body[:800]}") from exc
        except URLError as exc:
            raise RuntimeError(f"Gemini API indisponível: {exc.reason}") from exc

        return response_data

    def _generate_rewrite_from_response(self, response_data: dict[str, Any]) -> RewriteResult:
        candidate = (response_data.get("candidates") or [{}])[0]
        parts = ((candidate.get("content") or {}).get("parts") or [])
        text = "\n".join(str(part.get("text", "")) for part in parts if isinstance(part, dict))
        return _rewrite_from_record(_extract_json(text))

    def _candidates_from_response(self, response_data: dict[str, Any], *, query: str) -> list[SearchCandidate]:
        candidate = (response_data.get("candidates") or [{}])[0]
        parts = ((candidate.get("content") or {}).get("parts") or [])
        text = "\n".join(str(part.get("text", "")) for part in parts if isinstance(part, dict))

        parsed_candidates: list[SearchCandidate] = []
        if text.strip():
            try:
                parsed_candidates = [
                    _candidate_from_record(record, query=query)
                    for record in _candidate_records(_extract_json(text))
                ]
            except (json.JSONDecodeError, TypeError, ValueError):
                parsed_candidates = []

        seen_urls = {candidate.url for candidate in parsed_candidates if candidate.url}
        metadata = candidate.get("groundingMetadata") or {}
        for chunk in metadata.get("groundingChunks") or []:
            web = chunk.get("web") or {}
            uri = str(web.get("uri") or "")
            if not uri or uri in seen_urls:
                continue
            parsed_candidates.append(
                SearchCandidate(
                    title=str(web.get("title") or uri),
                    url=uri,
                    source_name=str(web.get("title") or ""),
                    query=query,
                )
            )
            seen_urls.add(uri)
        return parsed_candidates

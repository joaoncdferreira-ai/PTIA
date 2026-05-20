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
        query=query,
    )


def _rewrite_from_record(record: dict[str, Any]) -> RewriteResult:
    return RewriteResult(
        title=str(record.get("title") or ""),
        body=str(record.get("body") or record.get("text") or ""),
        hashtags=str(record.get("hashtags") or ""),
        rationale=str(record.get("rationale") or record.get("reason") or ""),
    )


class GeminiGroundedSearchProvider:
    """Small REST client for Gemini Grounding with Google Search.

    It intentionally returns candidates only. PTIA still validates domains and dates
    locally before anything reaches Verified Selection.
    """

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
Quais são as notícias mais importantes sobre Inteligência Artificial publicadas hoje
ou nos últimos 5 dias, no mundo e em Portugal?

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

Critérios editoriais PTIA:
- Priorizar impacto real para empresas, profissionais, builders, regulação e Portugal.
- Separar mundo e Portugal, mas não forçar Portugal se não houver fonte credível.
- Não incluir rumores sem fonte.
- Não inventar datas nem URLs.
""".strip()
        return self._generate_candidates(prompt, query="gemini-scout-today", limit=limit)

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
- Cético com hype, interessado em aplicação prática, produtividade, regulação e competitividade.
- Escreve para decisores, founders, profissionais e builders em Portugal.
- Tem ponto de vista, mas separa facto de leitura editorial.
- A primeira parte deve soar a notícia normal; a segunda deve ser leitura PTIA.

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

Regras:
- Português europeu.
- Voz PTIA: clara, sóbria, inteligente, útil, sem hype.
- Não inventar factos, números ou claims.
- Manter referência à fonte original.
- Promessa editorial PTIA: "os sinais de IA que importam para quem decide, constrói e trabalha em Portugal".
- Usa esta sequência internamente: facto primeiro, leitura editorial depois, implicação ou acção no fim.
- Não imprimas rótulos como "A notícia", "A leitura PTIA", "O que observar agora" ou "Porque importa".
- LinkedIn: tese clara, consequência concreta e fonte. Só acaba com pergunta se for específica e difícil de ignorar.
- Instagram: legenda curta, guardável, com 3 impactos concretos e fonte. Não usar tom de artigo longo.
- Site: artigo curto, arquivável, com fonte/data/categoria quando disponíveis. Sem CTA social.
- Não uses markdown pesado.
- Não acabar com perguntas genéricas sobre prioridades, opinião ou "o que achas".
- Evita títulos com "o que significa para Portugal?" quando o ângulo forçado não é material.
- Evita linguagem de IA e frases gastas: "sinal relevante", "separar sinal de ruído",
  "impacto prático", "merece atenção", "no contexto português", "workflows reais",
  "pode mudar tudo", "next-gen", "revolucionário".
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
depois leitura editorial PTIA com ponto de vista, depois acção ou pergunta útil.

Persona editorial fixa:
- Jornalista/editor português de tecnologia e negócios.
- Cético com hype, atento a produtividade, regulação, competitividade e adopção em Portugal.
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

Regras:
- Português europeu, sem brasileirismos.
- Mantém a notícia factual no início, sem opinião nem adornos.
- Depois acrescenta uma tese editorial concreta, sem a rotular explicitamente.
- Não imprimas headings ou rótulos como "A notícia", "A leitura PTIA", "O que observar agora" ou "Porque importa".
- Não inventar factos, números, datas, empresas ou conclusões.
- Não tornar o texto mais longo sem necessidade.
- Corrigir frases duras, traduções literais, inglês residual e tom genérico.
- Manter a fonte original visível.
- LinkedIn: tese clara, consequência concreta e fonte. Pergunta final só se for específica e não genérica.
- Instagram: legenda curta, guardável, com 3 impactos concretos e fonte.
- Site: factual, curto, arquivável, com fonte/data/categoria quando disponíveis. Sem CTA social.
- Não uses markdown pesado.
- Não terminar com perguntas genéricas sobre prioridades ou "o que achas".
- Evita títulos com "o que significa para Portugal?" quando o ângulo forçado não é material.
- Corta ou substitui estas expressões quando aparecerem: "sinal relevante",
  "separar sinal de ruído", "impacto prático", "merece atenção", "workflows reais",
  "no contexto português", "acompanhar de perto", "a próxima geração".
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

        return self._generate_rewrite_from_response(response_data)

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

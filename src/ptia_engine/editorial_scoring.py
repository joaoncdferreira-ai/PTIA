from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from ptia_engine.models import RadarSignal


PORTUGAL_TERMS = {
    "portugal",
    "português",
    "portuguesa",
    "portugueses",
    "lisboa",
    "porto",
    "coimbra",
    "braga",
    "aveiro",
    "leiria",
    "guimarães",
    "matosinhos",
    "sines",
    "governo português",
    "república portuguesa",
    # Empresas e centros de investigação com ADN português. Esta lista é o
    # principal sinal de relevância local: conteúdo sobre o ecossistema
    # nacional gera muito mais engagement por impressão do que noticia
    # internacional generica.
    "feedzai",
    "unbabel",
    "defined.ai",
    "definedcrowd",
    "luz saúde",
    "sword health",
    "outsystems",
    "talkdesk",
    "neuraspace",
    "tekever",
    "priberam",
    "critical software",
    "augusta labs",
    "brainr",
    "cascade",
    "starkdata",
    "neuralshift",
    "aptoide",
    "bloq.it",
    "indie campers",
    "greenvolt",
    "farfetch",
    "veniam",
    "codacy",
    "inesc",
    "inesc tec",
    "champalimaud",
    "instituto superior técnico",
    "universidade de lisboa",
    "universidade do porto",
    "startup portugal",
    "banco de fomento",
    "força aérea portuguesa",
    "agência espacial portuguesa",
}

CATEGORY_TERMS = {
    "portugal": PORTUGAL_TERMS,
    "regulation": {"regulação", "regulamento", "lei", "ai act", "comissão europeia", "privacidade"},
    "research": {"estudo", "investigação", "paper", "arxiv", "universidade", "benchmark"},
    "builders": {"developer", "programador", "coding", "api", "open source", "modelo", "agent", "agente"},
    "business": {"empresa", "startup", "negócio", "mercado", "investimento", "aquisição", "produtividade"},
}

GENERIC_PHRASES = {
    "nova informação sobre inteligência artificial",
    "o dado que interessa é este",
    "porque importa",
    "o que significa para portugal",
}


@dataclass(frozen=True, slots=True)
class CandidateScore:
    signal_id: str
    total: float
    editorial_value: float
    engagement_probability: float
    freshness: float
    portfolio_fit: float
    risk_penalty: float
    learning_adjustment: float
    category: str
    local_relevance: bool
    explanation: list[str]

    def to_record(self) -> dict:
        return asdict(self)


def signal_text(signal: RadarSignal) -> str:
    return " ".join(
        value.strip()
        for value in (
            signal.title,
            signal.summary,
            signal.why_it_matters,
            signal.topic_hint,
        )
        if value and value.strip()
    )


def contains_local_relevance(signal: RadarSignal) -> bool:
    text = signal_text(signal).casefold()
    return any(term in text for term in PORTUGAL_TERMS)


def infer_category(signal: RadarSignal) -> str:
    text = signal_text(signal).casefold()
    if contains_local_relevance(signal):
        return "portugal"
    scores = {
        category: sum(1 for term in terms if term in text)
        for category, terms in CATEGORY_TERMS.items()
        if category != "portugal"
    }
    best = max(scores, key=scores.get, default="world")
    return best if scores.get(best, 0) else "world"


def _freshness_score(published_at: str) -> float:
    if not published_at:
        return 0.0
    raw = published_at.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        try:
            parsed = datetime.fromisoformat(raw[:10])
        except ValueError:
            return 0.0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    age_hours = max(0.0, (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds() / 3600)
    return max(0.0, 100.0 - age_hours * 1.7)


def _specificity_score(signal: RadarSignal) -> float:
    text = signal_text(signal)
    words = re.findall(r"\b[\wÀ-ÿ.-]+\b", text)
    named_or_numeric = re.findall(r"\b(?:[A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÀ-ÿ.-]+|\d+(?:[.,]\d+)?)\b", text)
    score = min(100.0, len(words) * 1.15 + len(named_or_numeric) * 5.5)
    lowered = text.casefold()
    if any(phrase in lowered for phrase in GENERIC_PHRASES):
        score -= 35
    return max(0.0, score)


def _learned_adjustment(signal: RadarSignal, learning_weights: dict | None) -> float:
    patterns = (learning_weights or {}).get("editorial_patterns", {})
    if not patterns:
        return 0.0
    text = signal_text(signal)
    length = len(text)
    length_bucket = "short" if length < 500 else "medium" if length < 1100 else "long"
    entries = (
        patterns.get("question", {}).get("present" if "?" in text else "absent", {}),
        patterns.get("local_relevance", {}).get(
            "present" if contains_local_relevance(signal) else "absent",
            {},
        ),
        patterns.get("length", {}).get(length_bucket, {}),
    )
    return float(max(-8, min(8, sum(float(entry.get("adjustment", 0)) for entry in entries))))


def score_signal(signal: RadarSignal, learning_weights: dict | None = None) -> CandidateScore:
    local = contains_local_relevance(signal)
    category = infer_category(signal)
    specificity = _specificity_score(signal)
    has_summary = len((signal.summary or "").strip()) >= 45
    has_consequence = len((signal.why_it_matters or "").strip()) >= 30

    # Peso local reforçado: a performance medida no LinkedIn mostra que conteúdo
    # sobre o ecossistema português gera cerca de 2,2% de likes por impressão
    # contra 0,89% do internacional genérico, e todos os posts com alcance
    # acima de 300 impressões foram histórias portuguesas.
    editorial_value = min(
        100.0,
        specificity * 0.45
        + (22 if has_summary else 0)
        + (18 if has_consequence else 0)
        + (26 if local else 0),
    )
    learning_adjustment = _learned_adjustment(signal, learning_weights)
    engagement_probability = min(
        100.0,
        max(0.0, float(signal.engagement_score)) * 0.55
        + (30 if local else 0)
        + (10 if has_consequence else 0),
    )
    engagement_probability = max(0.0, min(100.0, engagement_probability + learning_adjustment))
    freshness = _freshness_score(signal.published_at)
    portfolio_fit = 92.0 if local else 55.0
    risk_penalty = 0.0
    explanation: list[str] = []

    if local:
        explanation.append("relevância portuguesa explícita")
    if has_consequence:
        explanation.append("consequência editorial concreta")
    if specificity >= 65:
        explanation.append("factos e entidades específicos")
    if not has_summary:
        risk_penalty += 35
        explanation.append("resumo factual insuficiente")
    if not signal.url:
        risk_penalty += 50
        explanation.append("fonte ausente")
    if signal.status not in {"verified", "verified_secondary", "selected"}:
        risk_penalty += 100
        explanation.append("fonte não verificada")
    if learning_adjustment:
        explanation.append(f"ajuste por performance histórica {learning_adjustment:+.0f}")

    total = (
        editorial_value * 0.55
        + engagement_probability * 0.25
        + freshness * 0.10
        + portfolio_fit * 0.10
        - risk_penalty
    )
    return CandidateScore(
        signal_id=signal.signal_id,
        total=round(max(0.0, total), 2),
        editorial_value=round(editorial_value, 2),
        engagement_probability=round(engagement_probability, 2),
        freshness=round(freshness, 2),
        portfolio_fit=round(portfolio_fit, 2),
        risk_penalty=round(risk_penalty, 2),
        learning_adjustment=round(learning_adjustment, 2),
        category=category,
        local_relevance=local,
        explanation=explanation,
    )


def select_portfolio(
    signals: list[RadarSignal],
    *,
    limit: int = 4,
    excluded_signal_ids: set[str] | None = None,
    learning_weights: dict | None = None,
) -> tuple[list[tuple[RadarSignal, CandidateScore]], list[tuple[RadarSignal, CandidateScore]]]:
    excluded = excluded_signal_ids or set()
    ranked = sorted(
        (
            (signal, score_signal(signal, learning_weights))
            for signal in signals
            if signal.signal_id not in excluded
            and signal.status in {"verified", "verified_secondary", "selected"}
        ),
        key=lambda row: (row[1].total, row[0].published_at),
        reverse=True,
    )

    selected: list[tuple[RadarSignal, CandidateScore]] = []
    category_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    selected_urls: set[str] = set()

    local_candidate = next((row for row in ranked if row[1].local_relevance and row[1].total >= 35), None)
    if local_candidate:
        selected.append(local_candidate)
        category_counts[local_candidate[1].category] = 1
        source_counts[local_candidate[0].source_name] = 1
        selected_urls.add(local_candidate[0].url.strip().casefold())

    for row in ranked:
        signal, score = row
        if row in selected or len(selected) >= limit:
            continue
        canonical_url = signal.url.strip().casefold()
        if canonical_url and canonical_url in selected_urls:
            continue
        if score.total < 30:
            continue
        # O ecossistema português é o foco editorial, por isso admite mais
        # histórias nacionais na mesma fila do que qualquer outra categoria.
        category_cap = 3 if score.category == "portugal" else 2
        if category_counts.get(score.category, 0) >= category_cap:
            continue
        if source_counts.get(signal.source_name, 0) >= 2:
            continue
        selected.append(row)
        if canonical_url:
            selected_urls.add(canonical_url)
        category_counts[score.category] = category_counts.get(score.category, 0) + 1
        source_counts[signal.source_name] = source_counts.get(signal.source_name, 0) + 1

    selected_ids = {signal.signal_id for signal, _score in selected}
    alternatives = [row for row in ranked if row[0].signal_id not in selected_ids]
    return selected, alternatives

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from urllib.parse import urlparse

from ptia_engine.dedupe import stable_hash
from ptia_engine.models import FinalPost, RadarSignal, utc_now_iso
from ptia_engine.services.editorial_hygiene import copy_quality_issues


GENERIC_FALLBACK_PATTERNS = (
    r"\ba fonte publicou uma nova informação\b",
    r"\bnova informação sobre inteligência artificial\b",
    r"\bo dado que interessa é este\b",
    r"\bvalidar o impacto para empresas, profissionais e builders\b",
)

GENERIC_INDEX_PATTERNS = (
    r"\búltimas notícias\b",
    r"\bnotícias,\s*opinião\b",
    r"\btudo sobre inteligência artificial\b",
)

GENERIC_INDEX_SLUGS = {
    "ai",
    "ia",
    "artificial-intelligence",
    "inteligencia-artificial",
}

STOP_WORDS = {
    "para", "como", "uma", "das", "dos", "com", "sem", "que", "por", "esta",
    "este", "sobre", "mais", "entre", "fonte", "original", "inteligência", "artificial",
}


@dataclass(slots=True)
class EditorialFactPack:
    fact_pack_id: str
    signal_id: str
    title: str
    source_url: str
    source_name: str
    published_at: str
    facts: list[str]
    entities: list[str]
    numbers: list[str]
    thesis: str
    consequence: str
    portugal_angle: str
    uncertainty: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)

    def to_record(self) -> dict:
        return asdict(self)

    @classmethod
    def from_record(cls, record: dict) -> "EditorialFactPack":
        return cls(
            fact_pack_id=str(record["fact_pack_id"]),
            signal_id=str(record["signal_id"]),
            title=str(record.get("title", "")),
            source_url=str(record.get("source_url", "")),
            source_name=str(record.get("source_name", "")),
            published_at=str(record.get("published_at", "")),
            facts=[str(value) for value in record.get("facts", [])],
            entities=[str(value) for value in record.get("entities", [])],
            numbers=[str(value) for value in record.get("numbers", [])],
            thesis=str(record.get("thesis", "")),
            consequence=str(record.get("consequence", "")),
            portugal_angle=str(record.get("portugal_angle", "")),
            uncertainty=[str(value) for value in record.get("uncertainty", [])],
            created_at=str(record.get("created_at", "")),
        )


@dataclass(frozen=True, slots=True)
class QualityGateReport:
    passed: bool
    issues: list[str]
    warnings: list[str]

    def to_record(self) -> dict:
        return asdict(self)


def _sentences(text: str) -> list[str]:
    return [
        value.strip()
        for value in re.split(r"(?<=[.!?])\s+|\n+", text or "")
        if len(value.strip()) >= 18
    ]


def _entities(text: str) -> list[str]:
    values = re.findall(
        r"\b(?:[A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÀ-ÿ.-]+(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÀ-ÿ.-]+){0,3})\b",
        text or "",
    )
    return list(dict.fromkeys(value.strip() for value in values if len(value.strip()) > 2))[:20]


def _numbers(text: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"\b\d+(?:[.,]\d+)?(?:\s*%|\s*(?:milhões|mil|milhares|biliões))?\b", text or "", re.IGNORECASE)))


def build_fact_pack(signal: RadarSignal) -> EditorialFactPack:
    summary = (signal.summary or "").strip()
    why = (signal.why_it_matters or "").strip()
    facts = _sentences(summary)
    if signal.title.strip() and signal.title.strip() not in facts:
        facts.insert(0, signal.title.strip().rstrip(".") + ".")
    thesis = why or (facts[1] if len(facts) > 1 else facts[0] if facts else "")
    consequence = why or summary
    text = " ".join([signal.title, summary, why])
    local = bool(re.search(r"\b(portugal|portugu[eê]s(?:a|es)?|lisboa|porto)\b", text, re.IGNORECASE))
    return EditorialFactPack(
        fact_pack_id=f"facts_{stable_hash(signal.signal_id, 18)}",
        signal_id=signal.signal_id,
        title=signal.title.strip(),
        source_url=signal.url.strip(),
        source_name=signal.source_name.strip(),
        published_at=signal.published_at.strip(),
        facts=facts[:8],
        entities=_entities(text),
        numbers=_numbers(text),
        thesis=thesis,
        consequence=consequence,
        portugal_angle=why if local else "",
        uncertainty=[] if summary else ["A fonte verificada não tem resumo factual suficiente."],
    )


def validate_fact_pack(pack: EditorialFactPack) -> QualityGateReport:
    issues: list[str] = []
    warnings: list[str] = []
    combined = " ".join([pack.title, *pack.facts, pack.thesis, pack.consequence])
    if not pack.source_url:
        issues.append("Fact Pack sem URL da fonte")
    if not pack.published_at:
        issues.append("Fact Pack sem data de publicação")
    if not pack.source_name:
        issues.append("Fact Pack sem fonte identificada")
    if re.match(r"^https?://", pack.title, re.IGNORECASE):
        issues.append("Fact Pack com URL no lugar do título")
    parsed_url = urlparse(pack.source_url)
    path_parts = [part for part in parsed_url.path.casefold().split("/") if part]
    if len(path_parts) == 1 and path_parts[0] in GENERIC_INDEX_SLUGS:
        issues.append("Fonte aponta para uma página índice, não para um artigo")
    if not pack.facts or len(" ".join(pack.facts)) < 45:
        issues.append("Fact Pack sem factos suficientes")
    if not pack.thesis or len(pack.thesis) < 25:
        issues.append("Fact Pack sem tese editorial específica")
    if any(re.search(pattern, combined, re.IGNORECASE) for pattern in GENERIC_FALLBACK_PATTERNS):
        issues.append("Fact Pack contém fallback editorial genérico")
    if any(re.search(pattern, combined, re.IGNORECASE) for pattern in GENERIC_INDEX_PATTERNS):
        issues.append("Fact Pack parece descrever uma página genérica de notícias")
    if not pack.portugal_angle:
        warnings.append("sem ângulo Portugal material; não forçar")
    return QualityGateReport(not issues, issues, warnings)


def _meaningful_tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"\b[\wÀ-ÿ.-]{4,}\b", (text or "").casefold())
        if token not in STOP_WORDS
    }


def validate_package(pack: EditorialFactPack, posts: list[FinalPost], *, require_images: bool = True) -> QualityGateReport:
    issues: list[str] = []
    warnings: list[str] = []
    source_tokens = _meaningful_tokens(" ".join([pack.title, *pack.facts, pack.thesis, pack.consequence]))
    allowed_numbers = set(pack.numbers) | set(_numbers(pack.published_at))
    expected_channels = {"linkedin", "instagram", "site"}
    channels = {post.channel for post in posts}
    missing_channels = sorted(expected_channels - channels)
    if missing_channels:
        issues.append("pacote sem canais: " + ", ".join(missing_channels))

    for post in posts:
        for issue in copy_quality_issues(post):
            issues.append(f"{post.channel}: {issue}")
        body = post.body or ""
        if any(re.search(pattern, body, re.IGNORECASE) for pattern in GENERIC_FALLBACK_PATTERNS):
            issues.append(f"{post.channel}: fallback editorial genérico")
        if pack.source_url not in post.source_urls:
            issues.append(f"{post.channel}: fonte do Fact Pack ausente")
        overlap = source_tokens & _meaningful_tokens(f"{post.title} {body}")
        if len(overlap) < 3:
            issues.append(f"{post.channel}: texto sem ligação semântica suficiente aos factos")
        post_numbers = set(_numbers(re.sub(r"https?://\S+", "", body)))
        unsupported = sorted(post_numbers - allowed_numbers)
        if unsupported:
            warnings.append(f"{post.channel}: confirmar números não presentes no Fact Pack: {', '.join(unsupported)}")
        if require_images and post.channel in {"linkedin", "instagram", "x", "site"} and not (
            post.image_path or post.image_variants
        ):
            issues.append(f"{post.channel}: imagem final ausente")
        if "?" in body and post.channel in {"linkedin", "instagram"}:
            warnings.append(f"{post.channel}: pergunta no texto; dados PTIA sugerem menor engagement")
        if re.search(r"[�]|(?:Ã.|Â.)", body):
            issues.append(f"{post.channel}: possível encoding corrompido")

    return QualityGateReport(not issues, list(dict.fromkeys(issues)), list(dict.fromkeys(warnings)))

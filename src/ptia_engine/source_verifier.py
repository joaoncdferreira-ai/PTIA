from __future__ import annotations

import re
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from urllib.error import HTTPError
from urllib.parse import urljoin, urlparse, urlunparse

from ptia_engine.editorial_board import ensure_recent_signal
from ptia_engine.http_client import urlopen_direct
from ptia_engine.news_media_domains import (
    GLOBAL_NEWS_MEDIA_DOMAINS,
    PORTUGUESE_NEWS_MEDIA_DOMAINS,
)
from ptia_engine.search_providers import GeminiGroundedSearchProvider, SearchCandidate


EDITORIAL_CREDIBLE_DOMAINS = {
    "anthropic.com": "Anthropic",
    "openai.com": "OpenAI",
    "blog.google": "Google",
    "deepmind.google": "Google DeepMind",
    "cloud.google.com": "Google Cloud",
    "microsoft.com": "Microsoft",
    "blogs.microsoft.com": "Microsoft",
    "aboutamazon.com": "Amazon",
    "nvidia.com": "NVIDIA",
    "mistral.ai": "Mistral AI",
    "meta.com": "Meta",
    "ai.meta.com": "Meta AI",
    "ramp.com": "Ramp",
    "adaptionlabs.ai": "Adaption Labs",
    "aisi.gov.uk": "UK AI Safety Institute",
    "businesswire.com": "Business Wire",
    "prnewswire.com": "PR Newswire",
    "reuters.com": "Reuters",
    "apnews.com": "AP",
    "theguardian.com": "The Guardian",
    "bloomberg.com": "Bloomberg",
    "ft.com": "Financial Times",
    "theverge.com": "The Verge",
    "technologyreview.com": "MIT Technology Review",
    "wired.com": "Wired",
    "techcrunch.com": "TechCrunch",
    "venturebeat.com": "VentureBeat",
    "siliconangle.com": "SiliconANGLE",
    "the-decoder.com": "The Decoder",
    "iapp.org": "IAPP",
    "biometricupdate.com": "Biometric Update",
    "futurumgroup.com": "Futurum Group",
    "morningstar.com": "Morningstar",
    "gartner.com": "Gartner",
    "arxiv.org": "arXiv",
    "europa.eu": "European Commission",
    "edpb.europa.eu": "EDPB",
    "cnpd.pt": "CNPD",
    "portugal.gov.pt": "Governo de Portugal",
    "ama.gov.pt": "AMA",
    "portugaldigital.gov.pt": "Portugal Digital",
    "ani.pt": "ANI",
    "apdc.pt": "APDC",
    "startupportugal.com": "Startup Portugal",
    "inesctec.pt": "INESC TEC",
    "tecnico.ulisboa.pt": "Instituto Superior Técnico",
    "up.pt": "Universidade do Porto",
    "ulisboa.pt": "Universidade de Lisboa",
    "eco.sapo.pt": "ECO",
    "jornaldenegocios.pt": "Jornal de Negócios",
    "jornaleconomico.sapo.pt": "Jornal Económico",
    "publico.pt": "Público",
    "observador.pt": "Observador",
    "expresso.pt": "Expresso",
    "portugalresident.com": "Portugal Resident",
    "dn.pt": "Diário de Notícias",
}


CREDIBLE_DOMAINS = {
    **GLOBAL_NEWS_MEDIA_DOMAINS,
    **PORTUGUESE_NEWS_MEDIA_DOMAINS,
    **EDITORIAL_CREDIBLE_DOMAINS,
}


DISCOVERY_ONLY_DOMAINS = {
    "rundown.ai": "The Rundown AI",
    "therundown.ai": "The Rundown AI",
}


BLOCKED_SOURCE_HOSTS = {
    "vertexaisearch.cloud.google.com",
}


BLOCKED_SOURCE_PATH_PARTS = {
    "/grounding-api-redirect/",
}


@dataclass(slots=True)
class VerificationResult:
    status: str
    source_name: str
    title: str
    published_at: str
    summary: str
    notes: str
    verified_url: str = ""


def domain_for_url(url: str) -> str:
    host = urlparse(url).netloc.casefold()
    if host.startswith("www."):
        host = host[4:]
    return host


def canonical_source_url(url: str) -> str:
    parsed = urlparse(url.strip())
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))


def is_blocked_source_url(url: str) -> bool:
    parsed = urlparse(url)
    host = domain_for_url(url)
    if host in BLOCKED_SOURCE_HOSTS:
        return True
    path = parsed.path.casefold()
    return any(part in path for part in BLOCKED_SOURCE_PATH_PARTS)


def credible_source_name(url: str) -> str:
    if is_blocked_source_url(url):
        return ""
    host = domain_for_url(url)
    for domain, name in CREDIBLE_DOMAINS.items():
        if host == domain or host.endswith("." + domain):
            return name
    return ""


def discovery_source_name(url: str) -> str:
    host = domain_for_url(url)
    for domain, name in DISCOVERY_ONLY_DOMAINS.items():
        if host == domain or host.endswith("." + domain):
            return name
    return ""


def _extract(patterns: list[str], html: str) -> str:
    for pattern in patterns:
        match = re.search(pattern, html, flags=re.IGNORECASE | re.DOTALL)
        if match:
            return unescape(re.sub(r"\s+", " ", match.group(1)).strip())
    return ""


def fetch_page_html(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "PTIAEditorialBot/0.1 (+local editorial verification)"},
    )
    with urlopen_direct(request, timeout=12) as response:
        return response.read(900_000).decode("utf-8", errors="ignore")


def extract_credible_links(html: str, base_url: str, limit: int = 12) -> list[str]:
    links: list[str] = []
    seen: set[str] = set()
    for raw_href in re.findall(r'href=["\']([^"\']+)["\']', html, flags=re.IGNORECASE):
        href = unescape(raw_href).strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        url = urljoin(base_url, href)
        if url in seen or not credible_source_name(url):
            continue
        seen.add(url)
        links.append(url)
        if len(links) >= limit:
            break
    return links


def _normalise_date(value: str) -> str:
    raw = value.strip()
    if not raw:
        return ""
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        for fmt in ("%B %d, %Y", "%b %d, %Y"):
            try:
                return datetime.strptime(raw, fmt).date().isoformat()
            except ValueError:
                continue
        date_match = re.search(r"\d{4}-\d{2}-\d{2}", raw)
        return date_match.group(0) if date_match else ""
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).date().isoformat()


def _date_from_url(url: str) -> str:
    path = urlparse(url).path
    iso_match = re.search(r"(\d{4})-(\d{2})-(\d{2})(?:[-/]|$)", path)
    if iso_match:
        return "-".join(iso_match.groups())

    numeric_path_match = re.search(r"/(\d{4})/(\d{1,2})/(\d{1,2})(?:/|$)", path)
    if numeric_path_match:
        year, month, day = numeric_path_match.groups()
        return f"{year}-{int(month):02d}-{int(day):02d}"

    month_match = re.search(
        r"/(\d{4})/(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)/(\d{1,2})(?:/|$)",
        path,
        flags=re.IGNORECASE,
    )
    if month_match:
        months = {
            "jan": "01",
            "feb": "02",
            "mar": "03",
            "apr": "04",
            "may": "05",
            "jun": "06",
            "jul": "07",
            "aug": "08",
            "sep": "09",
            "oct": "10",
            "nov": "11",
            "dec": "12",
        }
        year, month_name, day = month_match.groups()
        return f"{year}-{months[month_name[:3].casefold()]}-{int(day):02d}"
    return ""


def fetch_page_metadata(url: str) -> tuple[str, str, str]:
    body = fetch_page_html(url)
    title = _extract(
        [
            r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+name=["\']twitter:title["\'][^>]+content=["\']([^"\']+)["\']',
            r"<title[^>]*>(.*?)</title>",
        ],
        body,
    )
    description = _extract(
        [
            r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']',
        ],
        body,
    )
    published_at = _extract(
        [
            r'<meta[^>]+property=["\']article:published_time["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+name=["\']date["\'][^>]+content=["\']([^"\']+)["\']',
            r'"datePublished"\s*:\s*"([^"]+)"',
            r'"dateCreated"\s*:\s*"([^"]+)"',
            r'"publishedOn"\s*:\s*"([^"]+)"',
            r'<time[^>]+datetime=["\']([^"\']+)["\']',
            r'<meta[^>]+name=["\']publishdate["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+name=["\']pubdate["\'][^>]+content=["\']([^"\']+)["\']',
            r'<span[^>]+class=["\'][^"\']*date[^"\']*["\'][^>]*>\s*(\d{4}-\d{2}-\d{2})\s*</span>',
            r'<div[^>]*class=["\'][^"\']*agate[^"\']*["\'][^>]*>\s*([A-Z][a-z]+ \d{1,2}, \d{4})\s*</div>',
        ],
        body,
    )
    return title, description, _normalise_date(published_at) or _date_from_url(url)


def verify_url(url: str) -> VerificationResult:
    url = canonical_source_url(url)
    source_name = credible_source_name(url)
    if not source_name:
        return VerificationResult(
            status="verifying",
            source_name="Unverified",
            title=url,
            published_at="",
            summary="",
            notes="Fonte ainda nao reconhecida como credível. O engine precisa procurar uma fonte primária ou media credível.",
            verified_url=url,
        )

    try:
        title, summary, published_at = fetch_page_metadata(url)
    except Exception as exc:  # noqa: BLE001 - keep submitted links visible in verifying.
        if isinstance(exc, HTTPError) and exc.code not in {401, 403, 429}:
            return VerificationResult(
                status="rejected",
                source_name=source_name,
                title=url,
                published_at="",
                summary="",
                notes=f"A fonte respondeu HTTP {exc.code}; o artigo individual não existe ou não está acessível.",
                verified_url=url,
            )
        url_date = _date_from_url(url)
        if url_date:
            try:
                ensure_recent_signal(url_date)
            except ValueError as recent_exc:
                return VerificationResult(
                    status="rejected",
                    source_name=source_name,
                    title=url,
                    published_at=url_date,
                    summary="",
                    notes=str(recent_exc),
                    verified_url=url,
                )
            return VerificationResult(
                status="verified",
                source_name=source_name,
                title=url,
                published_at=url_date,
                summary="",
                notes=(
                    "Fonte credível e data dos últimos 5 dias verificadas pelo URL. "
                    f"Metadata bloqueada ou indisponível: {exc}"
                ),
                verified_url=url,
            )
        return VerificationResult(
            status="verifying",
            source_name=source_name,
            title=url,
            published_at="",
            summary="",
            notes=f"Fonte credível detectada, mas metadata ainda nao foi lida: {exc}",
            verified_url=url,
        )

    if not published_at:
        return VerificationResult(
            status="verifying",
            source_name=source_name,
            title=title or url,
            published_at="",
            summary=summary,
            notes="Fonte credível detectada, mas falta data exacta. Nao passa sem data dos ultimos 5 dias.",
            verified_url=url,
        )

    try:
        ensure_recent_signal(published_at)
    except ValueError as exc:
        return VerificationResult(
            status="rejected",
            source_name=source_name,
            title=title or url,
            published_at=published_at,
            summary=summary,
            notes=str(exc),
            verified_url=url,
        )

    return VerificationResult(
        status="verified",
        source_name=source_name,
        title=title or url,
        published_at=published_at,
        summary=summary,
        notes="Fonte credível e data dos últimos 5 dias verificadas automaticamente.",
        verified_url=url,
    )


def _metadata_for_query(url: str) -> tuple[str, str]:
    try:
        title, summary, _published_at = fetch_page_metadata(url)
    except Exception:  # noqa: BLE001 - submitted links may block metadata fetches.
        return "", ""
    return title, summary


def _with_notes(result: VerificationResult, extra_notes: str) -> VerificationResult:
    notes = "\n".join(part for part in [result.notes, extra_notes] if part)
    return VerificationResult(
        status=result.status,
        source_name=result.source_name,
        title=result.title,
        published_at=result.published_at,
        summary=result.summary,
        notes=notes,
        verified_url=result.verified_url,
    )


def resolve_discovery_link(submitted_url: str) -> VerificationResult:
    """Try to turn a discovery-only article into one of its original sources."""

    discovery_name = discovery_source_name(submitted_url)
    if not discovery_name:
        return verify_url(submitted_url)

    try:
        body = fetch_page_html(submitted_url)
    except Exception as exc:  # noqa: BLE001 - keep the discovery link visible.
        return VerificationResult(
            status="verifying",
            source_name=discovery_name,
            title=submitted_url,
            published_at="",
            summary="",
            notes=f"{discovery_name} e apenas fonte de descoberta. Nao consegui ler links originais: {exc}",
            verified_url=submitted_url,
        )

    rejected_notes: list[str] = []
    for source_url in extract_credible_links(body, submitted_url):
        candidate_result = verify_url(source_url)
        if candidate_result.status == "verified":
            return _with_notes(
                candidate_result,
                f"Fonte original encontrada dentro de {discovery_name}. Link de descoberta: {submitted_url}",
            )
        rejected_notes.append(f"{source_url}: {candidate_result.status} - {candidate_result.notes}")

    detail = f"{discovery_name} e apenas fonte de descoberta; nao encontrei fonte original valida no artigo."
    if rejected_notes:
        detail += " Links avaliados: " + " | ".join(rejected_notes[:4])
    return VerificationResult(
        status="verifying",
        source_name=discovery_name,
        title=submitted_url,
        published_at="",
        summary="",
        notes=detail,
        verified_url=submitted_url,
    )


def resolve_submitted_link(
    submitted_url: str,
    *,
    thought: str = "",
    provider: GeminiGroundedSearchProvider | None = None,
) -> VerificationResult:
    """Resolve any submitted link to a credible source when possible.

    Direct credible links can pass immediately. Social/secondary links trigger a
    grounded Gemini search; candidates still have to pass local domain + date
    verification before reaching Verified Selection.
    """

    discovery_result: VerificationResult | None = None
    if discovery_source_name(submitted_url):
        discovery_result = resolve_discovery_link(submitted_url)
        if discovery_result.status == "verified":
            return discovery_result

    direct = verify_url(submitted_url)
    if direct.status == "verified":
        return direct

    provider = provider or GeminiGroundedSearchProvider()
    if not provider.available:
        if discovery_result is not None:
            return _with_notes(
                discovery_result,
                "Fallback Gemini Scout nao executado: configura GEMINI_API_KEY para procurar fontes originais.",
            )
        return _with_notes(
            direct,
            "Pesquisa de fonte credível não executada: configura GEMINI_API_KEY para activar Gemini Scout.",
        )

    page_title, page_summary = _metadata_for_query(submitted_url)
    try:
        candidates = provider.search_for_link(
            submitted_url=submitted_url,
            page_title=page_title or direct.title,
            page_summary=page_summary or direct.summary,
            thought=thought,
        )
    except Exception as exc:  # noqa: BLE001 - keep the user's link visible in Verifying.
        return _with_notes(direct, f"Pesquisa Gemini falhou: {exc}")

    rejected_notes: list[str] = []
    for candidate in candidates:
        candidate_result = verify_search_candidate(candidate)
        if candidate_result.status == "verified":
            return _with_notes(
                candidate_result,
                f"Fonte credível encontrada via Gemini Scout. Link submetido: {submitted_url}",
            )
        rejected_notes.append(
            f"{candidate.source_name or candidate.url}: {candidate_result.status} - {candidate_result.notes}"
        )

    detail = "Sem candidatos devolvidos pelo Gemini Scout."
    if rejected_notes:
        detail = "Candidatos avaliados sem passar validação: " + " | ".join(rejected_notes[:4])
    return _with_notes(direct, detail)


def verify_search_candidate(candidate: SearchCandidate) -> VerificationResult:
    if not candidate.url:
        return VerificationResult(
            status="verifying",
            source_name=candidate.source_name or "Unverified",
            title=candidate.title,
            published_at=candidate.published_at,
            summary=candidate.summary,
            notes="Candidato sem URL verificável.",
        )
    if is_blocked_source_url(candidate.url):
        return VerificationResult(
            status="rejected",
            source_name=candidate.source_name or "Unverified",
            title=candidate.title,
            published_at=candidate.published_at,
            summary=candidate.summary,
            notes="URL de redirect/grounding rejeitado. O PTIA precisa da fonte original, nao de um link intermediario.",
            verified_url=candidate.url,
        )
    result = verify_url(candidate.url)
    if result.status == "verified":
        title = result.title
        if re.match(r"^https?://", title or "", flags=re.IGNORECASE):
            title = candidate.title or title
        return VerificationResult(
            status=result.status,
            source_name=result.source_name,
            title=title,
            published_at=result.published_at,
            summary=result.summary or candidate.summary,
            notes=result.notes,
            verified_url=result.verified_url,
        )
    if credible_source_name(candidate.url) and candidate.published_at:
        try:
            ensure_recent_signal(candidate.published_at)
        except ValueError:
            return result
        return VerificationResult(
            status="verified",
            source_name=credible_source_name(candidate.url),
            title=candidate.title or result.title,
            published_at=candidate.published_at,
            summary=candidate.summary or result.summary,
            notes=(
                "Fonte credível encontrada via Gemini Scout. Data veio da resposta grounded; "
                "confirmar manualmente se a página não expõe metadata."
            ),
            verified_url=candidate.url,
        )
    return result

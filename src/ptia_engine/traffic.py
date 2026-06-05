from __future__ import annotations

"""traffic.py

Camada minima de analytics para o site estatico ptia.pt.

Responsabilidades:
- Gerar o snippet HTML do provider de analytics configurado (Plausible por default).
- Injetar o snippet em ficheiros HTML estaticos existentes (operacao idempotente).
- Listar paginas rastraveis do site.
- Validar se o analytics esta instalado nos HTMLs.

Nenhuma chamada a APIs externas e feita aqui. Tudo read/write local.
"""

import os
from pathlib import Path
from typing import NamedTuple


# ---------------------------------------------------------------------------
# Configuracao via ambiente (reversivel, sem hardcode de vendor)
# ---------------------------------------------------------------------------

ANALYTICS_PROVIDER = os.getenv("PTIA_ANALYTICS_PROVIDER", "plausible")
ANALYTICS_DOMAIN = os.getenv("PTIA_ANALYTICS_DOMAIN", "ptia.pt")

_SNIPPET_MARKER = "<!-- ptia-analytics -->"
_SNIPPET_MARKER_END = "<!-- /ptia-analytics -->"


def build_analytics_snippet(
    provider: str = ANALYTICS_PROVIDER,
    domain: str = ANALYTICS_DOMAIN,
) -> str:
    """Devolve o bloco HTML de analytics para o provider indicado.

    Suporta: plausible (default), none (desativa).
    """
    if provider == "none" or not provider:
        return ""
    if provider == "plausible":
        return (
            _SNIPPET_MARKER + "\n"
            + '<script defer data-domain="' + domain + '" '
            + 'src="https://plausible.io/js/script.tagged-events.js"></script>\n'
            + _SNIPPET_MARKER_END
        )
    raise ValueError(f"Provider de analytics nao suportado: {provider!r}")


def snippet_already_present(html: str) -> bool:
    """Devolve True se o snippet ja foi injetado no HTML."""
    return _SNIPPET_MARKER in html


def inject_snippet_into_html(html: str, snippet: str) -> str:
    """Injeta o snippet antes de </head>. Operacao idempotente."""
    if not snippet:
        return html
    if snippet_already_present(html):
        return html
    return html.replace("</head>", snippet + "\n</head>", 1)


def inject_snippet_into_file(path: Path, snippet: str) -> bool:
    """Le, injeta e reescreve o ficheiro HTML. Devolve True se alterado."""
    if not path.exists():
        return False
    content = path.read_text(encoding="utf-8")
    updated = inject_snippet_into_html(content, snippet)
    if updated == content:
        return False
    path.write_text(updated, encoding="utf-8")
    return True


# ---------------------------------------------------------------------------
# Paginas rastraveis
# ---------------------------------------------------------------------------

class TrackablePage(NamedTuple):
    path: str          # caminho relativo dentro de site/
    url: str           # URL publica
    has_analytics: bool


def list_trackable_pages(
    site_dir: Path,
    base_url: str = "https://" + ANALYTICS_DOMAIN,
) -> list:
    """Lista todos os index.html rastraveis no site estatico."""
    pages: list = []
    for html_file in sorted(site_dir.rglob("index.html")):
        rel = html_file.relative_to(site_dir)
        parts = list(rel.parts)
        if parts == ["index.html"]:
            url_path = "/"
        else:
            url_path = "/" + "/".join(parts[:-1]) + "/"
        content = html_file.read_text(encoding="utf-8")
        pages.append(TrackablePage(
            path=str(rel),
            url=base_url + url_path,
            has_analytics=snippet_already_present(content),
        ))
    return pages


# ---------------------------------------------------------------------------
# Relatorio de trafego (stub read-only)
# ---------------------------------------------------------------------------

class TrafficReport(NamedTuple):
    site_dir: str
    provider: str
    domain: str
    total_pages: int
    pages_with_analytics: int
    pages_without_analytics: int
    trackable_pages: list


def build_traffic_report(site_dir: Path) -> "TrafficReport":
    """Constroi um relatorio read-only sobre o estado do analytics no site."""
    pages = list_trackable_pages(site_dir)
    with_analytics = [p for p in pages if p.has_analytics]
    without_analytics = [p for p in pages if not p.has_analytics]
    return TrafficReport(
        site_dir=str(site_dir),
        provider=ANALYTICS_PROVIDER,
        domain=ANALYTICS_DOMAIN,
        total_pages=len(pages),
        pages_with_analytics=len(with_analytics),
        pages_without_analytics=len(without_analytics),
        trackable_pages=pages,
    )


def format_traffic_report(report: "TrafficReport") -> str:
    """Formata o relatorio para saida em texto."""
    lines = [
        "=== PTIA Traffic Analytics Report ===",
        f"Provider : {report.provider}",
        f"Domain   : {report.domain}",
        f"Site dir : {report.site_dir}",
        "",
        f"Paginas totais    : {report.total_pages}",
        f"Com analytics     : {report.pages_with_analytics}",
        f"Sem analytics     : {report.pages_without_analytics}",
        "",
    ]
    if report.pages_without_analytics > 0:
        lines.append("AVISO - Paginas SEM analytics:")
        for p in report.trackable_pages:
            if not p.has_analytics:
                lines.append(f"  {p.url}  ({p.path})")
        lines.append("")
    if report.pages_with_analytics > 0:
        lines.append("OK - Paginas COM analytics:")
        for p in report.trackable_pages:
            if p.has_analytics:
                lines.append(f"  {p.url}  ({p.path})")
        lines.append("")
    lines.append("Para ver dados reais: https://plausible.io/" + report.domain)
    return "\n".join(lines)

from __future__ import annotations

from pathlib import Path


# Keep Portuguese hosts specific. Trusting broad portal roots such as sapo.pt or
# iol.pt would also accept unrelated subdomains.
PORTUGUESE_NEWS_MEDIA_DOMAINS = {
    "24.sapo.pt": "SAPO 24",
    "abola.pt": "A Bola",
    "cmjornal.pt": "Correio da Manha",
    "cnnportugal.iol.pt": "CNN Portugal",
    "dn.pt": "Diario de Noticias",
    "eco.sapo.pt": "ECO",
    "expresso.pt": "Expresso",
    "jn.pt": "Jornal de Noticias",
    "jornaldenegocios.pt": "Jornal de Negocios",
    "jornaleconomico.sapo.pt": "Jornal Economico",
    "lusa.pt": "Lusa",
    "noticiasaominuto.com": "Noticias ao Minuto",
    "observador.pt": "Observador",
    "publico.pt": "Publico",
    "record.pt": "Record",
    "rr.pt": "Renascenca",
    "rtp.pt": "RTP Noticias",
    "sabado.pt": "Sabado",
    "sicnoticias.pt": "SIC Noticias",
    "tsf.pt": "TSF",
}


def _load_domain_rows(path: Path) -> dict[str, str]:
    domains: dict[str, str] = {}
    for row in path.read_text(encoding="utf-8").splitlines():
        if not row or row.startswith("#"):
            continue
        domain, name = row.split("\t", 1)
        domains[domain.casefold()] = name
    return domains


GLOBAL_NEWS_MEDIA_DOMAINS = _load_domain_rows(
    Path(__file__).with_name("global_news_media_domains.tsv")
)

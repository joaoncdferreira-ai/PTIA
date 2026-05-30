from __future__ import annotations

import html
import re
from pathlib import Path
from urllib.parse import urlparse

import requests


SOURCE_URL = "https://top1000.com/top-1000-news-and-media-platforms/"
OUTPUT_PATH = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "ptia_engine"
    / "global_news_media_domains.tsv"
)
ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789:/?&%=._-"
PASSWORD = "31"
ROW_PATTERN = re.compile(
    r'<tr id="[^"]+">.*?'
    r'<td><a href="[^"]+" target="_blank">(?P<name>.*?)</a></td>'
    r"<td>(?P<country>.*?)</td>"
    r'<td><a href="#" class="protected-link" data-code="(?P<code>[^"]+)".*?</td>'
    r"<td>(?P<index>\d+)</td></tr>",
    flags=re.DOTALL,
)


def decode_protected_url(code: str) -> str:
    decoded: list[str] = []
    size = len(ALPHABET)
    for index, char in enumerate(code):
        alphabet_index = ALPHABET.find(char)
        if alphabet_index < 0:
            decoded.append(char)
            continue
        shift = ALPHABET.index(PASSWORD[index % len(PASSWORD)])
        decoded.append(ALPHABET[(alphabet_index - shift + size) % size])
    return "".join(decoded)


def domain_for_homepage(url: str) -> str:
    host = urlparse(url).netloc.casefold()
    return host.removeprefix("www.")


def fetch_global_domains() -> dict[str, str]:
    response = requests.get(
        SOURCE_URL,
        headers={"User-Agent": "PTIA domain refresh (+local editorial verification)"},
        timeout=30,
    )
    response.raise_for_status()

    domains: dict[str, str] = {}
    for match in ROW_PATTERN.finditer(response.text):
        domain = domain_for_homepage(decode_protected_url(match.group("code")))
        name = html.unescape(re.sub(r"<[^>]+>", "", match.group("name"))).strip()
        if domain and name:
            domains.setdefault(domain, name)
    return domains


def write_global_domains(domains: dict[str, str]) -> None:
    rows = [
        "# Source: Top1000 News & Media Platforms Worldwide",
        f"# Refresh URL: {SOURCE_URL}",
        "# Format: domain<TAB>platform name",
    ]
    rows.extend(f"{domain}\t{name}" for domain, name in domains.items())
    OUTPUT_PATH.write_text("\n".join(rows) + "\n", encoding="utf-8")


if __name__ == "__main__":
    fetched_domains = fetch_global_domains()
    if len(fetched_domains) < 995:
        raise RuntimeError(f"Top1000 refresh returned only {len(fetched_domains)} domains.")
    write_global_domains(fetched_domains)
    print(f"Wrote {len(fetched_domains)} global news media domains to {OUTPUT_PATH}")

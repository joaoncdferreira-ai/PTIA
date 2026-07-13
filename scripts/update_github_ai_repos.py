from __future__ import annotations

import json
import math
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "site" / "assets" / "github-ai-repos.json"


@dataclass(slots=True)
class RepoCandidate:
    full_name: str
    description: str
    html_url: str
    stars: int
    forks: int
    language: str
    updated_at: str
    topics: list[str]
    source_query: str

    @property
    def score(self) -> float:
        updated = _parse_datetime(self.updated_at)
        days_since_update = max(0, (datetime.now(timezone.utc) - updated).days) if updated else 365
        freshness = max(0, 30 - days_since_update) * 120
        topic_bonus = sum(
            450
            for topic in self.topics
            if topic
            in {
                "artificial-intelligence",
                "generative-ai",
                "large-language-models",
                "llm",
                "ai-agents",
                "rag",
            }
        )
        return math.log10(max(self.stars, 1)) * 2500 + self.forks * 0.25 + freshness + topic_bonus

    def to_record(self, rank: int) -> dict:
        return {
            "rank": rank,
            "name": self.full_name,
            "description": self.description,
            "url": self.html_url,
            "stars": self.stars,
            "forks": self.forks,
            "language": self.language,
            "updated_at": self.updated_at,
            "topics": self.topics[:8],
            "source_query": self.source_query,
            "score": round(self.score, 2),
        }


def _parse_datetime(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _github_get(path: str, params: dict[str, str]) -> dict:
    url = f"https://api.github.com{path}?{urlencode(params)}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "PTIA-Editorial-Radar",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    github_token = os.environ.get("GITHUB_TOKEN")
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"
    request = Request(url, headers=headers)
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _search_repos(query: str) -> list[RepoCandidate]:
    payload = _github_get(
        "/search/repositories",
        {
            "q": query,
            "sort": "stars",
            "order": "desc",
            "per_page": "25",
        },
    )
    repos = []
    for item in payload.get("items", []):
        repos.append(
            RepoCandidate(
                full_name=str(item.get("full_name", "")),
                description=str(item.get("description") or ""),
                html_url=str(item.get("html_url", "")),
                stars=int(item.get("stargazers_count") or 0),
                forks=int(item.get("forks_count") or 0),
                language=str(item.get("language") or ""),
                updated_at=str(item.get("updated_at") or ""),
                topics=[str(topic) for topic in item.get("topics", [])],
                source_query=query,
            )
        )
    return repos


def fetch_top_ai_repos() -> dict:
    recent_cutoff = (datetime.now(timezone.utc) - timedelta(days=45)).date().isoformat()
    queries = [
        f"topic:artificial-intelligence stars:>1000 pushed:>={recent_cutoff}",
        f"topic:large-language-models stars:>500 pushed:>={recent_cutoff}",
        f"topic:generative-ai stars:>500 pushed:>={recent_cutoff}",
        f"topic:llm stars:>500 pushed:>={recent_cutoff}",
        f"topic:ai-agents stars:>200 pushed:>={recent_cutoff}",
        f"topic:rag stars:>200 pushed:>={recent_cutoff}",
    ]
    by_name: dict[str, RepoCandidate] = {}
    errors = []
    for query in queries:
        try:
            for repo in _search_repos(query):
                if not repo.full_name or not repo.html_url:
                    continue
                existing = by_name.get(repo.full_name)
                if not existing or repo.score > existing.score:
                    by_name[repo.full_name] = repo
        except Exception as exc:  # noqa: BLE001 - keep partial results useful.
            errors.append({"query": query, "error": str(exc)})

    top = sorted(by_name.values(), key=lambda repo: repo.score, reverse=True)[:10]
    return {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "method": "GitHub Search API: AI/LLM topics, stars, forks and activity in the last 45 days.",
        "repos": [repo.to_record(index + 1) for index, repo in enumerate(top)],
        "errors": errors,
    }


def main() -> int:
    payload = fetch_top_ai_repos()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(payload['repos'])} repos to {OUTPUT_PATH}")
    if payload["errors"]:
        print(json.dumps(payload["errors"], ensure_ascii=False, indent=2), file=sys.stderr)
    return 0 if payload["repos"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

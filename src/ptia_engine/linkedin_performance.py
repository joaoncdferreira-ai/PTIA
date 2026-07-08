from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from rapidfuzz import fuzz

from ptia_engine.dedupe import stable_hash
from ptia_engine.models import ContentPerformance, FinalPost, utc_now_iso
from ptia_engine.performance_import import _upsert_performance
from ptia_engine.storage import load_final_posts


@dataclass(frozen=True, slots=True)
class LinkedInExportRow:
    title: str
    url: str
    published_at: str
    impressions: int
    clicks: int
    likes: int
    comments: int
    shares: int
    followers_gained: int


@dataclass(frozen=True, slots=True)
class LinkedInImportResult:
    imported: int
    matched: int
    unmatched: int
    records: list[ContentPerformance]
    unmatched_titles: list[str]


@dataclass(frozen=True, slots=True)
class LinkedInAutoImportResult:
    status: str
    export_path: str
    imported: int = 0
    matched: int = 0
    unmatched: int = 0
    message: str = ""


def _normalise(value: str) -> str:
    plain = unicodedata.normalize("NFKD", value or "")
    plain = "".join(char for char in plain if not unicodedata.combining(char))
    plain = re.sub(r"https?://\S+", " ", plain.casefold())
    return " ".join(re.findall(r"[\w.-]+", plain))


def _integer(value) -> int:
    if value in {"", None}:
        return 0
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _iso_date(value, *, datemode: int = 0) -> str:
    if isinstance(value, (int, float)) and value:
        import xlrd

        parsed = xlrd.xldate_as_datetime(value, datemode)
    else:
        text = str(value or "").strip()
        parsed = None
        for pattern in ("%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(text, pattern)
                break
            except ValueError:
                continue
        if parsed is None:
            return text
    return parsed.replace(tzinfo=timezone.utc).isoformat()


def _read_linkedin_rows(path: Path) -> list[LinkedInExportRow]:
    import xlrd

    workbook = xlrd.open_workbook(str(path))
    sheet = workbook.sheet_by_name("Todas as publicações")
    headers = {
        _normalise(str(sheet.cell_value(1, column))): column
        for column in range(sheet.ncols)
    }

    def value(row: int, header: str):
        column = headers.get(_normalise(header))
        return sheet.cell_value(row, column) if column is not None else ""

    rows: list[LinkedInExportRow] = []
    for row in range(2, sheet.nrows):
        title = str(value(row, "Título da publicação") or "").strip()
        url = str(value(row, "Link da publicação") or "").strip()
        if not title and not url:
            continue
        rows.append(
            LinkedInExportRow(
                title=title,
                url=url,
                published_at=_iso_date(value(row, "Criação"), datemode=workbook.datemode),
                impressions=_integer(value(row, "Impressões")),
                clicks=_integer(value(row, "Cliques")),
                likes=_integer(value(row, "Gostaram")),
                comments=_integer(value(row, "Comentários")),
                shares=_integer(value(row, "Compartilhamentos")),
                followers_gained=_integer(value(row, "Seguidores")),
            )
        )
    return rows


def match_linkedin_post(
    row: LinkedInExportRow,
    final_posts: list[FinalPost],
    *,
    threshold: float = 76.0,
) -> FinalPost | None:
    candidates = [post for post in final_posts if post.channel == "linkedin"]
    for post in candidates:
        if row.url and row.url == post.published_url:
            return post

    exported = _normalise(row.title)
    if not exported:
        return None
    ranked = []
    for post in candidates:
        post_text = _normalise(f"{post.title} {post.body}")
        if not post_text:
            continue
        prefix_score = fuzz.ratio(exported[:240], post_text[:240])
        token_score = fuzz.token_set_ratio(exported, post_text)
        ranked.append((max(prefix_score, token_score), post))
    if not ranked:
        return None
    score, post = max(ranked, key=lambda item: item[0])
    return post if score >= threshold else None


def import_linkedin_export(
    *,
    export_path: Path,
    final_posts_path: Path,
    performance_path: Path,
    match_threshold: float = 76.0,
) -> LinkedInImportResult:
    rows = _read_linkedin_rows(export_path)
    final_posts = load_final_posts(final_posts_path)
    records: list[ContentPerformance] = []
    unmatched_titles: list[str] = []
    matched = 0

    for row in rows:
        post = match_linkedin_post(row, final_posts, threshold=match_threshold)
        if post:
            matched += 1
        else:
            unmatched_titles.append(row.title[:160])
        stable_key = row.url or f"{row.published_at}:{row.title}"
        record = ContentPerformance(
            performance_id=f"linkedin_{stable_hash(stable_key, 18)}",
            draft_id=post.post_id if post else "",
            post_id=post.post_id if post else row.url,
            channel="linkedin",
            published_at=row.published_at,
            topic=post.title if post else row.title[:160],
            section="LinkedIn",
            impressions=row.impressions,
            likes=row.likes,
            comments=row.comments,
            shares=row.shares,
            clicks=row.clicks,
            followers_gained=row.followers_gained,
            page_url=row.url,
            notes=(
                f"LinkedIn export; match={'yes' if post else 'no'}; "
                f"source_title={row.title[:240]}"
            ),
            created_at=utc_now_iso(),
        )
        records.append(_upsert_performance(performance_path, record))

    return LinkedInImportResult(
        imported=len(records),
        matched=matched,
        unmatched=len(records) - matched,
        records=records,
        unmatched_titles=unmatched_titles,
    )


def _candidate_export_paths(export_dir: Path, *, max_age_days: int = 14) -> list[Path]:
    if not export_dir.exists() or not export_dir.is_dir():
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    candidates: list[Path] = []
    for path in export_dir.glob("*.xls"):
        if not path.is_file():
            continue
        try:
            modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        except OSError:
            continue
        if modified < cutoff:
            continue
        candidates.append(path)
    return sorted(candidates, key=lambda item: item.stat().st_mtime, reverse=True)


def _is_linkedin_export(path: Path) -> bool:
    try:
        _read_linkedin_rows(path)
    except Exception:
        return False
    return True


def find_latest_linkedin_export(
    *,
    export_path: Path | None = None,
    export_dir: Path | None = None,
    max_age_days: int = 14,
) -> Path | None:
    if export_path:
        return export_path if export_path.exists() and export_path.is_file() and _is_linkedin_export(export_path) else None
    if export_dir is None:
        export_dir = Path.home() / "Downloads"
    for candidate in _candidate_export_paths(export_dir, max_age_days=max_age_days):
        if _is_linkedin_export(candidate):
            return candidate
    return None


def import_latest_linkedin_export(
    *,
    final_posts_path: Path,
    performance_path: Path,
    export_path: Path | None = None,
    export_dir: Path | None = None,
    max_age_days: int = 14,
    match_threshold: float = 76.0,
) -> LinkedInAutoImportResult:
    selected = find_latest_linkedin_export(
        export_path=export_path,
        export_dir=export_dir,
        max_age_days=max_age_days,
    )
    if selected is None:
        location = str(export_path or export_dir or (Path.home() / "Downloads"))
        return LinkedInAutoImportResult(
            status="skipped",
            export_path="",
            message=f"No recent LinkedIn analytics .xls export found in {location}.",
        )
    result = import_linkedin_export(
        export_path=selected,
        final_posts_path=final_posts_path,
        performance_path=performance_path,
        match_threshold=match_threshold,
    )
    return LinkedInAutoImportResult(
        status="imported",
        export_path=str(selected),
        imported=result.imported,
        matched=result.matched,
        unmatched=result.unmatched,
        message=f"Imported LinkedIn analytics from {selected.name}: {result.matched}/{result.imported} matched.",
    )


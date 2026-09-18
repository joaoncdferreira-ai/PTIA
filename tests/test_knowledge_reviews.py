import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ptia_engine.knowledge import (
    KnowledgeValidationError,
    build_knowledge_payload,
    render_methodology_page,
    render_resources_page,
    render_tools_page,
    validate_catalog,
)
from ptia_engine.knowledge_reviews import build_tool_reviews, tool_review_note

ROOT = Path(__file__).resolve().parents[1]


def load_catalog():
    catalog = json.loads((ROOT / "config/ptia_knowledge.json").read_text(encoding="utf-8"))
    directory = json.loads((ROOT / "site/assets/quem-e-quem.json").read_text(encoding="utf-8"))
    return catalog, directory


def test_generation_date_does_not_replace_editorial_review_date():
    catalog, directory = load_catalog()
    catalog = copy.deepcopy(catalog)
    catalog["tool_category_evidence"]["estudo"]["reviewed_at"] = "2026-09-18"

    payload = build_knowledge_payload(
        catalog=catalog,
        directory=directory,
        signals=[],
        now=datetime(2026, 11, 3, tzinfo=timezone.utc),
    )

    assert payload["updated_at"].startswith("2026-11-03")
    assert payload["tool_category_reviews"]["estudo"]["reviewed_at"] == "2026-09-18"
    assert payload["tool_category_reviews"]["estudo"]["status"] == "due"
    assert "Revisão em falta" in render_tools_page(payload)
    assert "Revisão em falta" in render_resources_page(payload)


@pytest.mark.parametrize("reviewed_at", ["2026-02-30", "18/09/2026", "20260918"])
def test_rejects_malformed_category_review_date(reviewed_at):
    catalog, directory = load_catalog()
    catalog["tool_category_evidence"]["estudo"]["reviewed_at"] = reviewed_at

    with pytest.raises(KnowledgeValidationError, match="revisão"):
        validate_catalog(catalog, directory)


def test_catalog_records_a_review_for_all_nine_categories_and_removes_sora():
    catalog, directory = load_catalog()
    validate_catalog(catalog, directory)
    reviews = build_tool_reviews(
        catalog["tool_category_evidence"], now=datetime(2026, 9, 18, tzinfo=timezone.utc)
    )

    assert len(reviews) == 9
    assert all(review["reviewed_at"] for review in reviews.values())
    assert "sora" not in {tool["id"] for tool in catalog["tools"]}
    for assessment in catalog["tool_category_evidence"].values():
        assert all("sora" not in source["ranking"] for source in assessment["components"].values())


def test_missing_review_date_is_not_inferred_from_generation_date():
    reviews = build_tool_reviews({"coding": {}}, now=datetime(2026, 9, 18, tzinfo=timezone.utc))

    assert reviews["coding"]["reviewed_at"] == ""
    assert reviews["coding"]["status"] == "missing"
    assert "a data de geração não é uma revisão" in tool_review_note(
        {"tool_category_reviews": reviews}, "coding"
    )


@pytest.mark.parametrize("day,status", [(2, "current"), (3, "due")])
def test_flags_reviews_only_after_the_45_day_boundary(day, status):
    reviews = build_tool_reviews(
        {"coding": {"reviewed_at": "2026-09-18"}},
        now=datetime(2026, 11, day, tzinfo=timezone.utc),
    )

    assert reviews["coding"]["status"] == status


def test_preserves_the_period_of_historical_adoption_data():
    reviews = build_tool_reviews(
        {
            "imagem": {
                "reviewed_at": "2026-09-18",
                "components": {"popularity": {"data_period": "janeiro de 2026"}},
            }
        },
        now=datetime(2026, 9, 18, tzinfo=timezone.utc),
    )

    note = tool_review_note({"tool_category_reviews": reviews}, "imagem")
    assert "18/09/2026" in note
    assert "janeiro de 2026 (contexto histórico, não uso atual)" in note


def test_does_not_treat_a_future_review_date_as_current():
    reviews = build_tool_reviews(
        {"coding": {"reviewed_at": "2026-09-19"}},
        now=datetime(2026, 9, 18, tzinfo=timezone.utc),
    )

    assert reviews["coding"]["status"] == "future"
    assert "Data de revisão posterior" in tool_review_note(
        {"tool_category_reviews": reviews}, "coding"
    )


def test_methodology_uses_the_current_catalog_sources():
    catalog, directory = load_catalog()
    payload = build_knowledge_payload(
        catalog=catalog,
        directory=directory,
        signals=[],
        now=datetime(2026, 9, 18, tzinfo=timezone.utc),
    )

    page = render_methodology_page(payload)
    for source in catalog["tool_methodology_sources"]:
        assert source["url"] in page
        assert source["label"] in page
    assert "vellum.ai/llm-leaderboard" not in page
    assert "não prova adoção atual" in page

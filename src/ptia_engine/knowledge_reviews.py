"""Keep editorial review dates separate from page generation dates."""

import re
from datetime import date, datetime

TOOL_REVIEW_MAX_AGE_DAYS = 45


def parse_review_date(value: str) -> date:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("Review date must use YYYY-MM-DD.")
    return date.fromisoformat(value)


def build_tool_reviews(assessments: dict, *, now: datetime) -> dict:
    reviews = {}
    for category, assessment in assessments.items():
        reviewed_at = str(assessment.get("reviewed_at") or "")
        reviewed_date = parse_review_date(reviewed_at) if reviewed_at else None
        age_days = (now.date() - reviewed_date).days if reviewed_date else None
        status = (
            "missing"
            if age_days is None
            else "future"
            if age_days < 0
            else "due"
            if age_days > TOOL_REVIEW_MAX_AGE_DAYS
            else "current"
        )
        reviews[category] = {
            "reviewed_at": reviewed_at,
            "status": status,
            "note": str(assessment.get("review_note") or ""),
            "adoption_data_period": str(
                assessment.get("components", {}).get("popularity", {}).get("data_period") or ""
            ),
        }
    return reviews


def tool_review_note(payload: dict, category: str) -> str:
    review = payload.get("tool_category_reviews", {}).get(category, {})
    reviewed_at = str(review.get("reviewed_at") or "")
    if not reviewed_at:
        return "Revisão completa ainda não registada; a data de geração não é uma revisão."
    reviewed_date = parse_review_date(reviewed_at).strftime("%d/%m/%Y")
    parts = [f"Revisão editorial: {reviewed_date}."]
    if review.get("status") == "due":
        parts.append("Revisão em falta: esta avaliação tem mais de 45 dias.")
    if review.get("status") == "future":
        parts.append("Data de revisão posterior a esta edição; confirmar antes de a tratar como atual.")
    if review.get("note"):
        parts.append(str(review["note"]))
    if review.get("adoption_data_period"):
        parts.append(f"Tráfego: {review['adoption_data_period']} (contexto histórico, não uso atual).")
    return " ".join(parts)

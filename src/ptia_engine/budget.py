from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from ptia_engine.models import utc_now_iso


MODEL_PRICES_USD_PER_1M = {
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
    "gpt-4.1-nano": {"input": 0.10, "output": 0.40},
}


@dataclass(slots=True)
class UsageRecord:
    created_at: str
    model: str
    operation: str
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    article_id: str = ""

    def to_record(self) -> dict:
        return asdict(self)


def estimate_tokens(text: str) -> int:
    # Cheap conservative estimate for English/Portuguese text.
    return max(1, len(text) // 4)


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    prices = MODEL_PRICES_USD_PER_1M.get(model, MODEL_PRICES_USD_PER_1M["gpt-4.1-mini"])
    return (input_tokens / 1_000_000 * prices["input"]) + (
        output_tokens / 1_000_000 * prices["output"]
    )


def current_month_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def load_monthly_spend_usd(ledger_path: Path, month_key: str | None = None) -> float:
    month_key = month_key or current_month_key()
    if not ledger_path.exists():
        return 0.0
    total = 0.0
    with ledger_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if str(record.get("created_at", "")).startswith(month_key):
                total += float(record.get("estimated_cost_usd", 0.0))
    return total


def append_usage(ledger_path: Path, record: UsageRecord) -> None:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record.to_record(), ensure_ascii=False) + "\n")


def make_usage_record(
    model: str,
    operation: str,
    input_tokens: int,
    output_tokens: int,
    article_id: str = "",
) -> UsageRecord:
    return UsageRecord(
        created_at=utc_now_iso(),
        model=model,
        operation=operation,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=estimate_cost_usd(model, input_tokens, output_tokens),
        article_id=article_id,
    )

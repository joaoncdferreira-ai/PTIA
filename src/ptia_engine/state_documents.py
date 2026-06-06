from __future__ import annotations

import base64
import hashlib


STATE_CHUNK_BYTES = 500_000


def content_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def encode_content_chunks(content: str, *, chunk_bytes: int = STATE_CHUNK_BYTES) -> list[str]:
    raw = content.encode("utf-8")
    if not raw:
        return [""]
    return [
        base64.b64encode(raw[offset : offset + chunk_bytes]).decode("ascii")
        for offset in range(0, len(raw), chunk_bytes)
    ]


def decode_content_chunks(chunks: list[str]) -> str:
    raw = b"".join(base64.b64decode(chunk.encode("ascii")) for chunk in chunks if chunk)
    return raw.decode("utf-8")

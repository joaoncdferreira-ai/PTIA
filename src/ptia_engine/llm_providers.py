from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from typing import Any

from ptia_engine.budget import estimate_cost_usd, estimate_tokens


OPENAI_DEFAULT_MODEL = "gpt-4.1-mini"
GEMINI_DEFAULT_MODEL = "gemini-flash-latest"
OLLAMA_DEFAULT_MODEL = "llama3.1"
OLLAMA_DEFAULT_BASE_URL = "http://127.0.0.1:11434"


@dataclass(slots=True)
class LLMJsonResult:
    payload: dict[str, Any]
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float


def normalize_provider(provider: str) -> str:
    value = provider.strip().casefold()
    if value == "local":
        return "ollama"
    if value not in {"template", "openai", "gemini", "ollama"}:
        raise ValueError(f"Unsupported LLM provider: {provider}")
    return value


def default_model_for_provider(provider: str) -> str:
    provider = normalize_provider(provider)
    if provider == "template":
        return "template"
    if provider == "openai":
        return os.getenv("OPENAI_MODEL", OPENAI_DEFAULT_MODEL)
    if provider == "gemini":
        return os.getenv("GEMINI_MODEL", GEMINI_DEFAULT_MODEL)
    return os.getenv("OLLAMA_MODEL", OLLAMA_DEFAULT_MODEL)


def estimate_provider_cost_usd(
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> float:
    provider = normalize_provider(provider)
    if provider != "openai":
        return 0.0
    return estimate_cost_usd(model, input_tokens, output_tokens)


def generate_json(
    *,
    provider: str,
    prompt: str,
    schema: dict[str, Any],
    model: str | None = None,
    max_output_tokens: int = 1800,
    temperature: float = 0.3,
    system_message: str = "Responde apenas em JSON valido.",
) -> LLMJsonResult:
    provider = normalize_provider(provider)
    model = model or default_model_for_provider(provider)
    if provider == "openai":
        return _generate_openai_json(
            prompt=prompt,
            schema=schema,
            model=model,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            system_message=system_message,
        )
    if provider == "gemini":
        return _generate_gemini_json(
            prompt=prompt,
            model=model,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            system_message=system_message,
        )
    return _generate_ollama_json(
        prompt=prompt,
        model=model,
        max_output_tokens=max_output_tokens,
        temperature=temperature,
        system_message=system_message,
    )


def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def parse_json_text(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    return json.loads(cleaned)


def _generate_openai_json(
    *,
    prompt: str,
    schema: dict[str, Any],
    model: str,
    max_output_tokens: int,
    temperature: float,
    system_message: str,
) -> LLMJsonResult:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")

    request_payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_message},
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_schema", "json_schema": schema},
        "max_tokens": max_output_tokens,
        "temperature": temperature,
    }
    response_body = _post_json(
        "https://api.openai.com/v1/chat/completions",
        request_payload,
        {"Authorization": f"Bearer {api_key}"},
        timeout=90,
    )
    text = response_body["choices"][0]["message"]["content"]
    usage = response_body.get("usage", {})
    input_tokens = int(usage.get("prompt_tokens", estimate_tokens(prompt)))
    output_tokens = int(usage.get("completion_tokens", estimate_tokens(text)))
    return LLMJsonResult(
        payload=parse_json_text(text),
        provider="openai",
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=estimate_cost_usd(model, input_tokens, output_tokens),
    )


def _generate_gemini_json(
    *,
    prompt: str,
    model: str,
    max_output_tokens: int,
    temperature: float,
    system_message: str,
) -> LLMJsonResult:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set.")

    request_payload = {
        "systemInstruction": {"parts": [{"text": system_message}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_output_tokens,
            "responseMimeType": "application/json",
        },
    }
    response_body = _post_json(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        request_payload,
        {"x-goog-api-key": api_key},
        timeout=90,
    )
    parts = response_body["candidates"][0]["content"]["parts"]
    text = "".join(str(part.get("text", "")) for part in parts)
    usage = response_body.get("usageMetadata", {})
    input_tokens = int(usage.get("promptTokenCount", estimate_tokens(prompt)))
    output_tokens = int(usage.get("candidatesTokenCount", estimate_tokens(text)))
    return LLMJsonResult(
        payload=parse_json_text(text),
        provider="gemini",
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=0.0,
    )


def _generate_ollama_json(
    *,
    prompt: str,
    model: str,
    max_output_tokens: int,
    temperature: float,
    system_message: str,
) -> LLMJsonResult:
    base_url = os.getenv("OLLAMA_BASE_URL", OLLAMA_DEFAULT_BASE_URL).rstrip("/")
    request_payload = {
        "model": model,
        "system": system_message,
        "prompt": prompt,
        "format": "json",
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_output_tokens,
        },
    }
    response_body = _post_json(
        f"{base_url}/api/generate",
        request_payload,
        {},
        timeout=180,
    )
    text = str(response_body.get("response", ""))
    return LLMJsonResult(
        payload=parse_json_text(text),
        provider="ollama",
        model=model,
        input_tokens=int(response_body.get("prompt_eval_count", estimate_tokens(prompt))),
        output_tokens=int(response_body.get("eval_count", estimate_tokens(text))),
        estimated_cost_usd=0.0,
    )

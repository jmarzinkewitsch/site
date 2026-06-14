"""Tiny Anthropic Messages API client for optional M7 recommendation copy."""
from __future__ import annotations

import json

import httpx

from config import ServiceConfig
from models import RecommendationItem

DEFAULT_BASE_URL = "https://api.anthropic.com"
DEFAULT_MODEL = "claude-3-5-haiku-20241022"


class AnthropicError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class AnthropicService:
    def __init__(self, cfg: ServiceConfig, client: httpx.AsyncClient) -> None:
        self._key = cfg.api_key
        self._base = (cfg.base_url or DEFAULT_BASE_URL).rstrip("/")
        self._client = client

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self._key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

    async def _message(self, prompt: str, max_tokens: int = 900) -> str:
        try:
            response = await self._client.post(
                f"{self._base}/v1/messages",
                headers=self._headers(),
                json={
                    "model": DEFAULT_MODEL,
                    "max_tokens": max_tokens,
                    "temperature": 0.2,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
        except httpx.HTTPError as exc:
            raise AnthropicError(f"Anthropic nicht erreichbar: {exc}") from exc
        if response.status_code >= 400:
            raise AnthropicError(f"Anthropic {response.status_code}", response.status_code)
        data = response.json()
        chunks = data.get("content", []) if isinstance(data, dict) else []
        return "\n".join(c.get("text", "") for c in chunks if isinstance(c, dict) and c.get("type") == "text")

    async def improve(self, items: list[RecommendationItem], taste_titles: list[str]) -> list[RecommendationItem]:
        """Return the same real candidates, optionally reordered and reworded by Claude.

        Claude is constrained to known ids; malformed/partial responses simply keep
        algorithmic ordering/reasons for the affected items.
        """
        if not items:
            return items
        payload = [
            {"id": item.id, "title": item.title, "type": item.type, "reason": item.reason, "score": item.score}
            for item in items
        ]
        prompt = (
            "Du verbesserst Empfehlungen für eine private Mediathek. "
            "Nutze ausschließlich die Kandidaten-IDs aus JSON, erfinde keine Titel. "
            "Antworte nur als JSON-Array mit Objekten: id, reason. "
            "Die reasons sind kurze deutsche Begründungen (max. 22 Wörter).\n"
            f"Lieblingstitel: {', '.join(taste_titles[:8]) or 'unbekannt'}\n"
            f"Kandidaten: {json.dumps(payload, ensure_ascii=False)}"
        )
        text = await self._message(prompt)
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:
            raise AnthropicError("Anthropic lieferte kein JSON") from exc
        if not isinstance(raw, list):
            raise AnthropicError("Anthropic lieferte unerwartetes JSON")
        by_id = {item.id: item for item in items}
        improved: list[RecommendationItem] = []
        seen: set[str] = set()
        for row in raw:
            if not isinstance(row, dict):
                continue
            rid = str(row.get("id", ""))
            if rid not in by_id or rid in seen:
                continue
            item = by_id[rid].model_copy()
            if reason := row.get("reason"):
                item.reason = str(reason)
            improved.append(item)
            seen.add(rid)
        improved.extend(item for item in items if item.id not in seen)
        return improved

    async def ping(self) -> bool:
        await self._message("Antworte nur mit OK.", max_tokens=8)
        return True

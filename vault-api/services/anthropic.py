"""Tiny Anthropic Messages API client for optional M7 recommendation copy."""
from __future__ import annotations

import json
import os
import re

import httpx

from config import ServiceConfig
from models import RecommendationItem

DEFAULT_BASE_URL = "https://api.anthropic.com"
DEFAULT_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
# LLM inference routinely exceeds the shared 15s client timeout, so this client
# overrides it per request rather than letting a slow generation read as an error.
REQUEST_TIMEOUT = 60.0


def _json_array(text: str) -> list:
    """Accept strict JSON or a single JSON array wrapped in prose/code fences."""
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.IGNORECASE | re.MULTILINE).strip()
    try:
        raw = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("[")
        end = cleaned.rfind("]")
        if start < 0 or end <= start:
            raise
        raw = json.loads(cleaned[start:end + 1])
    if not isinstance(raw, list):
        raise AnthropicError("Anthropic lieferte unerwartetes JSON")
    return raw


def _json_object(text: str) -> dict:
    """Accept strict JSON or a JSON object wrapped in prose/code fences."""
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.IGNORECASE | re.MULTILINE).strip()
    try:
        raw = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            raise
        raw = json.loads(cleaned[start:end + 1])
    if not isinstance(raw, dict):
        raise AnthropicError("Anthropic lieferte unerwartetes JSON-Objekt")
    return raw



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
                timeout=REQUEST_TIMEOUT,
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
            "Die reasons sind kurze deutsche Begründungen (max. 16 Wörter), ohne direkte Anrede, ohne Sie/Ihr, ohne das Wort Lieblingstitel.\n"
            f"Lieblingstitel: {', '.join(taste_titles[:8]) or 'unbekannt'}\n"
            f"Kandidaten: {json.dumps(payload, ensure_ascii=False)}"
        )
        text = await self._message(prompt)
        try:
            raw = _json_array(text)
        except json.JSONDecodeError as exc:
            raise AnthropicError("Anthropic lieferte kein JSON") from exc
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


    async def curate_picks(
        self,
        request_summary: str,
        profiles_summary: str,
        library_candidates: list[dict],
        discover_candidates: list[dict],
        model: str | None = None,
    ) -> dict:
        """Select the best library and discover titles for the picker.

        Always uses claude-sonnet-4-6 for quality (overrides DEFAULT_MODEL).
        Returns a dict with keys library_pick, discover_pick, alternatives.
        """
        lib_compact = json.dumps(library_candidates[:30], ensure_ascii=False)
        disc_compact = json.dumps(discover_candidates[:30], ensure_ascii=False)
        json_schema = (
            '{ "library_pick": {"id": "...", "reason": "..."}, '
            '"discover_pick": {"id": "...", "reason": "..."}, '
            '"alternatives": [{"id": "...", "reason": "..."}] }'
        )
        prompt = (
            "Du bist ein Filmempfehlungs-Assistent fuer eine private Mediathek.\n"
            f"Anfrage: {request_summary}\n"
            f"Profile: {profiles_summary}\n"
            "Waehle aus den Kandidaten:\n"
            "  - genau EINEN besten LIBRARY-Titel (source=library)\n"
            "  - genau EINEN besten DISCOVER-Titel (source=discover)\n"
            "  - bis zu 6 Alternativen (Mix aus beiden Quellen)\n"
            "Fuer jeden: eine kurze deutsche Begruendung (max. 18 Woerter, keine direkte Anrede, kein Sie/Ihr).\n"
            f"Antworte NUR als striktes JSON (kein Prosa, keine Code-Fence): {json_schema}\n"
            f"Library-Kandidaten: {lib_compact}\n"
            f"Discover-Kandidaten: {disc_compact}"
        )
        used_model = model or "claude-sonnet-4-6"
        try:
            response = await self._client.post(
                f"{self._base}/v1/messages",
                headers=self._headers(),
                json={
                    "model": used_model,
                    "max_tokens": 1200,
                    "temperature": 0.3,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=REQUEST_TIMEOUT,
            )
        except httpx.HTTPError as exc:
            raise AnthropicError(f"Anthropic nicht erreichbar: {exc}") from exc
        if response.status_code >= 400:
            raise AnthropicError(f"Anthropic {response.status_code}", response.status_code)
        data = response.json()
        chunks = data.get("content", []) if isinstance(data, dict) else []
        text = "\n".join(c.get("text", "") for c in chunks if isinstance(c, dict) and c.get("type") == "text")
        try:
            return _json_object(text)
        except (json.JSONDecodeError, AnthropicError) as exc:
            raise AnthropicError("Anthropic lieferte kein valides JSON fuer den Picker") from exc

    async def ping(self) -> bool:
        await self._message("Antworte nur mit OK.", max_tokens=8)
        return True

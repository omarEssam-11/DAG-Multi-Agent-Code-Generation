"""OpenAI-compatible LLM client (chat completions + tool calls)."""
from __future__ import annotations

import json
from typing import Any

import httpx

from .config import settings


class LLLError(Exception):
    pass


class LLMClient:
    def __init__(self) -> None:
        self.base_url = settings.openai_base_url
        self.api_key = settings.openai_api_key
        self.model = settings.model

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.4,
    ) -> tuple[str, list[dict[str, Any]]]:
        """One chat-completions call. Returns (text, tool_calls)."""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            async with httpx.AsyncClient(timeout=180) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise LLLError(f"LLM request failed: {exc}") from exc

        if resp.status_code != 200:
            raise LLLError(f"LLM HTTP {resp.status_code}: {resp.text[:500]}")

        try:
            data = resp.json()
            choice = data["choices"][0]["message"]
        except (KeyError, IndexError, json.JSONDecodeError) as exc:
            raise LLLError(f"malformed LLM response: {resp.text[:500]}") from exc

        text = choice.get("content") or ""
        tool_calls = choice.get("tool_calls") or []
        return text, tool_calls

    async def complete_json(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        """Ask the model for a JSON object and parse it (with repair attempts)."""
        text, _ = await self.complete(
            messages + [{
                "role": "system",
                "content": "Respond with a single valid JSON object and nothing else.",
            }],
            temperature=0.0,
        )
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Tolerate ```json fenced blocks.
            start, end = text.find("{"), text.rfind("}")
            if start != -1 and end != -1 and end > start:
                return json.loads(text[start : end + 1])
            raise LLLError(f"model did not return valid JSON: {text[:300]}")

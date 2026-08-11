from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, cast
from urllib.parse import urlparse

import httpx

from polyglot.platform.errors import DomainError, ErrorCode


@dataclass(frozen=True, slots=True)
class ChatRequest:
    model: str
    messages: tuple[tuple[str, str], ...]
    max_output_tokens: int


@dataclass(frozen=True, slots=True)
class ChatResult:
    message: str
    input_tokens: int
    output_tokens: int


class ChatProvider(Protocol):
    code: str
    model: str

    async def complete(self, request: ChatRequest) -> ChatResult: ...


class LmStudioChatProvider:
    code = "lm_studio"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float = 120,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        parsed = urlparse(base_url)
        local_hosts = {"127.0.0.1", "localhost", "::1", "host.docker.internal"}
        if parsed.scheme != "http" or parsed.hostname not in local_hosts:
            raise ValueError("LM Studio must use a local HTTP endpoint")
        self._base_url = base_url.rstrip("/")
        self.model = model
        self._timeout = timeout_seconds
        self._client = client

    async def complete(self, request: ChatRequest) -> ChatResult:
        if request.model != self.model:
            raise DomainError(ErrorCode.PROVIDER_UNAVAILABLE, retryable=False)
        system_prompts = [content for role, content in request.messages if role == "system"]
        user_messages = [content for role, content in request.messages if role == "user"]
        if len(system_prompts) > 1 or len(user_messages) != 1 or any(
            role not in {"system", "user"} for role, _ in request.messages
        ):
            raise DomainError(ErrorCode.TOOL_SCHEMA_INVALID, retryable=False)
        payload = {
            "input": user_messages[0],
            "max_output_tokens": request.max_output_tokens,
            "model": request.model,
            "reasoning": "off",
            "store": False,
            "stream": False,
            "temperature": 0,
        }
        if system_prompts:
            payload["system_prompt"] = system_prompts[0]
        try:
            if self._client is None:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.post(f"{self._base_url}/api/v1/chat", json=payload)
            else:
                response = await self._client.post(
                    f"{self._base_url}/api/v1/chat",
                    json=payload,
                    timeout=self._timeout,
                )
        except (httpx.TimeoutException, httpx.NetworkError) as error:
            raise DomainError(ErrorCode.PROVIDER_UNAVAILABLE, retryable=False) from error
        if response.status_code != 200:
            raise DomainError(ErrorCode.PROVIDER_UNAVAILABLE, retryable=False)
        try:
            body = response.json()
        except ValueError as error:
            raise DomainError(ErrorCode.TOOL_SCHEMA_INVALID, retryable=False) from error
        if not isinstance(body, dict):
            raise DomainError(ErrorCode.TOOL_SCHEMA_INVALID, retryable=False)
        returned_model = body.get("model_instance_id")
        if returned_model != self.model:
            raise DomainError(ErrorCode.PROVIDER_UNAVAILABLE, retryable=False)
        output = body.get("output")
        if not isinstance(output, list):
            raise DomainError(ErrorCode.TOOL_SCHEMA_INVALID, retryable=False)
        messages = [
            self._message_text(item)
            for item in output
            if isinstance(item, dict) and item.get("type") == "message"
        ]
        message = "\n".join(item for item in messages if item)
        if not message:
            raise DomainError(ErrorCode.TOOL_SCHEMA_INVALID, retryable=False)
        stats = body.get("stats")
        input_tokens = self._token_count(stats, "input_tokens")
        output_tokens = self._token_count(stats, "total_output_tokens")
        return ChatResult(message, input_tokens, output_tokens)

    @staticmethod
    def _message_text(item: dict[object, object]) -> str:
        content = item.get("content")
        if isinstance(content, str):
            return content.strip()
        if not isinstance(content, list):
            return ""
        parts: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            text = block.get("text") or block.get("content")
            if isinstance(text, str):
                parts.append(text)
        return "\n".join(parts).strip()

    @staticmethod
    def _token_count(stats: object, key: str) -> int:
        if not isinstance(stats, dict):
            return 0
        value = cast(object, stats.get(key))
        valid = isinstance(value, int) and not isinstance(value, bool) and value >= 0
        return cast(int, value) if valid else 0

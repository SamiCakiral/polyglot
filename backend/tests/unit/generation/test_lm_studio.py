import json

import httpx
import pytest

from polyglot.modules.generation.providers import (
    ChatRequest,
    LmStudioChatProvider,
)
from polyglot.platform.errors import DomainError, ErrorCode


@pytest.mark.asyncio
async def test_lm_studio_uses_v1_chat_without_storage_and_ignores_reasoning() -> None:
    async def respond(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert request.url.path == "/api/v1/chat"
        assert payload == {
            "input": "task",
            "max_output_tokens": 800,
            "model": "qwen/qwen3.6-35b-a3b",
            "reasoning": "off",
            "store": False,
            "stream": False,
            "system_prompt": "system",
            "temperature": 0,
        }
        return httpx.Response(
            200,
            json={
                "model_instance_id": "qwen/qwen3.6-35b-a3b",
                "output": [
                    {"type": "reasoning", "content": "private chain"},
                    {"type": "message", "content": '{"tool_name":"catalogue.list_targets"}'},
                ],
                "stats": {"input_tokens": 42, "total_output_tokens": 17},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        result = await LmStudioChatProvider(
            base_url="http://127.0.0.1:1234",
            model="qwen/qwen3.6-35b-a3b",
            client=client,
        ).complete(
            ChatRequest(
                model="qwen/qwen3.6-35b-a3b",
                messages=(("system", "system"), ("user", "task")),
                max_output_tokens=800,
            )
        )

    assert result.message == '{"tool_name":"catalogue.list_targets"}'
    assert result.input_tokens == 42
    assert result.output_tokens == 17


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "expected"),
    (
        (
            {
                "model_instance_id": "another-model",
                "output": [{"type": "message", "content": "{}"}],
            },
            ErrorCode.PROVIDER_UNAVAILABLE,
        ),
        (
            {
                "model_instance_id": "qwen/qwen3.6-35b-a3b",
                "output": [{"type": "reasoning"}],
            },
            ErrorCode.TOOL_SCHEMA_INVALID,
        ),
    ),
)
async def test_lm_studio_rejects_model_substitution_and_missing_message(
    payload: dict[str, object], expected: ErrorCode
) -> None:
    async def respond(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        provider = LmStudioChatProvider(
            base_url="http://127.0.0.1:1234",
            model="qwen/qwen3.6-35b-a3b",
            client=client,
        )
        with pytest.raises(DomainError) as caught:
            await provider.complete(
                ChatRequest("qwen/qwen3.6-35b-a3b", (("user", "task"),), 800)
            )
    assert caught.value.code is expected


@pytest.mark.asyncio
async def test_lm_studio_failure_is_visible_and_never_retried() -> None:
    calls = 0

    async def unavailable(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, json={"error": "model not loaded"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(unavailable)) as client:
        provider = LmStudioChatProvider(
            base_url="http://127.0.0.1:1234",
            model="qwen/qwen3.6-35b-a3b",
            client=client,
        )
        with pytest.raises(DomainError) as caught:
            await provider.complete(
                ChatRequest("qwen/qwen3.6-35b-a3b", (("user", "task"),), 800)
            )
    assert caught.value.code is ErrorCode.PROVIDER_UNAVAILABLE
    assert calls == 1

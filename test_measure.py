"""Regression tests for request measurement parsing and streaming semantics."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

import src.measure as measure
from src.measure import RequestOutcome


def _data_line(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload)}"


def test_load_request_payload_requires_streaming_request(tmp_path: Path) -> None:
    request_file = tmp_path / "request.json"
    request_file.write_text(
        json.dumps(
            {
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 8,
                "temperature": 0.0,
                "stream": True,
            }
        ),
        encoding="utf-8",
    )

    payload = measure.load_request_payload(request_file)

    assert payload["stream"] is True

    missing_stream = tmp_path / "missing-stream.json"
    missing_stream.write_text(
        json.dumps(
            {
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 8,
                "temperature": 0.0,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="stream=true"):
        measure.load_request_payload(missing_stream)

    missing_required = tmp_path / "missing-required.json"
    missing_required.write_text(
        json.dumps({"messages": [], "stream": True}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="missing required fields"):
        measure.load_request_payload(missing_required)


def test_parse_sse_line_handles_control_fields_and_malformed_data() -> None:
    assert measure._parse_sse_line("") is None
    assert measure._parse_sse_line(": keepalive") is None
    assert measure._parse_sse_line("event: ping") is None
    assert measure._parse_sse_line("data: [DONE]") == {"done": True}
    assert measure._parse_sse_line('data: {"choices": []}') == {"choices": []}

    with pytest.raises(ValueError, match="Malformed SSE data line"):
        measure._parse_sse_line("data: {not-json}")


@pytest.mark.parametrize(
    ("chunk", "expected"),
    [
        ({}, False),
        ({"choices": []}, False),
        ({"choices": [{"delta": {"role": "assistant"}}]}, False),
        ({"choices": [{"delta": {"content": ""}}]}, False),
        ({"choices": [{"delta": {"tool_calls": [{"id": "call"}]}}]}, False),
        ({"choices": [{"delta": {"content": "hello"}}]}, True),
        ({"choices": [{"delta": {"reasoning_content": "thinking"}}]}, True),
    ],
)
def test_first_content_chunk_only_accepts_non_empty_content(
    chunk: dict[str, Any], expected: bool
) -> None:
    assert measure._first_content_chunk(chunk) is expected


def test_measure_request_streams_lines_until_done_and_preserves_zero_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    consumed_after_done = False

    class _Response:
        status_code = 200

        async def aiter_lines(self):
            nonlocal consumed_after_done
            yield _data_line({"choices": [{"delta": {"role": "assistant"}}]})
            yield _data_line({"choices": [{"delta": {"content": "hi"}}]})
            yield _data_line(
                {
                    "choices": [{"delta": {}, "finish_reason": "stop"}],
                    "timings": {
                        "prompt_n": 0,
                        "predicted_n": 2,
                        "tokens_cached": 0,
                    },
                }
            )
            yield "data: [DONE]"
            consumed_after_done = True
            raise AssertionError("stream reader continued after [DONE]")

        async def aread(self) -> bytes:
            return b""

    class _Stream:
        async def __aenter__(self) -> _Response:
            return _Response()

        async def __aexit__(self, *args: object) -> None:
            return None

    class _Client:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def __aenter__(self) -> "_Client":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        def stream(self, method: str, url: str, **kwargs: object) -> _Stream:
            assert method == "POST"
            assert url == "http://server.test/v1/chat/completions"
            assert kwargs["json"] == {"stream": True}
            return _Stream()

    ticks = iter([10.0, 10.025, 10.05])
    monkeypatch.setattr(measure.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(measure.time, "perf_counter", lambda: next(ticks, 10.05))

    result = asyncio.run(
        measure.measure_request(
            base_url="http://server.test",
            payload={"stream": True},
            request_type="speed_short",
            campaign_id="camp",
            config_id="cfg",
            cycle_number=1,
            request_index=2,
            timeout_s=1.0,
        )
    )

    assert result.outcome == RequestOutcome.SUCCESS
    assert result.http_status == 200
    assert result.ttft_ms == pytest.approx(25.0)
    assert result.total_wall_ms == pytest.approx(50.0)
    assert result.prompt_n == 0
    assert result.predicted_n == 2
    assert result.cache_n == 0
    assert result.total_tokens == 2
    assert consumed_after_done is False

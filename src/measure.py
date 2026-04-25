"""
QuantMap — measure.py
Streaming request harness with TTFT measurement, token accounting,
and request-level outcome classification.

TTFT DEFINITION (locked — matches MDD Section 9.1):
    Wall-clock milliseconds from the moment the first byte of the HTTP
    request is written to the socket, to the moment a streamed SSE chunk
    is received containing a non-empty delta.content or
    delta.reasoning_content field.

    NOT the first chunk. The first chunk with actual token content.

    This definition is encoded in _first_content_chunk() and is never
    changed. All TTFT values in raw.jsonl are produced by this function.

SEED AND DETERMINISM NOTE:
    Request payloads include a fixed seed per request class. This stabilizes
    sampling behavior across configs to reduce one source of variance. It does
    NOT guarantee runtime equivalence between configs — two configs producing
    identical token output are not necessarily equivalent in runtime
    performance. This is a performance lab, not an output-comparison lab.

OUTCOME CLASSIFICATION:
    Every request produces exactly one outcome string (see RequestOutcome).
    The outcome is determined by the first failure mode encountered. A request
    with outcome != "success" is retained in raw.jsonl but flagged; the
    runner uses success_rate as an elimination filter.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

import httpx  # type: ignore[import]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Outcome classification
# ---------------------------------------------------------------------------


class RequestOutcome(str, Enum):
    """
    Every request produces exactly one outcome. Values match the locked
    strings in MDD Section 9.2 and raw.jsonl schema.
    """

    SUCCESS = "success"
    TIMEOUT = "timeout"  # httpx.TimeoutException
    HTTP_ERROR = "http_error"  # 4xx / 5xx from server
    MALFORMED_STREAM = "malformed_stream"  # SSE parse failure
    TRUNCATED = "truncated"  # stream ended before stop token
    SERVER_RESTART = "server_restart"  # 503 mid-stream (server reloading)
    OOM = "oom"  # 500 with OOM text in body


# ---------------------------------------------------------------------------
# Request result dataclass
# ---------------------------------------------------------------------------


@dataclass
class RequestResult:
    """
    Complete per-request measurement record.

    All fields map 1:1 to raw.jsonl columns (MDD Section 9.2).
    None values indicate the measurement was not reachable due to an earlier
    failure (e.g. ttft_ms is None if the request timed out before the first
    token arrived).
    """

    # Identity
    campaign_id: str
    config_id: str
    cycle_number: int
    request_index: int  # 1 = cold, 2–6 = warm
    is_cold: bool
    request_type: str  # speed_short | speed_medium | quality_code | quality_reasoning

    # Outcome
    outcome: RequestOutcome
    http_status: int | None

    # TTFT (locked definition — see module docstring)
    ttft_ms: float | None

    # Wall time
    total_wall_ms: float | None

    # Token accounting from server timings block
    prompt_n: int | None
    prompt_ms: float | None
    prompt_per_second: float | None
    predicted_n: int | None
    predicted_ms: float | None
    predicted_per_second: float | None
    cache_n: int | None
    total_tokens: int | None  # prompt_n + predicted_n (derived)

    # Server context (populated by runner before writing)
    server_pid: int | None = None
    resolved_cmd_argv: list[str] = field(default_factory=list)

    # Timestamps
    timestamp_start: str = ""  # ISO8601 UTC

    # Cycle validity — set to "invalid" by runner on crash recovery
    cycle_status: str = "complete"

    # Error detail (populated on non-success outcomes)
    error_detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a flat dict suitable for raw.jsonl."""
        d = {
            "campaign_id": self.campaign_id,
            "config_id": self.config_id,
            "cycle_number": self.cycle_number,
            "request_index": self.request_index,
            "is_cold": self.is_cold,
            "request_type": self.request_type,
            "outcome": self.outcome.value,
            "http_status": self.http_status,
            "ttft_ms": self.ttft_ms,
            "total_wall_ms": self.total_wall_ms,
            "prompt_n": self.prompt_n,
            "prompt_ms": self.prompt_ms,
            "prompt_per_second": self.prompt_per_second,
            "predicted_n": self.predicted_n,
            "predicted_ms": self.predicted_ms,
            "predicted_per_second": self.predicted_per_second,
            "cache_n": self.cache_n,
            "total_tokens": self.total_tokens,
            "server_pid": self.server_pid,
            "resolved_cmd_argv": self.resolved_cmd_argv,
            "timestamp_start": self.timestamp_start,
            "cycle_status": self.cycle_status,
            "error_detail": self.error_detail,
        }
        return d


# ---------------------------------------------------------------------------
# Request payload loading
# ---------------------------------------------------------------------------


def load_request_payload(request_file: Path) -> dict[str, Any]:
    """
    Load and validate a request payload from a JSON file.

    Validates that required fields are present and that stream=true is set.
    TTFT measurement requires streaming — non-streaming requests are rejected.

    Raises:
        FileNotFoundError  — request file not found
        ValueError         — missing required fields or stream != true
    """
    if not request_file.is_file():
        raise FileNotFoundError(f"Request file not found: {request_file}")

    with open(request_file, encoding="utf-8") as f:
        payload = json.load(f)

    required = {"messages", "max_tokens", "temperature"}
    missing = required - set(payload.keys())
    if missing:
        raise ValueError(
            f"Request file {request_file.name} is missing required fields: {missing}"
        )

    if not payload.get("stream", False):
        raise ValueError(
            f"Request file {request_file.name} must have stream=true. "
            "TTFT measurement requires a streaming response."
        )

    return payload


# ---------------------------------------------------------------------------
# SSE parsing
# ---------------------------------------------------------------------------


def _parse_sse_line(line: str) -> dict | None:
    """
    Parse a single SSE text line into a dict.

    Accepts a fully-decoded, already-stripped text line (as produced by
    httpx's aiter_lines()).  Callers must not pass raw bytes or unstripped
    lines — decoding and stripping are the caller's responsibility so this
    function stays pure and testable.

    Returns:
        None          — keep-alive ping, comment (:), empty, or non-data field
        {"done": True} — terminal data: [DONE] sentinel
        dict          — parsed JSON payload from a data: line

    Raises:
        ValueError    — data: line whose JSON payload does not parse
    """
    if not line or line.startswith(":"):
        return None  # keep-alive or comment

    if line == "data: [DONE]":
        return {"done": True}

    if line.startswith("data: "):
        try:
            return json.loads(line[6:])
        except json.JSONDecodeError as exc:
            raise ValueError(f"Malformed SSE data line: {line!r}") from exc

    # Non-data SSE field (event:, id:, retry:) — ignore
    return None


def _first_content_chunk(chunk: dict) -> bool:
    """
    Return True if this SSE chunk contains actual token content.

    Per the locked TTFT definition: we are looking for a non-empty
    delta.content or delta.reasoning_content field. Role-only chunks,
    empty delta chunks, and tool-call-start chunks do not qualify.

    This function is the authoritative implementation of the TTFT gate.
    Do not modify without updating MDD Section 9.1.
    """
    choices = chunk.get("choices", [])
    if not choices:
        return False

    delta = choices[0].get("delta", {})

    content = delta.get("content")
    if content and len(content) > 0:
        return True

    reasoning = delta.get("reasoning_content")
    if reasoning and len(reasoning) > 0:
        return True

    return False


# ---------------------------------------------------------------------------
# Core measurement function
# ---------------------------------------------------------------------------


async def measure_request(
    base_url: str,
    payload: dict[str, Any],
    request_type: str,
    campaign_id: str,
    config_id: str,
    cycle_number: int,
    request_index: int,
    timeout_s: float = 300.0,
) -> RequestResult:
    """
    Send a single streaming request and return a fully populated RequestResult.

    TTFT is measured as wall-clock milliseconds from first-byte-sent to the
    first SSE chunk containing actual token content (see _first_content_chunk).

    The function never raises — all failure modes are captured in the
    outcome field. This ensures raw.jsonl always gets a complete record,
    even for failed requests.

    Args:
        base_url:       Server base URL, e.g. "http://127.0.0.1:8100"
        payload:        Request dict (loaded via load_request_payload)
        request_type:   String label for this request class
        campaign_id:    Campaign identifier
        config_id:      Config identifier
        cycle_number:   Cycle number (1-indexed)
        request_index:  Request index within cycle (1=cold, 2-6=warm)
        timeout_s:      Total request timeout in seconds

    Returns:
        RequestResult with all fields populated.
    """
    is_cold = request_index == 1
    timestamp_start = datetime.now(timezone.utc).isoformat()

    # Sentinel values — replaced on success or partial success
    outcome = RequestOutcome.TIMEOUT
    http_status: int | None = None
    ttft_ms: float | None = None
    total_wall_ms: float | None = None
    prompt_n: int | None = None
    prompt_ms: float | None = None
    prompt_per_second: float | None = None
    predicted_n: int | None = None
    predicted_ms: float | None = None
    predicted_per_second: float | None = None
    cache_n: int | None = None
    total_tokens: int | None = None
    error_detail: str = ""

    url = f"{base_url}/v1/chat/completions"
    wall_start = time.perf_counter()
    # ttft_deadline removed — per-token deadline enforcement not implemented.
    # The httpx client-level timeout (timeout_s) is the effective time limit.
    # If per-token timeout is added in future, compute it here. (MED-8 fix)

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_s)) as client:
            async with client.stream(
                "POST",
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
            ) as response:
                http_status = response.status_code

                # -- Non-200 responses ------------------------------------
                if response.status_code == 503:
                    await response.aread()
                    outcome = RequestOutcome.SERVER_RESTART
                    error_detail = "HTTP 503 — server reloading or overloaded"
                    logger.warning(
                        "[%s/%s cycle=%d req=%d] %s",
                        config_id,
                        request_type,
                        cycle_number,
                        request_index,
                        error_detail,
                    )
                    return _build_result(
                        locals(),
                        outcome,
                        timestamp_start,
                        is_cold,
                        campaign_id,
                        config_id,
                        cycle_number,
                        request_index,
                        request_type,
                    )

                if response.status_code != 200:
                    body = (await response.aread()).decode("utf-8", errors="replace")
                    # Classify OOM separately — it is operationally distinct
                    if response.status_code == 500 and (
                        "out of memory" in body.lower()
                        or "oom" in body.lower()
                        or "alloc" in body.lower()
                    ):
                        outcome = RequestOutcome.OOM
                        error_detail = f"HTTP 500 OOM: {body[:200]}"
                    else:
                        outcome = RequestOutcome.HTTP_ERROR
                        error_detail = f"HTTP {response.status_code}: {body[:200]}"
                    logger.warning(
                        "[%s/%s cycle=%d req=%d] %s",
                        config_id,
                        request_type,
                        cycle_number,
                        request_index,
                        error_detail,
                    )
                    return _build_result(
                        locals(),
                        outcome,
                        timestamp_start,
                        is_cold,
                        campaign_id,
                        config_id,
                        cycle_number,
                        request_index,
                        request_type,
                    )

                # -- Stream the response ----------------------------------
                ttft_captured = False
                last_chunk: dict | None = None
                received_any_content = False

                # aiter_lines() buffers across HTTP chunk boundaries so each
                # iteration yields one complete SSE line.  This simultaneously
                # fixes two bugs present in the earlier aiter_bytes() design:
                #
                # CRIT-3 (outer-loop break scope): With aiter_bytes() + an
                #   inner split loop, `break` on [DONE] only exited the inner
                #   for-loop; the outer async-for kept reading.  With a single
                #   flat aiter_lines() loop, `break` exits the only loop.
                #
                # HIGH-1 (split-boundary JSON parse error): aiter_bytes()
                #   delivered raw network chunks that could be split mid-JSON
                #   (e.g. at a 1460-byte TCP boundary), causing json.JSONDecodeError
                #   on a valid response and a false MALFORMED_STREAM outcome.
                #   aiter_lines() handles the buffering internally.
                async for raw_line in response.aiter_lines():
                    line = raw_line.strip()
                    if not line:
                        continue

                    try:
                        chunk = _parse_sse_line(line)
                    except ValueError as exc:
                        outcome = RequestOutcome.MALFORMED_STREAM
                        error_detail = str(exc)
                        total_wall_ms = (time.perf_counter() - wall_start) * 1000
                        logger.warning(
                            "[%s/%s cycle=%d req=%d] malformed stream: %s",
                            config_id,
                            request_type,
                            cycle_number,
                            request_index,
                            exc,
                        )
                        return _build_result(
                            locals(),
                            outcome,
                            timestamp_start,
                            is_cold,
                            campaign_id,
                            config_id,
                            cycle_number,
                            request_index,
                            request_type,
                        )

                    if chunk is None:
                        continue

                    if chunk.get("done"):
                        break  # exits the only loop — stream reading terminates here

                    # -- TTFT gate (locked definition) ----------------
                    if not ttft_captured and _first_content_chunk(chunk):
                        ttft_ms = (time.perf_counter() - wall_start) * 1000
                        ttft_captured = True
                        received_any_content = True

                    last_chunk = chunk

                # -- Post-stream: extract timings from final chunk --------
                total_wall_ms = (time.perf_counter() - wall_start) * 1000

                if not received_any_content:
                    # Stream completed but no content tokens were observed
                    outcome = RequestOutcome.TRUNCATED
                    error_detail = "Stream ended without any content tokens"
                    logger.warning(
                        "[%s/%s cycle=%d req=%d] truncated stream",
                        config_id,
                        request_type,
                        cycle_number,
                        request_index,
                    )
                    return _build_result(
                        locals(),
                        outcome,
                        timestamp_start,
                        is_cold,
                        campaign_id,
                        config_id,
                        cycle_number,
                        request_index,
                        request_type,
                    )

                # Extract timing data from the last chunk's usage block.
                # llama-server emits a final chunk with usage stats when
                # stream_options.include_usage is set, or embeds timings
                # in a custom field. We try both locations.
                if last_chunk is not None:
                    timings = last_chunk.get("timings") or {}
                    usage = last_chunk.get("usage") or {}

                    # Use explicit None checks instead of `or`-chaining.
                    # `or` short-circuits on 0, which is a valid token count
                    # (e.g. fully-cached prompt). (MED-1 fix)
                    _pn_candidates = [
                        _int(timings.get("prompt_n")),
                        _int(timings.get("tokens_evaluated")),
                        _int(usage.get("prompt_tokens")),
                    ]
                    prompt_n = next((v for v in _pn_candidates if v is not None), None)
                    prompt_ms = _float(timings.get("prompt_ms"))
                    prompt_per_second = _float(timings.get("prompt_per_second"))

                    _pdn_candidates = [
                        _int(timings.get("predicted_n")),
                        _int(timings.get("tokens_predicted")),
                        _int(usage.get("completion_tokens")),
                    ]
                    predicted_n = next((v for v in _pdn_candidates if v is not None), None)
                    predicted_ms = _float(timings.get("predicted_ms"))
                    predicted_per_second = _float(timings.get("predicted_per_second"))

                    cache_n = _int(timings.get("tokens_cached"))

                    if prompt_n is not None and predicted_n is not None:
                        total_tokens = prompt_n + predicted_n

                # Check for truncation: finish_reason should be "stop" or
                # "length" on a clean completion. Anything else is suspicious.
                finish_reason = None
                if last_chunk is not None:
                    choices = last_chunk.get("choices", [])
                    if choices:
                        finish_reason = choices[0].get("finish_reason")

                if finish_reason not in ("stop", "length", None):
                    outcome = RequestOutcome.TRUNCATED
                    error_detail = f"Unexpected finish_reason: {finish_reason!r}"
                    logger.warning(
                        "[%s/%s cycle=%d req=%d] finish_reason=%r",
                        config_id,
                        request_type,
                        cycle_number,
                        request_index,
                        finish_reason,
                    )
                    return _build_result(
                        locals(),
                        outcome,
                        timestamp_start,
                        is_cold,
                        campaign_id,
                        config_id,
                        cycle_number,
                        request_index,
                        request_type,
                    )

                outcome = RequestOutcome.SUCCESS
                logger.debug(
                    "[%s/%s cycle=%d req=%d] ttft=%.1fms tg=%.2f t/s wall=%.1fms",
                    config_id,
                    request_type,
                    cycle_number,
                    request_index,
                    ttft_ms or 0,
                    predicted_per_second or 0,
                    total_wall_ms,
                )

    except httpx.TimeoutException as exc:
        outcome = RequestOutcome.TIMEOUT
        error_detail = f"Request timed out after {timeout_s}s: {exc}"
        total_wall_ms = (time.perf_counter() - wall_start) * 1000
        logger.warning(
            "[%s/%s cycle=%d req=%d] timeout after %.1fs",
            config_id,
            request_type,
            cycle_number,
            request_index,
            timeout_s,
        )

    except httpx.HTTPError as exc:
        outcome = RequestOutcome.HTTP_ERROR
        error_detail = f"HTTP error: {exc}"
        total_wall_ms = (time.perf_counter() - wall_start) * 1000
        logger.warning(
            "[%s/%s cycle=%d req=%d] http error: %s",
            config_id,
            request_type,
            cycle_number,
            request_index,
            exc,
        )

    except Exception as exc:  # noqa: BLE001
        outcome = RequestOutcome.MALFORMED_STREAM
        error_detail = f"Unexpected error: {exc}"
        total_wall_ms = (time.perf_counter() - wall_start) * 1000
        logger.exception(
            "[%s/%s cycle=%d req=%d] unexpected error",
            config_id,
            request_type,
            cycle_number,
            request_index,
        )

    return _build_result(
        locals(),
        outcome,
        timestamp_start,
        is_cold,
        campaign_id,
        config_id,
        cycle_number,
        request_index,
        request_type,
    )


# ---------------------------------------------------------------------------
# Result construction helper
# ---------------------------------------------------------------------------


def _build_result(
    ns: dict,
    outcome: RequestOutcome,
    timestamp_start: str,
    is_cold: bool,
    campaign_id: str,
    config_id: str,
    cycle_number: int,
    request_index: int,
    request_type: str,
) -> RequestResult:
    """
    Construct a RequestResult from the local namespace of measure_request.
    Uses .get() with None defaults so partial measurements are preserved.
    """
    return RequestResult(
        campaign_id=campaign_id,
        config_id=config_id,
        cycle_number=cycle_number,
        request_index=request_index,
        is_cold=is_cold,
        request_type=request_type,
        outcome=outcome,
        http_status=ns.get("http_status"),
        ttft_ms=ns.get("ttft_ms"),
        total_wall_ms=ns.get("total_wall_ms"),
        prompt_n=ns.get("prompt_n"),
        prompt_ms=ns.get("prompt_ms"),
        prompt_per_second=ns.get("prompt_per_second"),
        predicted_n=ns.get("predicted_n"),
        predicted_ms=ns.get("predicted_ms"),
        predicted_per_second=ns.get("predicted_per_second"),
        cache_n=ns.get("cache_n"),
        total_tokens=ns.get("total_tokens"),
        timestamp_start=timestamp_start,
        error_detail=ns.get("error_detail", ""),
    )


# ---------------------------------------------------------------------------
# Type coercion helpers (safe — return None rather than raise)
# ---------------------------------------------------------------------------


def _int(v: Any) -> int | None:
    """Safely cast a value to int; return None on failure."""
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _float(v: Any) -> float | None:
    """Safely cast a value to float; return None on failure."""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Synchronous wrapper (for runner.py which manages its own event loop)
# ---------------------------------------------------------------------------


def measure_request_sync(
    base_url: str,
    payload: dict[str, Any],
    request_type: str,
    campaign_id: str,
    config_id: str,
    cycle_number: int,
    request_index: int,
    timeout_s: float = 300.0,
) -> RequestResult:
    """
    Synchronous wrapper around measure_request for use in runner.py.

    runner.py is a synchronous orchestrator and does not maintain an async
    event loop. This wrapper creates a fresh event loop per call.

    For high-frequency concurrent use, call measure_request directly from
    an async context instead.
    """
    import asyncio

    return asyncio.run(
        measure_request(
            base_url=base_url,
            payload=payload,
            request_type=request_type,
            campaign_id=campaign_id,
            config_id=config_id,
            cycle_number=cycle_number,
            request_index=request_index,
            timeout_s=timeout_s,
        )
    )

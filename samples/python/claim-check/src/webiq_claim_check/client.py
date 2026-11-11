# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Auto REST request, retries, and error messages."""

import json
import math
import random
import re
import time
from contextlib import ExitStack
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx

AUTO_URL = "https://api.microsoft.ai/v3/auto"
MAX_RESPONSE_LENGTH = 30_000
MAX_RETRIES = 2
MAX_RETRY_DELAY_SECONDS = 60
REQUEST_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
RETRYABLE_STATUSES = {408, 429, 500, 502, 503, 504}
KNOWN_ERROR_CODES = {
    "AuthNoToken",
    "AuthInvalidApiKey",
    "AuthExpiredTrial",
    "AuthenticationFailed",
    "AuthUnauthorizedService",
    "AuthUserThrottled",
    "AuthUserDailyUsageExceeded",
    "HandlerInvalidInput",
    "InternalServerError",
    "RequestInvalidFormat",
    "RequestUnsupportedMediaType",
}


class AutoError(RuntimeError):
    """A service failure whose message contains no request or response content."""


def build_request(
    query: str, *, mode: str = "lite", language: str = "en", region: str = "US"
) -> dict[str, object]:
    if not isinstance(query, str) or not 1 <= len(query.strip()) <= 1_000:
        raise ValueError("The claim must contain between 1 and 1,000 characters.")
    if mode not in {"lite", "advanced"}:
        raise ValueError("Mode must be lite or advanced.")
    if not re.fullmatch(r"[a-zA-Z]{2}", language):
        raise ValueError("Language must be a two-letter code, such as en.")
    if not re.fullmatch(r"[a-zA-Z]{2}", region):
        raise ValueError("Region must be a two-letter code, such as US.")
    return {
        "query": query.strip(),
        "mode": mode,
        "language": language.lower(),
        "region": region.upper(),
        "maxResponseLength": MAX_RESPONSE_LENGTH,
        "responseFilter": ["web", "news"],
    }


def search_auto(
    api_key: str,
    query: str,
    *,
    mode: str = "lite",
    language: str = "en",
    region: str = "US",
    client: httpx.Client | None = None,
) -> dict[str, object]:
    payload = build_request(query, mode=mode, language=language, region=region)
    if not isinstance(api_key, str) or not api_key.strip():
        raise ValueError("Set WEBIQ_API_KEY to an API key with Auto access.")
    api_key = api_key.strip()
    if not all(33 <= ord(character) <= 126 for character in api_key):
        raise ValueError("WEBIQ_API_KEY contains whitespace or invalid header characters.")

    with ExitStack() as stack:
        session = client if client is not None else stack.enter_context(httpx.Client())
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = session.post(
                    AUTO_URL,
                    headers={
                        "x-apikey": api_key,
                        "content-type": "application/json",
                        "accept": "application/json",
                    },
                    json=payload,
                    timeout=REQUEST_TIMEOUT,
                    follow_redirects=False,
                )
            except httpx.RequestError as error:
                if attempt == MAX_RETRIES:
                    message = (
                        "The Web IQ request timed out."
                        if isinstance(error, httpx.TimeoutException)
                        else "Could not reach Web IQ. Check network, TLS, and proxy settings."
                    )
                    raise AutoError(
                        f"{message} Stopped after {attempt + 1} attempts."
                    ) from None
                time.sleep(_backoff(attempt))
                continue

            if response.status_code == 200:
                try:
                    body = response.json()
                except (json.JSONDecodeError, UnicodeDecodeError):
                    raise AutoError("Web IQ returned HTTP 200 with invalid JSON.") from None
                if not isinstance(body, dict) or "errorCode" in body:
                    raise AutoError("Web IQ returned an unexpected response object.")
                return body

            error_body = _error_body(response)
            failure = _failure_message(response.status_code, error_body, api_key)
            if (
                response.status_code not in RETRYABLE_STATUSES
                or error_body.get("errorCode") == "AuthUserDailyUsageExceeded"
                or attempt == MAX_RETRIES
            ):
                raise AutoError(f"{failure} Stopped after {attempt + 1} attempt(s).")
            try:
                delay = _retry_delay(
                    response.headers.get("retry-after"),
                    error_body.get("retryAfter"),
                    attempt,
                    datetime.now(timezone.utc),
                )
            except ValueError:
                raise AutoError(
                    f"{failure} Retry guidance was invalid; no automatic retry was made."
                ) from None
            if delay > MAX_RETRY_DELAY_SECONDS:
                raise AutoError(
                    f"{failure} The service requires waiting more than "
                    f"{MAX_RETRY_DELAY_SECONDS} seconds. "
                    "Try later; this run will not retry early."
                )
            time.sleep(delay)
    raise AssertionError("Unreachable retry state.")


def _error_body(response: httpx.Response) -> dict[str, object]:
    try:
        body = response.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return body if isinstance(body, dict) else {}


def _failure_message(status: int, body: dict[str, object], api_key: str) -> str:
    hints = {
        400: "Check the claim and documented request parameters.",
        401: "Check WEBIQ_API_KEY and whether it has expired.",
        403: "Confirm the key's application is enabled for Auto and the requested answer types.",
        429: "The service is throttling requests or the application has reached its quota.",
    }
    hint = hints.get(status, "The service could not complete the request. Try again later.")
    if 300 <= status < 400:
        hint = "Redirects are not followed, to avoid forwarding credentials."
    if body.get("errorCode") == "AuthUserDailyUsageExceeded":
        hint = (
            "The daily quota is exhausted. It resets at 00:00 UTC; "
            "no automatic retry was made."
        )
    message = f"Web IQ returned HTTP {status}. {hint}"
    code = body.get("errorCode")
    if isinstance(code, str) and code in KNOWN_ERROR_CODES and api_key not in code:
        message += f" Code: {code}."
    trace_id = body.get("traceId")
    if (
        isinstance(trace_id, str)
        and re.fullmatch(
            r"[0-9a-fA-F]{32}|[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}",
            trace_id,
        )
        and api_key not in trace_id
    ):
        message += f" Trace ID: {trace_id}."
    return message


def _backoff(attempt: int) -> float:
    return random.uniform(0.5, 1.0) * (2 ** attempt)


def _retry_delay(
    header: str | None, body_value: object, attempt: int, now: datetime
) -> float:
    delays = [_backoff(attempt)]
    if header is not None:
        delays.append(_parse_retry_after(header, now, http_header=True))
    if body_value is not None:
        delays.append(_parse_retry_after(body_value, now, http_header=False))
    return max(delays)


def _parse_retry_after(value: object, now: datetime, *, http_header: bool) -> float:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Invalid retry guidance.")
    value = value.strip()
    pattern = r"[0-9]+(?:\.[0-9]+)?" if http_header else r"[0-9]+(?:\.[0-9]+)?s"
    if re.fullmatch(pattern, value):
        seconds = float(value if http_header else value[:-1])
        if not math.isfinite(seconds):
            raise ValueError("Non-finite retry delay.")
        return seconds
    try:
        instant = (
            parsedate_to_datetime(value)
            if http_header
            else datetime.fromisoformat(value.replace("Z", "+00:00"))
        )
    except (ValueError, TypeError, OverflowError):
        raise ValueError("Invalid retry timestamp.") from None
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("Retry timestamps must include a timezone.")
    return max(0.0, (instant - now).total_seconds())

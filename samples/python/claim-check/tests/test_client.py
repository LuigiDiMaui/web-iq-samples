# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

import json

import httpx
import pytest

from webiq_claim_check import client
from webiq_claim_check.client import AutoError, build_request, search_auto


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    delays = []
    monkeypatch.setattr(client.time, "sleep", delays.append)
    return delays


def mock_client(*responses):
    calls = []
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    return httpx.Client(transport=httpx.MockTransport(handler)), calls


def test_build_request_uses_documented_defaults():
    assert build_request("  The Eiffel Tower is taller than 300 metres. ") == {
        "query": "The Eiffel Tower is taller than 300 metres.",
        "mode": "lite",
        "language": "en",
        "region": "US",
        "maxResponseLength": 30000,
        "responseFilter": ["web", "news"],
    }


@pytest.mark.parametrize(
    "kwargs",
    [
        {"query": ""},
        {"query": "x" * 1001},
        {"query": "claim", "mode": "deep"},
        {"query": "claim", "language": "eng"},
        {"query": "claim", "region": "USA"},
    ],
)
def test_build_request_rejects_invalid_input(kwargs):
    query = kwargs.pop("query")
    with pytest.raises(ValueError):
        build_request(query, **kwargs)


def test_search_sends_key_header_and_body():
    http, calls = mock_client(httpx.Response(200, json={"results": []}))
    assert search_auto("test-key", "claim", client=http) == {"results": []}
    request = calls[0]
    assert str(request.url) == client.AUTO_URL
    assert request.headers["x-apikey"] == "test-key"
    assert json.loads(request.content)["query"] == "claim"


def test_key_with_whitespace_is_rejected_before_any_call():
    http, calls = mock_client()
    with pytest.raises(ValueError):
        search_auto("bad key", "claim", client=http)
    assert calls == []


def test_429_is_retried_with_service_guidance(no_sleep):
    http, calls = mock_client(
        httpx.Response(429, json={"errorCode": "AuthUserThrottled", "retryAfter": "30s"}),
        httpx.Response(200, json={"results": []}),
    )
    search_auto("k", "claim", client=http)
    assert len(calls) == 2
    assert no_sleep == [30.0]


def test_wait_longer_than_limit_stops_without_retry():
    http, calls = mock_client(
        httpx.Response(429, json={"errorCode": "AuthUserThrottled", "retryAfter": "120s"})
    )
    with pytest.raises(AutoError, match="more than 60 seconds"):
        search_auto("k", "claim", client=http)
    assert len(calls) == 1


def test_daily_quota_is_not_retried():
    http, calls = mock_client(
        httpx.Response(429, json={"errorCode": "AuthUserDailyUsageExceeded"})
    )
    with pytest.raises(AutoError, match="00:00 UTC"):
        search_auto("k", "claim", client=http)
    assert len(calls) == 1


def test_401_reports_code_and_trace_id_but_no_body():
    trace = "0123456789abcdef0123456789abcdef"
    http, _ = mock_client(
        httpx.Response(
            401,
            json={"errorCode": "AuthInvalidApiKey", "traceId": trace, "message": "secret"},
        )
    )
    with pytest.raises(AutoError) as error:
        search_auto("k", "claim", client=http)
    message = str(error.value)
    assert "Code: AuthInvalidApiKey" in message
    assert trace in message
    assert "secret" not in message


def test_transient_errors_stop_after_three_attempts():
    http, calls = mock_client(
        httpx.Response(503), httpx.Response(503), httpx.Response(503)
    )
    with pytest.raises(AutoError, match="3 attempt"):
        search_auto("k", "claim", client=http)
    assert len(calls) == 3


def test_timeouts_are_reported_after_retries():
    http, calls = mock_client(*(httpx.ReadTimeout("timeout") for _ in range(3)))
    with pytest.raises(AutoError, match="timed out"):
        search_auto("k", "claim", client=http)
    assert len(calls) == 3


def test_redirects_are_not_followed():
    http, calls = mock_client(
        httpx.Response(302, headers={"location": "https://elsewhere.example/"})
    )
    with pytest.raises(AutoError, match="Redirects are not followed"):
        search_auto("k", "claim", client=http)
    assert len(calls) == 1


def test_invalid_json_is_an_error():
    http, _ = mock_client(httpx.Response(200, content=b"not json"))
    with pytest.raises(AutoError, match="invalid JSON"):
        search_auto("k", "claim", client=http)

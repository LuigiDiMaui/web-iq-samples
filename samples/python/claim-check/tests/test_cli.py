# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

import httpx
import pytest

from webiq_claim_check import cli, client


class Terminal:
    def __init__(self, interactive):
        self.interactive = interactive
        self.text = ""

    def isatty(self):
        return self.interactive

    def write(self, value):
        self.text += value

    def flush(self):
        pass


def test_help_needs_no_key_or_network(capsys):
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--help"])
    assert exit_info.value.code == 0
    assert "--mode" in capsys.readouterr().out


def test_piped_output_is_refused(monkeypatch, capsys):
    monkeypatch.setattr(cli.sys, "stdout", Terminal(False))
    monkeypatch.setenv("WEBIQ_API_KEY", "k")
    assert cli.main(["claim"]) == 1
    assert "interactive terminal" in capsys.readouterr().err


def test_missing_key_stops_before_a_call(monkeypatch, capsys):
    monkeypatch.setattr(cli.sys, "stdout", Terminal(True))
    monkeypatch.delenv("WEBIQ_API_KEY", raising=False)
    assert cli.main(["claim"]) == 1
    assert "WEBIQ_API_KEY" in capsys.readouterr().err


def test_end_to_end_with_a_mock_service(monkeypatch):
    body = {
        "results": [
            {
                "evidence": {"type": "text", "content": "Synthetic evidence. " * 50},
                "citations": [
                    {
                        "contentSource": "web",
                        "url": "https://example.com/synthetic-source",
                        "title": "Example source",
                        "lastUpdatedAt": "2026-11-05T12:00:00Z",
                        "crawledAt": "2026-11-06T06:00:00Z",
                    }
                ],
            }
        ]
    }
    http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body)))
    real_search = client.search_auto
    monkeypatch.setattr(
        cli, "search_auto", lambda *a, **k: real_search(*a, client=http, **k)
    )
    terminal = Terminal(True)
    monkeypatch.setattr(cli.sys, "stdout", terminal)
    monkeypatch.setenv("WEBIQ_API_KEY", "test-key")
    assert cli.main(["Synthetic claim"]) == 0
    assert "Example source" in terminal.text
    assert "999 characters returned, 199 shown" in terminal.text

# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

import io
import re
from datetime import datetime, timezone

from webiq_claim_check.display import (
    DISPLAY_CHARACTER_LIMIT,
    excerpt,
    render_evidence,
    timestamp_label,
)
from webiq_claim_check.evidence import Citation, EvidenceItem, EvidenceSelection

NOW = datetime(2026, 11, 6, 12, tzinfo=timezone.utc)


def source(url):
    return Citation(
        url=url,
        title=f"Title {url}",
        content_source="web",
        last_updated_at="2026-11-05T12:00:00Z",
        crawled_at="2026-11-06T06:00:00Z",
    )


def render(*items):
    output = io.StringIO()
    selection = EvidenceSelection(tuple(items), ())
    render_evidence("Synthetic claim\x1b[31m", selection, output, now=NOW)
    return output.getvalue()


def shown_excerpts(text):
    return [match.removesuffix("...") for match in re.findall(r'^    "(.*)"$', text, re.M)]


def test_each_source_shows_at_most_the_display_limit():
    words = "word " * 600
    text = render(
        EvidenceItem(words, (source("https://a.example"),), False),
        EvidenceItem(words, (source("https://a.example"),), False),
    )
    excerpts = shown_excerpts(text)
    assert len(excerpts) == 1
    assert len(excerpts[0]) <= DISPLAY_CHARACTER_LIMIT
    assert "Not shown" in text
    assert "3,000 characters returned" in text


def test_multi_source_excerpt_counts_toward_every_cited_source():
    words = "word " * 30
    text = render(
        EvidenceItem(words, (source("https://a.example"), source("https://b.example")), False),
        EvidenceItem("x " * 200, (source("https://a.example"),), False),
        EvidenceItem("y " * 200, (source("https://b.example"),), False),
    )
    excerpts = shown_excerpts(text)
    assert len(excerpts[0]) + len(excerpts[1]) <= DISPLAY_CHARACTER_LIMIT
    assert len(excerpts[0]) + len(excerpts[2]) <= DISPLAY_CHARACTER_LIMIT


def test_totals_and_freshness_are_shown():
    text = render(EvidenceItem("Short synthetic evidence.", (source("https://a.example"),), False))
    assert "(1 day ago)" in text
    assert "(6 hours ago)" in text
    assert "25 characters of evidence from 1 source(s)" in text
    assert "not an automated verdict" in text


def test_control_characters_are_removed():
    assert "\x1b" not in render(
        EvidenceItem("Text\x1b[2J here.", (source("https://a.example"),), False)
    )


def test_empty_selection_makes_no_claim():
    text = render()
    assert "does not confirm or refute" in text


def test_excerpt_cuts_at_a_word_boundary():
    cut = excerpt("alpha beta gamma delta " * 20, 50)
    assert len(cut) <= 50
    assert not cut.endswith(" ")
    assert excerpt("short", 10) == ""


def test_timestamp_labels():
    assert "age unknown" in timestamp_label(None, NOW)
    assert "age unknown" in timestamp_label("2026-11-06T10:00:00", NOW)
    assert "future" in timestamp_label("2027-01-01T00:00:00Z", NOW)
    assert "unrecognized" in timestamp_label("yesterday", NOW)

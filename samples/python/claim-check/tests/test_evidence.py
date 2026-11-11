# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

import pytest

from webiq_claim_check.evidence import select_evidence


def citation(url, **extra):
    return {
        "contentSource": "web",
        "url": url,
        "title": f"Title {url}",
        "lastUpdatedAt": "2026-11-05T12:00:00Z",
        "crawledAt": "2026-11-06T06:00:00Z",
        **extra,
    }


def result(text, *urls, evidence_type="text"):
    return {
        "evidence": {"type": evidence_type, "content": text},
        "citations": [citation(url) for url in urls],
    }


def test_text_evidence_keeps_its_own_citations():
    selection = select_evidence(
        {"results": [result("Synthetic text.", "https://a.example/1", "https://b.example/2")]}
    )
    assert len(selection.items) == 1
    assert [c.url for c in selection.items[0].citations] == [
        "https://a.example/1",
        "https://b.example/2",
    ]
    assert selection.source_count == 2


def test_budget_is_shared_by_every_cited_source():
    selection = select_evidence(
        {
            "results": [
                result("A" * 2500, "https://a.example/1"),
                result("B" * 1000, "https://a.example/1", "https://b.example/2"),
                result("C", "https://a.example/1"),
            ]
        }
    )
    assert len(selection.items) == 2
    assert len(selection.items[1].content) == 500
    assert selection.items[1].shortened
    assert any("budget is exhausted" in w for w in selection.warnings)


def test_unusable_results_are_skipped_with_a_warning():
    selection = select_evidence(
        {
            "results": [
                result("Image", "https://img.example", evidence_type="media/image"),
                result("Bad URL", "javascript:alert(1)"),
                {"evidence": {"type": "text", "content": "No sources"}, "citations": []},
                result("   ", "https://blank.example"),
            ]
        }
    )
    assert selection.items == ()
    assert len(selection.warnings) == 4


def test_at_most_ten_sources():
    results = [result(f"Item {i}", f"https://s{i}.example") for i in range(12)]
    selection = select_evidence({"results": results})
    assert selection.source_count == 10
    assert any("10-source limit" in w for w in selection.warnings)


def test_missing_results_is_empty():
    assert select_evidence({}).items == ()


def test_long_passage_keeps_its_returned_length():
    selection = select_evidence({"results": [result("x" * 5154, "https://a.example")]})
    item = selection.items[0]
    assert len(item.content) == 3000
    assert item.returned_length == 5154
    assert item.shortened


def test_invalid_results_type_raises():
    with pytest.raises(ValueError):
        select_evidence({"results": {}})

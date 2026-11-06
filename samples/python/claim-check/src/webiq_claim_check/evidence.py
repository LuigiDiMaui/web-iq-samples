# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Parse Auto results into evidence items, each with its own citations."""

import unicodedata
from dataclasses import dataclass
from urllib.parse import urlsplit

MAX_SOURCES = 10
MAX_CHARACTERS_PER_SOURCE = 3_000


@dataclass(frozen=True, slots=True)
class Citation:
    url: str
    title: str | None
    content_source: str | None
    last_updated_at: str | None
    crawled_at: str | None


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    content: str
    citations: tuple[Citation, ...]
    shortened: bool
    returned_length: int = 0
    """Characters Auto returned for this item, before this sample's per-source budget."""


@dataclass(frozen=True, slots=True)
class EvidenceSelection:
    items: tuple[EvidenceItem, ...]
    warnings: tuple[str, ...]

    @property
    def source_count(self) -> int:
        return len({source.url for item in self.items for source in item.citations})


def select_evidence(response: dict[str, object]) -> EvidenceSelection:
    """Keep up to 10 sources and 3,000 characters per source, in service order.

    This is the evidence a model would receive. What the terminal shows is
    limited separately in display.py.
    """
    results = response.get("results")
    if results is None:
        results = []
    if not isinstance(results, list):
        raise ValueError("The Auto response has an invalid results field; expected an array.")

    items: list[EvidenceItem] = []
    warnings: list[str] = []
    used_characters: dict[str, int] = {}
    for index, result in enumerate(results, start=1):
        try:
            content, citations = _parse_result(result)
        except ValueError as error:
            warnings.append(f"Result {index} skipped: {error}")
            continue
        urls = {citation.url for citation in citations}
        if len(used_characters.keys() | urls) > MAX_SOURCES:
            warnings.append(
                f"Result {index} skipped: its complete citation group exceeds the "
                f"{MAX_SOURCES}-source limit."
            )
            continue
        # Charge a multi-source excerpt to every source it cites, including repeats.
        available = min(
            MAX_CHARACTERS_PER_SOURCE - used_characters.get(url, 0) for url in urls
        )
        if available == 0:
            warnings.append(
                f"Result {index} skipped: a cited source's character budget is exhausted."
            )
            continue
        returned_length = len(content)
        shortened = returned_length > available
        content = content[:available]
        for url in urls:
            used_characters[url] = used_characters.get(url, 0) + len(content)
        items.append(EvidenceItem(content, citations, shortened, returned_length))
    return EvidenceSelection(tuple(items), tuple(warnings))


def _parse_result(result: object) -> tuple[str, tuple[Citation, ...]]:
    if not isinstance(result, dict):
        raise ValueError("expected an evidence result object.")
    evidence = result.get("evidence")
    if not isinstance(evidence, dict) or evidence.get("type") != "text":
        raise ValueError("expected text evidence for the web/news filter.")
    content = evidence.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("no nonempty text evidence was supplied.")
    raw_citations = result.get("citations")
    if not isinstance(raw_citations, list) or not raw_citations:
        raise ValueError("no usable source citations were supplied.")
    citations = tuple(_parse_citation(citation) for citation in raw_citations)
    return content.strip(), citations


def _parse_citation(value: object) -> Citation:
    if not isinstance(value, dict):
        raise ValueError("a citation is not an object; the whole result was omitted.")
    url = value.get("url")
    if not isinstance(url, str) or not _is_source_url(url):
        raise ValueError("a citation lacks a valid HTTP(S) URL; the whole result was omitted.")
    fields: list[str | None] = []
    for key in ("title", "contentSource", "lastUpdatedAt", "crawledAt"):
        field = value.get(key)
        if field is not None and not isinstance(field, str):
            raise ValueError("a citation has invalid text metadata; the whole result was omitted.")
        fields.append(field.strip() or None if isinstance(field, str) else None)
    return Citation(
        url=url,
        title=fields[0],
        content_source=fields[1],
        last_updated_at=fields[2],
        crawled_at=fields[3],
    )


def _is_source_url(url: str) -> bool:
    if any(
        character.isspace() or unicodedata.category(character).startswith("C")
        for character in url
    ):
        return False
    try:
        parsed = urlsplit(url)
        return (
            parsed.scheme in {"http", "https"}
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and (parsed.port is None or 1 <= parsed.port <= 65535)
        )
    except ValueError:
        return False

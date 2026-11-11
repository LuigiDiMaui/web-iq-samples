# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Terminal output: short excerpts, sources, and freshness labels."""

import unicodedata
from datetime import datetime, timezone
from typing import TextIO

from .evidence import EvidenceSelection

# The Web IQ Terms of Use limit displayed content to 200 characters per source,
# or less if the website owner sets a lower maximum (which this sample can't detect).
DISPLAY_CHARACTER_LIMIT = 200
MIN_EXCERPT_CHARACTERS = 40
ELLIPSIS = "..."


def timestamp_label(value: str | None, now: datetime) -> str:
    if not value:
        return "not provided (age unknown)"
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return "unrecognized timestamp (age unknown)"
    if instant.tzinfo is None or instant.utcoffset() is None:
        return f"{terminal_text(value)} (timezone not supplied; age unknown)"
    try:
        instant = instant.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        return "unrecognized timestamp (age unknown)"
    stamp = instant.isoformat().replace("+00:00", "Z")
    age = (now - instant).total_seconds()
    if age < 0:
        return f"{stamp} (future timestamp; verify the source clock)"
    if age < 60:
        return f"{stamp} (less than 1 minute ago)"
    for seconds, unit in ((86400, "day"), (3600, "hour"), (60, "minute")):
        if age >= seconds:
            count = int(age // seconds)
            return f"{stamp} ({count} {unit}{'' if count == 1 else 's'} ago)"
    raise AssertionError("Unreachable timestamp state.")


def terminal_text(value: str) -> str:
    """Drop control characters and collapse whitespace to a single line."""
    text = "".join(
        character
        for character in value
        if not unicodedata.category(character).startswith("C")
        or character in "\n\t"
    )
    return " ".join(text.split())


def excerpt(text: str, limit: int) -> str:
    """Return at most `limit` characters of text, cut at a word boundary when possible."""
    if limit < MIN_EXCERPT_CHARACTERS:
        return ""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    boundary = cut.rfind(" ")
    if boundary >= limit * 0.6:
        cut = cut[:boundary]
    return cut.rstrip()


def render_evidence(
    claim: str,
    selection: EvidenceSelection,
    output: TextIO,
    *,
    now: datetime | None = None,
) -> None:
    now = now if now is not None else datetime.now(timezone.utc)
    print(f"Claim: {terminal_text(claim)}", file=output)
    print("Retrieved evidence for human review - not an automated verdict.", file=output)
    if not selection.items:
        print(
            "No usable sourced text evidence was returned. "
            "This does not confirm or refute the claim.",
            file=output,
        )
        return
    print(
        f"{len(selection.items)} evidence item(s), "
        f"{selection.source_count} distinct source URL(s).",
        file=output,
    )

    shown_per_source: dict[str, int] = {}
    returned_total = 0
    kept_total = 0
    shown_total = 0
    for index, item in enumerate(selection.items, start=1):
        text = terminal_text(item.content)
        urls = {source.url for source in item.citations}
        # A multi-source excerpt counts toward the display limit of every source it cites.
        available = min(
            DISPLAY_CHARACTER_LIMIT - shown_per_source.get(url, 0) for url in urls
        )
        shown = excerpt(text, available)
        for url in urls:
            shown_per_source[url] = shown_per_source.get(url, 0) + len(shown)
        returned = item.returned_length or len(item.content)
        kept_total += len(item.content)
        returned_total += returned
        shown_total += len(shown)

        print(
            f"\n[{index}] Evidence ({returned:,} characters returned, "
            f"{len(shown):,} shown)",
            file=output,
        )
        if shown:
            suffix = ELLIPSIS if len(shown) < len(text) else ""
            print(f'    "{shown}{suffix}"', file=output)
        else:
            print(
                "    [Not shown: this run already displayed the maximum excerpt "
                "from a cited source. Open the source to read it.]",
                file=output,
            )
        for source_index, source in enumerate(item.citations, start=1):
            print(
                f"  Source {source_index}: "
                f"{terminal_text(source.title or '(title not provided)')}",
                file=output,
            )
            print(f"    URL: {source.url}", file=output)
            print(
                f"    Content source: {terminal_text(source.content_source or 'not provided')}",
                file=output,
            )
            print(
                f"    Last updated: {timestamp_label(source.last_updated_at, now)}",
                file=output,
            )
            print(f"    Crawled: {timestamp_label(source.crawled_at, now)}", file=output)
    print(
        f"\nAuto returned {returned_total:,} characters of evidence from "
        f"{selection.source_count} source(s). This sample keeps {kept_total:,} for a model "
        f"in this run (up to 3,000 per source) and shows {shown_total:,}.",
        file=output,
    )
    print(
        "Review the original sources before publishing. "
        "A recent crawl is not a publication date, and neither a timestamp "
        "nor the presence of evidence establishes that a claim is true.",
        file=output,
    )

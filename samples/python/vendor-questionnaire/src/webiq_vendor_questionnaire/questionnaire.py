# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Send each question to each page, then pick the best sources for each answer."""

import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from .client import BrowseClient, Page, PageProblem
from .config import Vendor

MAX_SOURCES_PER_ANSWER = 2
WORKERS = 4

STOPWORDS = {
    "about", "after", "and", "any", "are", "before", "can", "does", "for", "from",
    "has", "have", "how", "into", "its", "our", "the", "their", "them", "there",
    "they", "this", "that", "used", "use", "uses", "what", "when", "where", "which",
    "who", "will", "with", "would", "you", "your",
    # Words in almost every questionnaire question, which don't help pick a page.
    "customer", "customers", "data", "information", "vendor", "vendors",
}
SUFFIXES = ("ations", "ation", "ions", "ion", "ing", "ed", "es", "s", "age")


@dataclass(frozen=True)
class Source:
    page: Page
    score: float


@dataclass(frozen=True)
class Answer:
    question: str
    sources: tuple[Source, ...]
    # Every page that returned passages for this question: the input for a model.
    pages: tuple[Page, ...]


@dataclass(frozen=True)
class Results:
    answers: tuple[Answer, ...]
    problems: tuple[PageProblem, ...]
    passages: int
    characters: int


def collect(
    client: BrowseClient,
    vendor: Vendor,
    questions: tuple[str, ...],
    *,
    live_crawl: bool = False,
    progress: Callable[[str], None] | None = None,
) -> list[list[Page | PageProblem]]:
    """Return results[question][page]. Indexed pages run in parallel; live crawls one at a time."""
    pairs = [(q, p) for q in range(len(questions)) for p in range(len(vendor.pages))]
    results: list[list[Page | PageProblem | None]] = [
        [None] * len(vendor.pages) for _ in questions
    ]

    def run(pair: tuple[int, int], crawl: bool) -> None:
        question, page = pair
        results[question][page] = client.browse(
            vendor.pages[page].url, questions[question], live_crawl=crawl
        )

    if progress:
        progress(f"Sending {len(pairs)} Browse requests ({len(questions)} questions x "
                 f"{len(vendor.pages)} pages)...")
    pool = ThreadPoolExecutor(max_workers=WORKERS)
    try:
        for future in [pool.submit(run, pair, False) for pair in pairs]:
            future.result()
    except BaseException:
        # A failure that stops the run (or Ctrl+C) cancels the queued requests.
        client.stop()
        pool.shutdown(wait=True, cancel_futures=True)
        raise
    pool.shutdown()

    if live_crawl:
        missing = [
            pair for pair in pairs
            if isinstance(results[pair[0]][pair[1]], PageProblem)
            and results[pair[0]][pair[1]].not_indexed
        ]
        if missing and progress:
            progress(f"Requesting live crawls for {len(missing)} requests, one at a time...")
        # Live crawl has a lower limit than indexed requests, so these run one at a time.
        for pair in missing:
            run(pair, True)

    return [[item for item in row if item is not None] for row in results]


def build_results(
    questions: tuple[str, ...], results: list[list[Page | PageProblem]]
) -> Results:
    answers: list[Answer] = []
    problems: dict[str, PageProblem] = {}
    passages = 0
    characters = 0
    for question, row in zip(questions, results):
        pages = tuple(item for item in row if isinstance(item, Page) and item.content.strip())
        for item in row:
            if isinstance(item, PageProblem):
                problems.setdefault(item.url, item)
        passages += len(pages)
        characters += sum(len(page.content) for page in pages)
        answers.append(Answer(question, rank_sources(question, pages), pages))
    return Results(tuple(answers), tuple(problems.values()), passages, characters)


def rank_sources(question: str, pages: tuple[Page, ...]) -> tuple[Source, ...]:
    """Rank pages by the question's distinctive words found in their passages.

    A simple keyword match, so the sample runs without a model. Words found on every
    page count less. A page needs at least one word that isn't on every page.
    """
    terms = keywords(question)
    if not terms or not pages:
        return ()
    page_terms = [keywords(page.content) for page in pages]
    document_frequency = {term: sum(term in found for found in page_terms) for term in terms}
    scored: list[Source] = []
    for page, found in zip(pages, page_terms):
        matched = terms & found
        if len(pages) > 1 and all(document_frequency[t] == len(pages) for t in matched):
            continue
        score = sum(1 / document_frequency[term] for term in matched)
        if score > 0:
            scored.append(Source(page, score))
    scored.sort(key=lambda source: source.score, reverse=True)
    return tuple(scored[:MAX_SOURCES_PER_ANSWER])


def best_segment(question: str, content: str) -> str:
    """Return the passage segment or sentence that contains the most question words."""
    terms = keywords(question)
    segments = [
        segment.strip()
        for part in re.split(r"\s\.\.\.\s", content)
        for segment in re.split(r"(?<=[.!?])\s+", part)
        if segment.strip()
    ]
    if not segments:
        return ""
    return max(segments, key=lambda segment: len(terms & keywords(segment)))


def keywords(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {stem(word) for word in words if len(word) >= 3 and word not in STOPWORDS}


def stem(word: str) -> str:
    for suffix in SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    return word

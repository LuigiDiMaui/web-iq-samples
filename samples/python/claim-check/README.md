# Web IQ Auto: claim check

Review current evidence for a statement before you publish an article or product page. Paste a claim, call [Auto](https://learn.microsoft.com/en-us/web-iq/reference/auto) once, and inspect each returned evidence item with its own sources and how recent they are.

The sample calls the Auto REST API directly. It doesn't call a model and doesn't produce a true/false verdict. Retrieved content stays in memory for the current run: no files, database, cache, or export.

## What the user does

1. Paste one statement from a draft, up to 1,000 characters.
2. Get web and news evidence, with each citation kept beside the item it supports.
3. Check each source's title, URL, `lastUpdatedAt`, and `crawledAt`, then open the original sources before deciding what to publish.

An empty result doesn't refute a claim. A recent crawl time doesn't prove that a source's content is recent, correct, or supports the statement.

## Prerequisites

- Python 3.11 or later
- An interactive terminal
- A [Web IQ API key](https://learn.microsoft.com/en-us/web-iq/get-started/quickstart) whose application is enabled for Auto, with web and news access

Requests incur [Web IQ charges](https://learn.microsoft.com/en-us/web-iq/resources/pricing). No SDK, model account, or model deployment is needed.

## Get started

Run these commands from this sample's directory.

### Windows (PowerShell)

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install .
$env:WEBIQ_API_KEY = "<your Web IQ API key>"
webiq-claim-check
```

### macOS/Linux (Bash)

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
export WEBIQ_API_KEY="<your Web IQ API key>"
webiq-claim-check
```

Paste a public statement at the prompt, for example:

```text
The Eiffel Tower is taller than 300 metres.
```

Use the prompt rather than passing sensitive draft text on the command line, where shell history can keep it. Keep keys out of source control and use an approved secret store in production.

## Options

| Command | Use it when |
| --- | --- |
| `webiq-claim-check` | You want a quick first look. `lite` prioritizes speed. |
| `webiq-claim-check --mode advanced` | A more comprehensive evidence search matters more than latency. |
| `webiq-claim-check --language en --region US` | You want to set the interface language and market. These are the defaults. |
| `webiq-claim-check --help` | You want to see the options without a key or a network call. |

Neither mode verifies truth. There's no automatic mode switch and no hidden model call.

## Request

The sample sends this request to `https://api.microsoft.ai/v3/auto` with the `x-apikey` header:

```json
{
  "query": "<the statement entered for this run>",
  "mode": "lite",
  "language": "en",
  "region": "US",
  "maxResponseLength": 30000,
  "responseFilter": ["web", "news"]
}
```

`maxResponseLength` is a budget for the whole response, not a promise of a number of sources or characters per source.

## What the sample keeps and what it shows

**Evidence kept for the run**: at most 10 distinct source URLs and 3,000 characters per source, in the order the service returns them. An item that cites several sources keeps all its citations, and its text counts toward each of them. If an item's citations don't fit, or one is unusable, the whole item is skipped with a warning. This is the evidence your model would receive (see [Add your own model](#add-your-own-model)).

**What the terminal shows**: at most 200 characters from each source, cut at a word boundary, with the source's title, link, and dates next to it. An excerpt from an item with several sources counts toward each of them. Each item shows how many characters were returned and how many are shown, and the run ends with the totals, for example:

```text
[1] Evidence (1,719 characters returned, 194 shown)
    "Synthetic evidence for demonstration only. Synthetic evidence for demonstration only. Synthetic evidence for demonstration only. Synthetic evidence for demonstration only. Synthetic evidence for..."
  Source 1: Example source
    URL: https://example.com/synthetic-source
    Content source: web
    Last updated: 2026-11-05T12:00:00Z (1 day ago)
    Crawled: 2026-11-06T06:00:00Z (6 hours ago)

Auto returned 1,719 characters of evidence from 1 source(s). This sample keeps 1,719 for a model in this run (up to 3,000 per source) and shows 194.
```

This example uses synthetic text and a reserved example domain, not saved API output. Ages assume a run at `2026-11-06T12:00:00Z`.

The 200-character limit follows the Use and Display Requirements in the [Web IQ Terms of Use](https://www.microsoft.com/en-us/webiq/webiq-legal). A website owner can set a lower maximum, which the sample can't detect.

## Freshness

`lastUpdatedAt` and `crawledAt` are shown separately, each with its age at the time of the run. Missing values are labeled unknown, timestamps without a time zone get no age, and future timestamps are flagged. The sample never invents a publication date.

## Reliability and errors

The client uses a 10-second connection timeout, 30-second read, write, and pool timeouts, and at most three attempts.

HTTP 429 and transient 408, 500, 502, 503, and 504 responses, plus network errors, are retried with exponential backoff and jitter. The sample respects both the `Retry-After` header and the `retryAfter` field in the JSON error, and waits for the longer one. Invalid guidance, or a required wait over 60 seconds, stops the run instead of retrying early. An exhausted daily quota isn't retried.

| Outcome | What the sample does |
| --- | --- |
| Missing key or invalid input | Stops before any network call, with a clear message. |
| HTTP 401 | Asks you to check the key and whether it expired. No retry. |
| HTTP 403 | Asks you to confirm the application is enabled for Auto. No retry. |
| HTTP 429 | Retries within the limits above, or reports an exhausted quota or a required wait. |
| Invalid JSON or response shape | Reports an error instead of treating it as evidence. |
| Empty result | Reports that no usable evidence came back, without a verdict. |
| Unsupported evidence or unusable citations | Warns and skips the whole item. |

Error messages don't echo service response bodies, claims, keys, or retrieved content. Known error codes and well-formed trace IDs are shown so you can quote them to support. Redirects aren't followed. Exit codes: 0 for a completed request (including an empty result), 1 for errors, 2 for invalid options, 130 for a cancelled run.

## Add your own model

No model runs in this sample. To ground your own model, pass `selection.items` to it in `main()` in `cli.py`, right after `select_evidence(response)`, in the same request.

Keep each item's text with that item's citations. Treat retrieved content as untrusted data, not instructions. Ask for grounded references, handle conflicting or missing evidence, and keep a human review step. Model costs, data handling, and retention are your application's responsibility. Don't add storage for the evidence.

## Data handling

This is a developer sample, not a ready-made fact-checking application. Before you build on it, review the [Web IQ Terms of Use](https://www.microsoft.com/en-us/webiq/webiq-legal), including section 2.5, the Use and Display Requirements in Exhibit A, and section 3.2.15 on storing and caching. Not storing results doesn't on its own meet every use and display requirement.

The sample writes no result files, caches, or logs, calls no model, and sends no telemetry. It refuses to run when its output is redirected or piped. Terminal software, shell history, session recording, debuggers, and proxies can still keep data outside the sample's control, so don't record, redirect, log, or save retrieved content.

Claims are sent to Web IQ, so use only text you're authorized to send. For how Web IQ handles requests, see the [Web IQ privacy guidance](https://learn.microsoft.com/en-us/web-iq/resources/faq#privacy-and-data-handling).

## Contribute

Install in editable mode, then run the offline tests. They use synthetic data and a mock service, so they need no key or network access:

```text
python -m pip install -e ".[dev]"
pytest
```

For a live check, run `webiq-claim-check` in an interactive terminal with an Auto-enabled key, enter a public claim, and check the sources and freshness labels. Each run, including `--mode advanced`, is a billable request.

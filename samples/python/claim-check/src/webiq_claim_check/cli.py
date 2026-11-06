# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Command-line entry point for the claim check sample."""

import argparse
import os
import sys

from .client import AutoError, search_auto
from .display import render_evidence
from .evidence import select_evidence


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="webiq-claim-check",
        description="Inspect current Auto evidence for a claim without a model or saved results.",
    )
    parser.add_argument(
        "claim", nargs="?", help="A statement to inspect; omitted means prompt for it."
    )
    parser.add_argument(
        "--mode",
        choices=("fast", "advanced"),
        default="fast",
        help="fast prioritizes speed; advanced prioritizes comprehensiveness (default: fast).",
    )
    parser.add_argument(
        "--language", default="en", help="Two-letter interface language (default: en)."
    )
    parser.add_argument(
        "--region", default="US", help="Two-letter market region (default: US)."
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if not sys.stdout.isatty():
            raise ValueError(
                "Run in an interactive terminal. Redirecting or piping retrieved evidence "
                "is disabled; this sample does not save results."
            )
        api_key = os.environ.get("WEBIQ_API_KEY")
        if not api_key or not api_key.strip():
            raise ValueError("Set WEBIQ_API_KEY to an API key with Auto access.")
        claim = (
            args.claim
            if args.claim is not None
            else input("Paste one claim (1-1,000 characters): ")
        )
        response = search_auto(
            api_key, claim, mode=args.mode, language=args.language, region=args.region
        )
        selection = select_evidence(response)
        # To ground your own model, pass selection.items to it here, in this request,
        # keeping each item's text with its citations. Don't store the evidence.
        for warning in selection.warnings:
            print(f"Warning: {warning}", file=sys.stderr)
        render_evidence(claim, selection, sys.stdout)
        return 0
    except EOFError:
        print(
            "Error: No claim was entered. Run again in an interactive terminal.",
            file=sys.stderr,
        )
        return 1
    except (AutoError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 130
    except BrokenPipeError:
        return 1


def entrypoint() -> None:
    raise SystemExit(main())

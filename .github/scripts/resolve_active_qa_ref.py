#!/usr/bin/env python3
"""Resolve one writable QA branch from an exact public deployment SHA."""

from __future__ import annotations

import argparse
import re
import sys


SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
QA_REF_PREFIXES = (
    "refs/heads/codex/",
    "refs/heads/homepages-agent/",
)


def resolve_ref(
    lines: list[str], *, sha: str, aggregate_ref: str, optional: bool = False
) -> str:
    if not SHA_PATTERN.fullmatch(sha):
        raise ValueError(f"Public QA source is not an exact commit SHA: {sha}")
    if not aggregate_ref.startswith("refs/heads/"):
        raise ValueError(f"Aggregate QA ref is not a branch: {aggregate_ref}")

    exact_refs: list[str] = []
    for line in lines:
        parts = line.split()
        if len(parts) == 2 and parts[0] == sha:
            exact_refs.append(parts[1])

    if aggregate_ref in exact_refs:
        return aggregate_ref

    candidates = sorted(
        ref
        for ref in exact_refs
        if ref != "refs/heads/main" and ref.startswith(QA_REF_PREFIXES)
    )
    if len(candidates) == 1:
        return candidates[0]
    if not candidates and optional:
        return ""
    if not candidates:
        raise ValueError(
            f"No writable registered QA branch points to public source {sha}"
        )
    raise ValueError(
        f"Multiple writable QA branches point to public source {sha}: "
        + ", ".join(candidates)
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sha", required=True)
    parser.add_argument("--aggregate-ref", required=True)
    parser.add_argument("--optional", action="store_true")
    args = parser.parse_args()
    try:
        resolved = resolve_ref(
            sys.stdin.read().splitlines(),
            sha=args.sha,
            aggregate_ref=args.aggregate_ref,
            optional=args.optional,
        )
    except ValueError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    print(resolved)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

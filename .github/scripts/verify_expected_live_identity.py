"""Refuse a deploy when the live site is not the version the caller built on.

Read from the deploy target's own storage (not the CDN), immediately before the
upload inside the per-site deploy queue, so a deploy prepared on an older live
version can never silently overwrite newer work. Exit 3 means "live changed".
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

from publish_deployment_identity import identity_object


LIVE_CHANGED = 3
_SHA = re.compile(r"^[0-9a-f]{40}$")


def read_live_identity(*, config: Path, target_name: str, runner=subprocess.run) -> tuple[str, str]:
    """Return (source SHA, "") or ("", short reason) when absent or unreadable."""

    uri, extra = identity_object(config=config, target_name=target_name)
    completed = runner(["aws", "s3", "cp", uri, "-", *extra], capture_output=True, text=True)
    if completed.returncode != 0:
        detail = " ".join(str(getattr(completed, "stderr", "") or "").split())[:200]
        return "", f"storage read failed ({detail or 'no detail'})"
    try:
        payload = json.loads(completed.stdout)
    except ValueError:
        return "", "stored identity is not valid JSON"
    source = payload.get("source_sha") if isinstance(payload, dict) else ""
    source = str(source or "").strip().lower()
    return source, "" if source else "stored identity has no source_sha"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--target", required=True)
    parser.add_argument("--expected", required=True)
    return parser


def main(argv: list[str] | None = None, runner=subprocess.run) -> int:
    args = build_parser().parse_args(argv)
    expected = args.expected.strip().lower()
    if not _SHA.fullmatch(expected):
        print("::error::expected_live_sha must be a full 40-character commit SHA.")
        return 2
    live, reason = read_live_identity(config=args.config, target_name=args.target, runner=runner)
    if live != expected:
        print(
            f"::error::Live target {args.target} serves {live or reason}, "
            f"not the expected {expected}; refusing to deploy over newer work."
        )
        return LIVE_CHANGED
    print(f"Live target {args.target} is the expected {expected}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

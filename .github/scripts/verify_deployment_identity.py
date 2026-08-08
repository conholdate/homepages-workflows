from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from write_deployment_identity import deployment_identity


def verify_identity(
    *,
    identity: Path,
    source_sha: str,
    site: str,
    environment: str,
    run_id: int,
    run_attempt: int,
) -> None:
    payload = json.loads(identity.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Deployment identity must be a JSON object.")
    generated_at = payload.get("generated_at_utc")
    if not isinstance(generated_at, str):
        raise ValueError("Deployment identity has no generated_at_utc value.")
    datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    expected = deployment_identity(
        source_sha=source_sha,
        site=site,
        environment=environment,
        run_id=run_id,
        run_attempt=run_attempt,
        generated_at_utc=generated_at,
    )
    if payload != expected:
        raise ValueError("Deployment identity does not match the exact requested source and workflow run.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify an exact existing deployment identity artifact.")
    parser.add_argument("--identity", required=True, type=Path)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--site", required=True)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--run-attempt", required=True, type=int)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    verify_identity(
        identity=args.identity,
        source_sha=args.source_sha,
        site=args.site,
        environment=args.environment,
        run_id=args.run_id,
        run_attempt=args.run_attempt,
    )
    print("deployment identity verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

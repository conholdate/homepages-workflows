from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re


SCHEMA_VERSION = 1
KIND = "homepages-deployment-identity"
HOMEPAGES_REPOSITORY = "conholdate/homepages"
WORKFLOW_REPOSITORY = "conholdate/homepages-workflows"
PUBLIC_IDENTITY_PATH = Path(".well-known/homepages-deployment.json")
EVIDENCE_FILE = "homepages-deployment.json"
_SOURCE_SHA_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_SITE_RE = re.compile(r"^[a-z0-9.-]+$")


def deployment_identity(
    *,
    source_sha: str,
    site: str,
    environment: str,
    run_id: int,
    run_attempt: int,
    generated_at_utc: str | None = None,
) -> dict[str, object]:
    source_sha = source_sha.strip().lower()
    site = site.strip().lower()
    environment = environment.strip().lower()
    if not _SOURCE_SHA_RE.fullmatch(source_sha):
        raise ValueError("source_sha must be a full hexadecimal Git object id")
    if not _SITE_RE.fullmatch(site):
        raise ValueError("site must be a lowercase managed domain")
    if environment not in {"qa", "production"}:
        raise ValueError("environment must be qa or production")
    if run_id <= 0 or run_attempt <= 0:
        raise ValueError("workflow run id and attempt must be positive")
    timestamp = generated_at_utc or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "repository": HOMEPAGES_REPOSITORY,
        "source_sha": source_sha,
        "site": site,
        "environment": environment,
        "workflow": {
            "repository": WORKFLOW_REPOSITORY,
            "run_id": run_id,
            "run_attempt": run_attempt,
        },
        "generated_at_utc": timestamp,
    }


def write_identity(
    *,
    output_root: Path,
    evidence_dir: Path,
    payload: dict[str, object],
) -> tuple[Path, Path]:
    endpoint = output_root / PUBLIC_IDENTITY_PATH
    evidence = evidence_dir / EVIDENCE_FILE
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    endpoint.parent.mkdir(parents=True, exist_ok=True)
    evidence.parent.mkdir(parents=True, exist_ok=True)
    endpoint.write_text(rendered, encoding="utf-8")
    evidence.write_text(rendered, encoding="utf-8")
    return endpoint, evidence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Write public, non-secret homepage deployment identity.")
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--site", required=True)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--run-attempt", required=True, type=int)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--evidence-dir", required=True, type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    payload = deployment_identity(
        source_sha=args.source_sha,
        site=args.site,
        environment=args.environment,
        run_id=args.run_id,
        run_attempt=args.run_attempt,
    )
    endpoint, evidence = write_identity(
        output_root=args.output_root,
        evidence_dir=args.evidence_dir,
        payload=payload,
    )
    print(f"deployment identity endpoint: {endpoint}")
    print(f"deployment identity evidence: {evidence}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import tomllib
from urllib.parse import parse_qs, urlsplit


PUBLIC_IDENTITY_PATH = ".well-known/homepages-deployment.json"


def upload_command(*, config: Path, target_name: str, identity: Path) -> list[str]:
    data = tomllib.loads(config.read_text(encoding="utf-8-sig"))
    deployment = data.get("deployment")
    targets = deployment.get("targets") if isinstance(deployment, dict) else None
    matches = [
        item
        for item in targets or []
        if isinstance(item, dict) and str(item.get("name") or "") == target_name
    ]
    if len(matches) != 1:
        raise ValueError(f"Expected one deployment target named {target_name!r}; found {len(matches)}.")

    raw_url = str(matches[0].get("URL") or matches[0].get("url") or "").strip()
    parsed = urlsplit(raw_url)
    if parsed.scheme != "s3" or not parsed.netloc or "@" in parsed.netloc:
        raise ValueError("Deployment identity publishing requires a credential-free s3 target URL.")
    query = parse_qs(parsed.query, keep_blank_values=True)
    unknown = sorted(set(query) - {"endpoint", "region"})
    if unknown:
        raise ValueError("Unsupported deployment target query fields: " + ", ".join(unknown))

    prefix = parsed.path.strip("/")
    key = "/".join(part for part in (prefix, PUBLIC_IDENTITY_PATH) if part)
    command = [
        "aws",
        "s3",
        "cp",
        str(identity),
        f"s3://{parsed.netloc}/{key}",
        "--content-type",
        "application/json",
        "--cache-control",
        "no-store, max-age=0",
    ]
    endpoint = (query.get("endpoint") or [""])[-1].strip()
    region = (query.get("region") or [""])[-1].strip()
    if endpoint:
        if urlsplit(endpoint).scheme != "https":
            raise ValueError("Deployment target endpoint must use HTTPS.")
        command.extend(("--endpoint-url", endpoint))
    if region:
        command.extend(("--region", region))
    return command


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Publish the generated deployment identity excluded by Hugo's hidden-path filter."
    )
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--target", required=True)
    parser.add_argument("--identity", required=True, type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not args.identity.is_file():
        raise FileNotFoundError(f"Deployment identity does not exist: {args.identity}")
    command = upload_command(config=args.config, target_name=args.target, identity=args.identity)
    subprocess.run(command, check=True)
    print(f"published deployment identity for target: {args.target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

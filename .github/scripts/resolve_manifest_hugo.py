from __future__ import annotations

import argparse
from pathlib import Path
import re


_VERSION = re.compile(r"\d+\.\d+\.\d+")


def resolve_manifest_hugo(text: str, *, site: str, environment: str) -> str:
    if environment not in {"qa", "production"}:
        raise ValueError("environment must be qa or production")
    header = f"  {site}:"
    lines = text.replace("\r\n", "\n").splitlines()
    try:
        start = lines.index(header) + 1
    except ValueError as exc:
        raise ValueError(f"site is not registered: {site}") from exc
    key = "stage_hugo" if environment == "qa" else "production_hugo"
    values: list[str] = []
    for line in lines[start:]:
        if line.startswith("  ") and not line.startswith("    "):
            break
        match = re.fullmatch(rf"    {key}:\s*['\"]?([^\s'\"]+)['\"]?\s*", line)
        if match:
            values.append(match.group(1))
    if len(values) != 1 or not _VERSION.fullmatch(values[0]):
        raise ValueError(f"{site} has no unique valid {key} contract")
    return values[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--site", required=True)
    parser.add_argument("--environment", choices=("qa", "production"), required=True)
    args = parser.parse_args()
    print(
        resolve_manifest_hugo(
            args.manifest.read_text(encoding="utf-8-sig"),
            site=args.site.strip(),
            environment=args.environment,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

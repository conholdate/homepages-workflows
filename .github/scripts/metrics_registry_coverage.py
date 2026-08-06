#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import yaml


COVERAGE_FIELD = "HOMEPAGES_METRICS_COVERED_SITES"


def _registered_sites(registry_path: Path) -> set[str]:
    data = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    sites = data.get("sites") if isinstance(data, dict) else {}
    if not isinstance(sites, dict):
        return set()
    return {
        str(site)
        for site, config in sites.items()
        if isinstance(config, dict)
        and isinstance(config.get("metrics"), dict)
        and any(
            isinstance(metric, dict) and metric.get("enabled") is True
            for metric in config["metrics"].values()
        )
    }


def _coverage_values(value: object) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key == COVERAGE_FIELD and isinstance(child, str):
                found.extend(child.split())
            else:
                found.extend(_coverage_values(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_coverage_values(child))
    return found


def _scheduled_sites(workflow_dir: Path) -> tuple[set[str], set[str]]:
    owners: dict[str, int] = {}
    for path in sorted(workflow_dir.glob("*.yml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for site in _coverage_values(data):
            owners[site] = owners.get(site, 0) + 1
    duplicates = {site for site, count in owners.items() if count > 1}
    return set(owners), duplicates


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify registered metrics sites have one scheduled workflow owner.")
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--workflow-dir", type=Path, required=True)
    args = parser.parse_args()

    registered = _registered_sites(args.registry)
    scheduled, duplicates = _scheduled_sites(args.workflow_dir)
    missing = sorted(registered - scheduled)
    unknown = sorted(scheduled - registered)
    if missing:
        print(f"Missing scheduled metrics coverage: {', '.join(missing)}")
    if unknown:
        print(f"Scheduled metrics coverage has no enabled registry metrics: {', '.join(unknown)}")
    if duplicates:
        print(f"Metrics sites have multiple scheduled workflow owners: {', '.join(sorted(duplicates))}")
    if missing or unknown or duplicates:
        return 1
    print(f"Metrics schedule coverage OK: {', '.join(sorted(registered))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env bash
set -euo pipefail

paths=("$@")
if [ "$#" -eq 0 ]; then
  mapfile -t paths < <(git diff --cached --name-only)
fi

bad_paths=()
for path in "${paths[@]}"; do
  [ -n "$path" ] || continue
  if [[ "$path" != "data/products.json" && ! "$path" =~ ^data/metrics/[^/]+\.json$ ]]; then
    bad_paths+=("$path")
  fi
done

if [ "${#bad_paths[@]}" -ne 0 ]; then
  echo "::error::Metrics refresh may commit only data/products.json and data/metrics/*.json"
  printf 'Out-of-scope path: %s\n' "${bad_paths[@]}"
  exit 1
fi

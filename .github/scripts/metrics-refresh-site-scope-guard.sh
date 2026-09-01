#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "Usage: $0 <site> [changed-path ...]" >&2
  exit 2
fi

site="$1"
shift
expected="data/metrics/${site}.json"

for path in "$@"; do
  [ -n "${path}" ] || continue
  if [ "${path}" != "${expected}" ]; then
    echo "::error::Production metrics refresh for ${site} may change only ${expected}"
    echo "Out-of-scope path: ${path}"
    exit 1
  fi
done

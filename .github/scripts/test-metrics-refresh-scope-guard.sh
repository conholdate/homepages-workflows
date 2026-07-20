#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
guard="${script_dir}/metrics-refresh-scope-guard.sh"

"${guard}" data/products.json data/metrics/aspose.com.json data/metrics/aspose.cloud.json

if "${guard}" data/metrics/aspose.com.json README.md >/tmp/metrics-refresh-guard.out 2>&1; then
  echo "Expected out-of-scope path to fail"
  exit 1
fi

grep -q "Out-of-scope path: README.md" /tmp/metrics-refresh-guard.out

if "${guard}" data/metrics/nested/aspose.com.json >/tmp/metrics-refresh-guard-nested.out 2>&1; then
  echo "Expected nested metrics path to fail"
  exit 1
fi

grep -q "Out-of-scope path: data/metrics/nested/aspose.com.json" /tmp/metrics-refresh-guard-nested.out

if "${guard}" data/families_order.json >/tmp/metrics-refresh-guard-data.out 2>&1; then
  echo "Expected unrelated data file to fail"
  exit 1
fi

grep -q "Out-of-scope path: data/families_order.json" /tmp/metrics-refresh-guard-data.out

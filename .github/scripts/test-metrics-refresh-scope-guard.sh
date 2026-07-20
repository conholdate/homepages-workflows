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

tmp_repo="$(mktemp -d)"
trap 'rm -rf "${tmp_repo}"' EXIT
git -C "${tmp_repo}" init -q
mkdir -p "${tmp_repo}/data/metrics"
printf '{}\n' > "${tmp_repo}/data/products.json"
printf '{}\n' > "${tmp_repo}/data/metrics/aspose.com.json"
git -C "${tmp_repo}" add data/products.json data/metrics/aspose.com.json
printf 'unexpected\n' > "${tmp_repo}/README.md"
if (cd "${tmp_repo}" && "${guard}") >/tmp/metrics-refresh-guard-worktree.out 2>&1; then
  echo "Expected unstaged or untracked out-of-scope path to fail"
  exit 1
fi
grep -q "Out-of-scope path: README.md" /tmp/metrics-refresh-guard-worktree.out

#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
workflow="${script_dir}/../workflows/metrics-refresh.yml"
site_guard="${script_dir}/metrics-refresh-site-scope-guard.sh"

grep -q 'Synchronize QA homepage deployments' "${workflow}"
grep -q 'environment=qa' "${workflow}"
grep -q 'Refresh production metrics from exact live sources' "${workflow}"
grep -q 'public_production_source' "${workflow}"
grep -Fq "git checkout -B production-metrics-refresh \"\${current_production_sha}\"" "${workflow}"
grep -q 'metrics-refresh-site-scope-guard.sh' "${workflow}"
grep -q 'environment=production' "${workflow}"

for forbidden in 'refresh_branch main' 'steps.refresh.outputs.main_sha'; do
  if grep -q "${forbidden}" "${workflow}"; then
    echo "Production metrics refresh must not derive from main: ${forbidden}"
    exit 1
  fi
done

bash "${site_guard}" aspose.ai data/metrics/aspose.ai.json
for forbidden in \
  data/metrics/aspose.app.json \
  data/products.json \
  themes/homepage-v2-theme/layouts/partials/structured-home-claude-inspired-v1.html; do
  if bash "${site_guard}" aspose.ai "${forbidden}" >/tmp/metrics-refresh-site-guard.out 2>&1; then
    echo "Expected ${forbidden} to fail the exact-site production guard"
    exit 1
  fi
  grep -q "Out-of-scope path: ${forbidden}" /tmp/metrics-refresh-site-guard.out
done

tmp_repo="$(mktemp -d)"
trap 'rm -rf "${tmp_repo}"' EXIT
git -C "${tmp_repo}" init -q
git -C "${tmp_repo}" config user.name test
git -C "${tmp_repo}" config user.email test@example.com
mkdir -p "${tmp_repo}/data/metrics" "${tmp_repo}/themes/homepage-v2-theme/layouts/partials"
printf 'old-metrics\n' > "${tmp_repo}/data/metrics/aspose.ai.json"
printf 'live-renderer\n' > "${tmp_repo}/themes/homepage-v2-theme/layouts/partials/structured-home-claude-inspired-v1.html"
git -C "${tmp_repo}" add .
git -C "${tmp_repo}" commit -qm production
production_sha="$(git -C "${tmp_repo}" rev-parse HEAD)"

printf 'new-metrics\n' > "${tmp_repo}/data/metrics/aspose.ai.json"
printf 'unapproved-renderer\n' > "${tmp_repo}/themes/homepage-v2-theme/layouts/partials/structured-home-claude-inspired-v1.html"
git -C "${tmp_repo}" commit -qam aggregate
metrics_source_sha="$(git -C "${tmp_repo}" rev-parse HEAD)"

git -C "${tmp_repo}" checkout -q "${production_sha}"
git -C "${tmp_repo}" checkout "${metrics_source_sha}" -- data/metrics/aspose.ai.json
mapfile -t changed_paths < <(git -C "${tmp_repo}" diff --cached --name-only)
bash "${site_guard}" aspose.ai "${changed_paths[@]}"
test "$(cat "${tmp_repo}/data/metrics/aspose.ai.json")" = "new-metrics"
test "$(cat "${tmp_repo}/themes/homepage-v2-theme/layouts/partials/structured-home-claude-inspired-v1.html")" = "live-renderer"

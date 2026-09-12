#!/usr/bin/env bash
# Shared exact-live-parent metrics publisher; no content or feed promotion.
set -euo pipefail
refreshed_sites="${METRICS_REFRESH_SITES:-}"
read -r -a sites <<< "${refreshed_sites}"
if [ "${#sites[@]}" -eq 0 ]; then
  echo "::error::No successfully refreshed production sites were reported"
  exit 1
fi
printf 'sites=%s\n' "${refreshed_sites}" >> "${GITHUB_OUTPUT}"

if [ -z "${HOMEPAGES_SOURCE_PAT:-}" ]; then
  echo "::error::Missing HOMEPAGES_SOURCE_PAT"
  exit 1
fi
if [[ ! "${METRICS_SOURCE_SHA}" =~ ^[0-9a-f]{40}$ ]]; then
  echo "::error::Metrics source is not an exact commit SHA: ${METRICS_SOURCE_SHA}"
  exit 1
fi

auth_header="$(printf 'x-access-token:%s' "${HOMEPAGES_SOURCE_PAT}" | base64 -w0)"
homepages_repo="${GITHUB_WORKSPACE}/homepages"
workflows_repo="${GITHUB_WORKSPACE}/workflows"
candidate_heads="$(git -C "${homepages_repo}" -c "http.https://github.com/.extraheader=AUTHORIZATION: basic ${auth_header}" \
  ls-remote --heads origin)"

public_production_source() {
  local site="$1"
  local cache_key="$2"
  local identity
  local source_sha
  identity="$(curl -fsS --compressed --max-time 20 \
    "https://www.${site}/.well-known/homepages-deployment.json?metrics-refresh=${cache_key}" || true)"
  source_sha="$(jq -r '.source_sha // ""' <<<"${identity}" 2>/dev/null || true)"
  if [[ ! "${source_sha}" =~ ^[0-9a-f]{40}$ ]] || \
    [ "$(jq -r '.repository // ""' <<<"${identity}" 2>/dev/null || true)" != "conholdate/homepages" ] || \
    [ "$(jq -r '.site // ""' <<<"${identity}" 2>/dev/null || true)" != "${site}" ] || \
    [ "$(jq -r '.environment // ""' <<<"${identity}" 2>/dev/null || true)" != "production" ]; then
    echo "::error::Invalid public production identity for ${site}" >&2
    return 1
  fi
  printf '%s\n' "${source_sha}"
}

declare -A target_shas
declare -A run_ids
for site in "${sites[@]}"; do
  current_production_sha="$(public_production_source "${site}" "${GITHUB_RUN_ID}-parent-${site//./-}")"
  candidate_ref="refs/heads/homepages-agent/production-metrics-refresh/${site}"
  candidate_remote_sha="$(awk -v ref="${candidate_ref}" '$2 == ref {print $1}' <<<"${candidate_heads}")"

  cd "${homepages_repo}"
  if ! git cat-file -e "${current_production_sha}^{commit}" 2>/dev/null; then
    if ! git -c "http.https://github.com/.extraheader=AUTHORIZATION: basic ${auth_header}" \
      fetch origin "${current_production_sha}"; then
      echo "::error::Could not fetch exact public production source ${current_production_sha} for ${site}"
      exit 1
    fi
  fi
  git checkout -B production-metrics-refresh "${current_production_sha}"
  if [ "$(git rev-parse HEAD)" != "${current_production_sha}" ]; then
    echo "::error::Selected production metrics parent differs from public ${site}"
    exit 1
  fi

  git clean -fd -- "data/metrics/${site}.json"
  git checkout "${METRICS_SOURCE_SHA}" -- "data/metrics/${site}.json"
  mapfile -t changed_paths < <(git diff --cached --name-only)
  bash "${workflows_repo}/.github/scripts/metrics-refresh-site-scope-guard.sh" \
    "${site}" "${changed_paths[@]}"

  if git diff --cached --quiet; then
    candidate_sha="${current_production_sha}"
    echo "Production ${site} already has the refreshed metrics file at ${candidate_sha}."
  else
    git commit \
      -m "Refresh ${site} production metrics" \
      -m $'Co-authored-by: salmansarfraz <kh.salman.sarfraz@gmail.com>\nCo-authored-by: Codex <codex@openai.com>\nCo-authored-by: Homepages Agent <homepages.agent@conholdate.com>'
    candidate_sha="$(git rev-parse HEAD)"
    lease="${candidate_ref}:"
    if [ -n "${candidate_remote_sha}" ]; then
      lease="${candidate_ref}:${candidate_remote_sha}"
    fi
    git -c "http.https://github.com/.extraheader=AUTHORIZATION: basic ${auth_header}" \
      push --force-with-lease="${lease}" origin "HEAD:${candidate_ref}"
    echo "Prepared ${site} production metrics at ${candidate_sha} from exact live parent ${current_production_sha}."
  fi
  target_shas["${site}"]="${candidate_sha}"

  if [ "${candidate_sha}" = "${current_production_sha}" ]; then
    continue
  fi
  latest_production_sha="$(public_production_source "${site}" "${GITHUB_RUN_ID}-pre-dispatch-${site//./-}")"
  if [ "${latest_production_sha}" != "${current_production_sha}" ]; then
    echo "::error::Public production changed before metrics deployment for ${site}: expected ${current_production_sha}, found ${latest_production_sha}"
    exit 1
  fi

  transaction_id="metrics-refresh-${GITHUB_RUN_ID}-${site//./-}"
  gh workflow run deploy-homepage.yml \
    --repo "${GITHUB_REPOSITORY}" \
    --ref main \
    -f "site=${site}" \
    -f "environment=production" \
    -f "ref=${candidate_sha}" \
    -f "deploy=true" \
    -f "invalidate_cache=true" \
    -f "transaction_id=${transaction_id}"

  run_id=""
  for _ in $(seq 1 30); do
    runs_json="$(gh api "repos/${GITHUB_REPOSITORY}/actions/workflows/deploy-homepage.yml/runs?event=workflow_dispatch&per_page=100")"
    run_id="$(jq -r --arg marker "tx=${transaction_id}" '.workflow_runs | map(select(.display_title | contains($marker))) | sort_by(.created_at) | last | .id // empty' <<<"${runs_json}")"
    [ -n "${run_id}" ] && break
    sleep 2
  done
  if [ -z "${run_id}" ]; then
    echo "::error::Could not discover production deploy run for ${site} (${transaction_id})"
    exit 1
  fi
  run_ids["${site}"]="${run_id}"
  echo "Dispatched ${site} production metrics run ${run_id} at ${candidate_sha}."
done

for site in "${sites[@]}"; do
  target_sha="${target_shas[$site]}"
  run_id="${run_ids[$site]:-}"
  if [ -n "${run_id}" ]; then
    completed=false
    for _ in $(seq 1 180); do
      run_json="$(gh api "repos/${GITHUB_REPOSITORY}/actions/runs/${run_id}")"
      status="$(jq -r '.status' <<<"${run_json}")"
      conclusion="$(jq -r '.conclusion // ""' <<<"${run_json}")"
      if [ "${status}" = "completed" ]; then
        if [ "${conclusion}" != "success" ]; then
          echo "::error::Production deploy run ${run_id} for ${site} completed as ${conclusion}"
          exit 1
        fi
        completed=true
        break
      fi
      sleep 10
    done
    if [ "${completed}" != "true" ]; then
      echo "::error::Timed out waiting for production deploy run ${run_id} for ${site}"
      exit 1
    fi
  fi

  verified_source="$(public_production_source "${site}" "${GITHUB_RUN_ID}-verify-${site//./-}")"
  if [ "${verified_source}" != "${target_sha}" ]; then
    echo "::error::Public production did not converge for ${site}: expected ${target_sha}, found ${verified_source}"
    exit 1
  fi
  echo "Verified ${site} production metrics identity at ${target_sha}${run_id:+ (run ${run_id})}."
done

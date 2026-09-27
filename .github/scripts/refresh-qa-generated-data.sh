#!/usr/bin/env bash
# Shared QA generated-data publisher (D-067). For each site, place the refreshed
# generated files onto exactly what is live on QA (never older QA content), deploy
# with the live version it was built on, and retry a site whose QA changed
# underneath it, bounded to 3 rounds. Brand specifics are inputs, not code:
#   QA_REFRESH_SITES      space-separated sites
#   REFRESHED_SOURCE_SHA  commit holding the refreshed generated files
#   REFRESH_BASE_SHA      optional: commit the refresh was baked on; if QA still
#                         serves it, REFRESHED_SOURCE_SHA is deployed as is
#   GENERATED_PATHS       optional path templates ({site}, {key}); default metrics
#   REFRESH_SOURCE_REF    optional branch that must keep pointing at
#                         REFRESHED_SOURCE_SHA before and after the deploys
#   TRANSACTION_PREFIX    optional deploy transaction prefix; default metrics-refresh
set -euo pipefail

read -r -a sites <<< "${QA_REFRESH_SITES:-}"
if [ "${#sites[@]}" -eq 0 ]; then
  echo "::error::No successfully refreshed QA sites were reported"
  exit 1
fi
if [ -z "${HOMEPAGES_SOURCE_PAT:-}" ]; then
  echo "::error::Missing HOMEPAGES_SOURCE_PAT"
  exit 1
fi
if [[ ! "${REFRESHED_SOURCE_SHA:-}" =~ ^[0-9a-f]{40}$ ]]; then
  echo "::error::Refreshed QA source is not an exact commit SHA: ${REFRESHED_SOURCE_SHA:-}"
  exit 1
fi
# A separate default: "}" inside ${VAR:-...} would end the expansion early.
default_paths='data/metrics/{site}.json'
read -r -a path_templates <<< "${GENERATED_PATHS:-${default_paths}}"

auth_header="$(printf 'x-access-token:%s' "${HOMEPAGES_SOURCE_PAT}" | base64 -w0)"
homepages_repo="${GITHUB_WORKSPACE}/homepages"
workflows_repo="${GITHUB_WORKSPACE}/workflows"

git_auth() {
  git -C "${homepages_repo}" -c "http.https://github.com/.extraheader=AUTHORIZATION: basic ${auth_header}" "$@"
}
remote_ref_sha() {
  git_auth ls-remote origin "refs/heads/$1" | awk '{print $1}'
}
public_qa_source() {
  local site="$1"
  local cache_key="$2"
  local identity
  identity="$(curl -fsS --compressed --max-time 20 \
    "https://qa.${site}/.well-known/homepages-deployment.json?metrics-refresh=${cache_key}" || true)"
  if [ "$(jq -r '.repository // ""' <<<"${identity}" 2>/dev/null || true)" != "conholdate/homepages" ] || \
    [ "$(jq -r '.site // ""' <<<"${identity}" 2>/dev/null || true)" != "${site}" ] || \
    [ "$(jq -r '.environment // ""' <<<"${identity}" 2>/dev/null || true)" != "qa" ]; then
    return 0
  fi
  jq -r '.source_sha // ""' <<<"${identity}" 2>/dev/null || true
}
public_qa_has_noindex() {
  local html
  html="$(curl -fsS --compressed --max-time 20 "https://qa.$1/?metrics-refresh=$2" || true)"
  grep -Eiq '<meta[^>]*name="?robots"?[^>]*content="?[^>]*noindex' <<<"${html}"
}
site_paths() {
  local site="$1"
  local key="${site//./_}"
  local template path
  for template in "${path_templates[@]}"; do
    path="${template//\{site\}/${site}}"
    path="${path//\{key\}/${key}}"
    if ! git -C "${homepages_repo}" cat-file -e "${REFRESHED_SOURCE_SHA}:${path}" 2>/dev/null; then
      continue
    fi
    # Copy only what the refresh changed, so an untouched generated file never
    # reverts newer work on the live QA version.
    if [ -n "${REFRESH_BASE_SHA:-}" ] && \
      git -C "${homepages_repo}" diff --quiet "${REFRESH_BASE_SHA}" "${REFRESHED_SOURCE_SHA}" -- "${path}"; then
      continue
    fi
    printf '%s\n' "${path}"
  done
}

if [ -n "${REFRESH_SOURCE_REF:-}" ] && [ "$(remote_ref_sha "${REFRESH_SOURCE_REF}")" != "${REFRESHED_SOURCE_SHA}" ]; then
  echo "::error::QA source ref ${REFRESH_SOURCE_REF} drifted before deploy: expected ${REFRESHED_SOURCE_SHA}"
  exit 1
fi
if ! git -C "${homepages_repo}" cat-file -e "${REFRESHED_SOURCE_SHA}^{commit}" 2>/dev/null; then
  git_auth fetch origin "${REFRESHED_SOURCE_SHA}"
fi

declare -A target_shas
declare -A parent_shas
max_rounds=3
pending=("${sites[@]}")
for round in $(seq 1 "${max_rounds}"); do
  [ "${#pending[@]}" -eq 0 ] && break
  unset run_ids conflicted
  declare -A run_ids
  declare -A conflicted
  suffix=""
  [ "${round}" -gt 1 ] && suffix="-r${round}"
  candidate_heads="$(git_auth ls-remote --heads origin)"

  for site in "${pending[@]}"; do
    current_qa_sha="$(public_qa_source "${site}" "${GITHUB_RUN_ID}-candidate-${site//./-}${suffix}")"
    if [[ ! "${current_qa_sha}" =~ ^[0-9a-f]{40}$ ]]; then
      echo "::error::Public QA source is not an exact commit SHA for ${site}: ${current_qa_sha}"
      exit 1
    fi
    parent_shas["${site}"]="${current_qa_sha}"
    if [ "${current_qa_sha}" = "${REFRESHED_SOURCE_SHA}" ]; then
      target_shas["${site}"]="${current_qa_sha}"
      echo "QA ${site} already serves ${current_qa_sha}; no deploy needed."
      continue
    fi
    if [ -n "${REFRESH_BASE_SHA:-}" ] && [ "${current_qa_sha}" = "${REFRESH_BASE_SHA}" ]; then
      candidate_sha="${REFRESHED_SOURCE_SHA}"
    else
      recovery_ref="refs/heads/homepages-agent/qa-refresh/${site}"
      candidate_ref="$(printf '%s\n' "${candidate_heads}" | python \
        "${workflows_repo}/.github/scripts/resolve_active_qa_ref.py" \
        --sha "${current_qa_sha}" --aggregate-ref "refs/heads/${HOMEPAGES_QA_SOURCE_REF}" \
        --recovery-ref "${recovery_ref}")"
      candidate_remote_sha="$(awk -v ref="${candidate_ref}" '$2 == ref {print $1}' <<<"${candidate_heads}")"
      cd "${homepages_repo}"
      if ! git cat-file -e "${current_qa_sha}^{commit}" 2>/dev/null; then
        git_auth fetch origin "${current_qa_sha}"
      fi
      git checkout -q -B active-qa-generated-data-refresh "${current_qa_sha}"
      mapfile -t paths < <(site_paths "${site}")
      if [ "${#paths[@]}" -eq 0 ]; then
        if [ -z "${REFRESH_BASE_SHA:-}" ]; then
          echo "::error::Refreshed source has no generated files for ${site}"
          exit 1
        fi
        target_shas["${site}"]="${current_qa_sha}"
        echo "No generated-data change for ${site}; active QA ${current_qa_sha} is kept."
        continue
      fi
      for path in "${paths[@]}"; do
        git clean -fdq -- "${path}"
        git checkout "${REFRESHED_SOURCE_SHA}" -- "${path}"
      done
      unexpected="$(git diff --cached --name-only | grep -Fxv -f <(printf '%s\n' "${paths[@]}") || true)"
      if [ -n "${unexpected}" ]; then
        echo "::error::Generated-data refresh changed an unapproved path for ${site}: ${unexpected}"
        exit 1
      fi
      if git diff --cached --quiet; then
        candidate_sha="${current_qa_sha}"
        echo "No generated-data change for active QA ${site} at ${current_qa_sha}."
      else
        git commit \
          -m "Refresh ${site} generated homepage data" \
          -m $'Co-authored-by: salmansarfraz <kh.salman.sarfraz@gmail.com>\nCo-authored-by: Codex <codex@openai.com>\nCo-authored-by: Homepages Agent <homepages.agent@conholdate.com>'
        candidate_sha="$(git rev-parse HEAD)"
        git_auth push -q --force-with-lease="${candidate_ref}:${candidate_remote_sha}" origin "HEAD:${candidate_ref}"
        echo "Placed ${site} generated data on exact live QA ${current_qa_sha}; target ${candidate_sha}."
      fi
    fi
    target_shas["${site}"]="${candidate_sha}"
    if [ "${candidate_sha}" = "${current_qa_sha}" ]; then
      continue
    fi
    latest_qa_sha="$(public_qa_source "${site}" "${GITHUB_RUN_ID}-pre-dispatch-${site//./-}${suffix}")"
    if [ "${latest_qa_sha}" != "${current_qa_sha}" ]; then
      echo "::warning::Public QA changed before deploy for ${site} (round ${round}): expected ${current_qa_sha}, found ${latest_qa_sha}; rebuilding on the new live version."
      conflicted["${site}"]=1
      continue
    fi

    transaction_id="${TRANSACTION_PREFIX:-metrics-refresh}-${GITHUB_RUN_ID}-qa-${site//./-}${suffix}"
    gh workflow run deploy-homepage.yml \
      --repo "${GITHUB_REPOSITORY}" \
      --ref main \
      -f "site=${site}" \
      -f "environment=qa" \
      -f "ref=${candidate_sha}" \
      -f "deploy=true" \
      -f "invalidate_cache=true" \
      -f "transaction_id=${transaction_id}" \
      -f "expected_live_sha=${current_qa_sha}"
    run_id=""
    for _ in $(seq 1 30); do
      runs_json="$(gh api "repos/${GITHUB_REPOSITORY}/actions/workflows/deploy-homepage.yml/runs?event=workflow_dispatch&per_page=100")"
      run_id="$(jq -r --arg marker "tx=${transaction_id}" '.workflow_runs | map(select(.display_title | contains($marker))) | sort_by(.created_at) | last | .id // empty' <<<"${runs_json}")"
      [ -n "${run_id}" ] && break
      sleep 2
    done
    if [ -z "${run_id}" ]; then
      echo "::error::Could not discover QA deploy run for ${site} (${transaction_id})"
      exit 1
    fi
    run_ids["${site}"]="${run_id}"
    echo "Dispatched ${site} QA deploy run ${run_id} at ${candidate_sha}."
  done

  for site in "${pending[@]}"; do
    [ -n "${conflicted[$site]:-}" ] && continue
    target_sha="${target_shas[$site]}"
    run_id="${run_ids[$site]:-}"
    if [ -n "${run_id}" ]; then
      conclusion=""
      for _ in $(seq 1 180); do
        run_json="$(gh api "repos/${GITHUB_REPOSITORY}/actions/runs/${run_id}")"
        if [ "$(jq -r '.status' <<<"${run_json}")" = "completed" ]; then
          conclusion="$(jq -r '.conclusion // ""' <<<"${run_json}")"
          break
        fi
        sleep 10
      done
      if [ -z "${conclusion}" ]; then
        echo "::error::Timed out waiting for QA deploy run ${run_id} for ${site}"
        exit 1
      fi
      if [ "${conclusion}" != "success" ]; then
        # Retry only when another deploy won (live is a valid version that is neither
        # our parent nor our own candidate) or our queued run was cancelled.
        live_now="$(public_qa_source "${site}" "${GITHUB_RUN_ID}-conflict-${site//./-}${suffix}")"
        if [ "${conclusion}" = "cancelled" ] || { [[ "${live_now}" =~ ^[0-9a-f]{40}$ ]] && \
          [ "${live_now}" != "${parent_shas[$site]}" ] && [ "${live_now}" != "${target_sha}" ]; }; then
          echo "::warning::QA ${site} changed during the deploy (round ${round}, ${conclusion}); rebuilding on the new live version ${live_now:-unknown}."
          conflicted["${site}"]=1
          continue
        fi
        if [ "${live_now}" = "${target_sha}" ]; then
          echo "::error::QA ${site} now serves ${target_sha}, but deploy run ${run_id} completed as ${conclusion} (for example a failed cache purge); cached pages may be stale"
        else
          echo "::error::QA deploy run ${run_id} for ${site} completed as ${conclusion}"
        fi
        exit 1
      fi
    fi

    verified=false
    for attempt in $(seq 1 60); do
      if [ "$(public_qa_source "${site}" "${GITHUB_RUN_ID}-after-${site//./-}${suffix}-${attempt}")" = "${target_sha}" ]; then
        verified=true
        break
      fi
      sleep 10
    done
    if [ "${verified}" != "true" ]; then
      echo "::error::Public QA deployment identity did not converge for ${site} at ${target_sha}"
      exit 1
    fi
    if ! public_qa_has_noindex "${site}" "${GITHUB_RUN_ID}-noindex-${site//./-}${suffix}"; then
      echo "::error::Public QA root is missing robots noindex for ${site} at ${target_sha}"
      exit 1
    fi
    echo "Verified ${site} QA identity at ${target_sha}${run_id:+ (run ${run_id})}."
  done

  next=()
  for site in "${pending[@]}"; do
    [ -n "${conflicted[$site]:-}" ] && next+=("${site}")
  done
  pending=("${next[@]}")
done

if [ "${#pending[@]}" -gt 0 ]; then
  echo "::error::QA generated data was not refreshed for ${pending[*]} after ${max_rounds} attempts because QA kept changing; the next scheduled refresh will try again."
  exit 1
fi
if [ -n "${REFRESH_SOURCE_REF:-}" ] && [ "$(remote_ref_sha "${REFRESH_SOURCE_REF}")" != "${REFRESHED_SOURCE_SHA}" ]; then
  echo "::error::QA source ref ${REFRESH_SOURCE_REF} changed during deploy: expected ${REFRESHED_SOURCE_SHA}"
  exit 1
fi

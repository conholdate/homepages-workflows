#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
workflow="${script_dir}/../workflows/deploy-homepage.yml"

if ! grep -Fq 'group: homepage-${{ inputs.site }}-${{ inputs.environment }}' "${workflow}"; then
  echo "deploy-homepage concurrency must serialize by site and environment" >&2
  exit 1
fi

if grep -Fq 'group: homepage-${{ inputs.site }}-${{ inputs.environment }}-${{ inputs.ref }}' "${workflow}"; then
  echo "deploy-homepage concurrency must not include ref" >&2
  exit 1
fi

if ! grep -Fq 'transaction_id:' "${workflow}"; then
  echo "deploy-homepage workflow must expose transaction_id for run correlation" >&2
  exit 1
fi

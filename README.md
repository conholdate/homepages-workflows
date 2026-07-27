# Homepages Workflows

## Deployment source identity

`deploy-homepage.yml` resolves the checked-out `conholdate/homepages` commit
with `git rev-parse HEAD`; the workflow repository commit is never substituted
for that source identity. Every build writes the versioned, non-secret contract
to `public/.well-known/homepages-deployment.json` and uploads a byte-identical
`homepages-deployment.json` run artifact. The public contract contains only the
source SHA, site, environment, workflow repository/run/attempt, schema/kind,
and generation timestamp. It deliberately excludes refs supplied by users,
transaction or approval identifiers, credentials, and deployment-provider
details.

The same static identity file is deployed through Hugo for CloudFront, Ceph,
BunnyCDN, or any future provider, so Homepages Agent can reconcile without a
provider-specific control-plane API. A source SHA that predates current
monorepo `main` is not automatically stale: the agent uses its managed-site
registry to compare only render inputs relevant to that site.

Public GitHub Actions orchestrator for homepage build/deploy jobs.

## Daily metrics refresh

`Metrics Refresh` runs daily at `02:10 UTC` when repository variable
`METRICS_REFRESH_CRON_ENABLED=true`. For both `qa-homepages-v1` and `main` it
first synchronizes `data/products.json` from the fixed
`https://products.aspose.org/` **Available Now** catalog, then bakes and
validates metrics for all managed Aspose sites. Its commit scope is restricted
to `data/products.json` and `data/metrics/*.json`; catalog removals, ambiguous
GitHub repository evidence, endpoint failures, stale values, validation errors,
or any unrelated changed path stop the run before commit or deployment.

After each successful refresh, the workflow compares all six public QA
deployment identities with the exact `qa-homepages-v1` commit. Sites already
serving that commit are skipped; stale sites are rebuilt, polled to success,
and verified at the exact QA SHA. This also repairs a stale or partial QA
rollout when the daily data files themselves did not change.

When `METRICS_REFRESH_PRODUCTION_DEPLOY_ENABLED=true`, a scheduled main metrics
commit automatically dispatches all six Aspose production homepage rebuilds at
the exact committed SHA. The workflow correlates and polls every deploy run,
requires success, verifies each public
`/.well-known/homepages-deployment.json` identity at that SHA, and confirms
remote `main` did not drift during the rollout. This is a narrow metrics-only
automation path; it grants no unattended content, UI, configuration, or theme
publishing authority.

This repository is intentionally public so GitHub-hosted Actions minutes are
not consumed from the private `conholdate/homepages` repository. Workflow code
is public; all credentials must stay in encrypted GitHub Actions secrets.

## Main Workflow

Use **Deploy Homepage** from the Actions tab.

Inputs:

- `site`: homepage domain, for example `aspose.com`
- `environment`: `qa` or `production`
- `ref`: branch, tag, or commit SHA from `conholdate/homepages`
- `deploy`: set `false` for build-only verification
- `invalidate_cache`: set `true` to purge CloudFront or BunnyCDN where mapped
- `transaction_id`: optional Homepages Agent transaction id for publish/rollback
  run correlation

Default safe test:

```powershell
site=aspose.com
environment=qa
ref=main
deploy=false
invalidate_cache=false
```

Deploys are serialized by destination with concurrency group
`homepage-${{ inputs.site }}-${{ inputs.environment }}`. The source `ref` is
intentionally not part of the group, so two production deploys for the same site
cannot write the same destination concurrently.

## Metrics Refresh

Use **Metrics Refresh** from the Actions tab to refresh baked Aspose metrics.
The workflow checks out `conholdate/homepages-agent` and `conholdate/homepages`,
runs catalog sync plus data-only all-site metric bake, validates the refreshed
metrics, and commits only `data/products.json` and flat
`data/metrics/*.json` paths when values changed. It updates both
`qa-homepages-v1` and `main` with the commit message
`Refresh baked metrics (scheduled)`.

The QA and main metrics commits are a narrow data-only exception lane. A
workflow guard hard-fails if any worktree path is outside
`data/products.json` or flat `data/metrics/*.json`.

The workflow runs at `01:20` and `13:20 UTC`, after the common 12-hour
intersection of the upstream metrics collection schedules. Scheduled mutation
remains disabled unless `METRICS_REFRESH_CRON_ENABLED=true`. QA synchronization follows
every enabled successful refresh and skips exact current deployments.
Production deploy dispatches are separately gated: manual runs require
the `deploy_production` input, and scheduled runs require
`METRICS_REFRESH_PRODUCTION_DEPLOY_ENABLED=true`. When enabled and a main metrics
commit was created, the workflow dispatches `deploy-homepage.yml` for the six
Aspose production sites at `ref=main`; no deploy is dispatched when there are no
metric changes.

A manual run with `deploy_production=false` is QA-only: it refreshes and
synchronizes `qa-homepages-v1` but leaves `main` unchanged. Scheduled runs
refresh `main` only when the production-deploy repository variable is enabled;
manual runs do so only with `deploy_production=true`. Both use the production
gate above.

## Safety Rules

- Homepage deployment workflows are `workflow_dispatch` only; Metrics Refresh
  also has the documented daily schedule.
- The source repository is checked out with `HOMEPAGES_SOURCE_PAT`.
- Production jobs use the GitHub environment named `production`.
- Do not echo secrets, credentials, tokens, or signed URLs in workflow steps.
- Add production environment reviewers before using production deployment.

## Guarded PR Autopilot

Use **Homepages Agent PR Autopilot** for `conholdate/homepages-agent` PRs and
**Homepages Theme PR Autopilot** for shared-theme PRs in
`conholdate/homepages`.

Both wrappers call the same reusable guarded workflow. The only differences are
the target repository, commit-status context, and encrypted PAT secret binding.
The agent still enforces semantic review approval, required co-author trailers,
the pinned PR head SHA, and the repository-specific merge policy.
The homepages wrapper uses the encrypted `HOMEPAGES_REPOS_PAT` secret; the agent
wrapper continues to use `AGENT_REPO_PAT`.

## Required Secrets

See `docs/required-secrets-and-variables.md`. The file documents names only,
not values.

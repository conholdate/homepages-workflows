# Homepages Workflows

`conholdate/homepages-workflows` is the public GitHub Actions orchestrator for
Homepages Agent CI, PR review, homepage builds, deployments, scheduled metrics,
and operational health checks.

This README is the human source of truth for this repository. Files under
`.github/workflows/` and `.github/scripts/` remain authoritative for exact
inputs and execution. Treat any disagreement as a defect.

## Start Here

Normal users should request homepage work through Homepages Agent, Dashboard,
or WordPress. Those interfaces own authorization, change identity, QA evidence,
approval, and production confirmation. Do not manually dispatch production to
bypass that lifecycle.

Repository operators can use GitHub Actions for a controlled build or recovery.
The safest manual deployment test is build-only:

```text
Workflow: Deploy Homepage
site: aspose.com
environment: qa
ref: <exact conholdate/homepages commit SHA>
deploy: false
invalidate_cache: false
transaction_id: <empty>
```

## Workflow Catalog

| Workflow | Trigger | Purpose |
| --- | --- | --- |
| `deploy-homepage.yml` | Manual | Build or deploy one site/environment from an exact Homepages ref. |
| `agent-ci.yml` | Manual | Run affected Agent tests and publish the `Homepages Agent CI` commit status. |
| `agent-pr-autopilot.yml` | Manual | Review, and optionally merge, an Agent PR through the shared guard. |
| `homepages-pr-autopilot.yml` | Manual | Review, and optionally merge, a Homepages PR through the shared guard. |
| `guarded-pr-autopilot.yml` | Reusable call | Shared implementation used by both PR wrappers. |
| `metrics-refresh.yml` | Schedule/manual | Refresh bounded Aspose product/metric data and synchronize approved deployments. |
| `groupdocs-data-refresh.yml` | Schedule/manual | Bake one GroupDocs site's metrics and blog data, then refresh only its QA homepage. |
| `homepages-agent-heartbeat.yml` | Every hour at `:07` and `:37` UTC/manual | Produce Aspose coordination, validation, readiness, and metric evidence. |
| `homepages-agent-menu-health.yml` | Daily at `03:17` UTC/manual | Refresh and commit Agent menu-health reports. |
| `workflow-lint.yml` | Workflow/script PR or main push/manual | Run `actionlint`, `shellcheck`, and the deployment concurrency contract test. |

All schedules use UTC.

## Deploy Homepage

`deploy-homepage.yml` accepts:

| Input | Meaning | Default |
| --- | --- | --- |
| `site` | One listed homepage domain. | Required |
| `environment` | `qa` or `production`. | Required |
| `ref` | Branch, tag, or SHA in `conholdate/homepages`. Prefer an exact SHA. | `main` |
| `deploy` | Publish after the build. | `false` |
| `invalidate_cache` | Purge the mapped CloudFront or BunnyCDN cache after publish. | `false` |
| `transaction_id` | Optional Agent correlation ID for publish or rollback. | Empty |

Supported workflow choices are:

- Aspose: `aspose.com`, `aspose.cloud`, `aspose.app`, `aspose.ai`,
  `aspose.net`, and `aspose.org`;
- GroupDocs: `groupdocs.com`, `groupdocs.cloud`, and `groupdocs.app`;
- Conholdate: `conholdate.com`, `conholdate.cloud`, and `conholdate.app`.

A choice in this workflow means a build/deploy mapping exists. It does not by
itself mean that the site is fully onboarded or available to ordinary Agent
users; that status comes from the Homepages site manifest.

### Execution Contract

The workflow:

1. checks out this repository for workflow support;
2. checks out the requested `conholdate/homepages` ref;
3. resolves the checkout to an exact source SHA;
4. selects the site/environment config, target, credentials, and cache mapping;
5. resolves the exact QA or production Hugo pin from the checked-out site
   manifest, installs that Hugo Extended version, and builds the site;
6. writes and uploads deployment identity evidence;
7. deploys only when `deploy=true` and explicitly publishes the hidden
   `.well-known` identity file to every selected S3 target;
8. invalidates mapped cache only when requested.

The checked-out `docs/homepage-sites-manifest.yaml` is the Hugo runtime source
of truth. The workflow fails before build or deployment when the selected site
has no unique semantic-version pin for the requested environment.

Deploys are serialized by destination:

```text
homepage-<site>-<environment>
```

The source ref is intentionally absent from the concurrency group, so two runs
cannot write the same site/environment destination concurrently.

### Deployment Identity

Every build writes:

```text
public/.well-known/homepages-deployment.json
```

The same byte-identical file is uploaded as a run artifact. It records only the
source SHA, site, environment, workflow repository/run/attempt, schema/kind, and
generation time. It excludes credentials, provider details, approval IDs, and
user-supplied refs.

Homepages Agent uses this public identity to verify the exact deployed source
without depending on a provider-specific API.

Hugo deployment excludes hidden paths, so the shared workflow uploads this
single generated JSON file explicitly after each successful Hugo target deploy
and before cache invalidation. The upload uses only the selected committed
deployment target; it does not broaden the homepage file scope.

## QA And Production Safety

- `deploy=false` is the default.
- QA and production use separate serialized destinations.
- Production jobs use the GitHub environment named `production`.
- Configure required production environment reviewers before production use.
- Use an exact reviewed Homepages SHA for governed QA and production work.
- Production must promote the exact approved QA version through Homepages
  Agent; a manual workflow dispatch is an operator recovery path.
- Cache invalidation is explicit and mapped per site/provider.
- Never print tokens, credentials, private keys, or signed URLs.

## Metrics Refresh

`metrics-refresh.yml` is limited to the six Aspose sites. Its schedule is:

```text
01:20, 07:20, 13:20, and 19:20 UTC
```

Scheduled execution is skipped unless:

```text
METRICS_REFRESH_CRON_ENABLED=true
```

Before refreshing, the workflow compares every metrics-enabled Agent registry
site with the coverage declared by the existing Aspose and GroupDocs scheduled
workflows. Missing, unknown, or duplicate ownership blocks the run.

The workflow refreshes `qa-homepages-v1` first. It synchronizes
`data/products.json` from the fixed Aspose Available Now catalog, bakes metrics,
validates each successfully refreshed Aspose site, and permits commits only to:

- `data/products.json`;
- flat files under `data/metrics/*.json`.

Catalog removals, ambiguous repository evidence, validation failures, or
unrelated changed paths stop the run. An endpoint that remains unavailable
after bounded retries preserves that site's last verified file; other sites
continue independently.

After a successful refresh, public QA is reconciled to the exact QA commit.
Sites already serving that SHA are skipped; stale sites are deployed and then
verified for exact identity and `noindex`.

### Production Metrics Gate

A manual run updates `main` and production only when
`deploy_production=true`. A scheduled run does so only when:

```text
METRICS_REFRESH_PRODUCTION_DEPLOY_ENABLED=true
```

When a main metrics commit is created, the workflow deploys only successfully
refreshed Aspose sites at the exact commit, waits for every run, verifies every
public identity, and confirms `main` did not move during the rollout. No metrics
change means no production deployment.

This exception lane grants no unattended content, UI, config, theme, GroupDocs,
or Conholdate publishing authority.

## GroupDocs Data Refresh

`groupdocs-data-refresh.yml` runs 20 minutes after every second supplied
upstream GroupDocs metrics cycle:

| Site | Refresh times (UTC) | Baked data |
| --- | --- | --- |
| `groupdocs.com` | `01:10`, `07:10`, `13:10`, `19:10` | Total Downloads and latest blog posts |
| `groupdocs.cloud` | `00:20`, `06:20`, `12:20`, `18:20` | Downloads and latest blog posts |
| `groupdocs.app` | `01:15`, `09:15`, `17:15` | Data Processed |

Schedules run only when `GROUPDOCS_DATA_REFRESH_CRON_ENABLED=true`. Each run
fetches one site's approved endpoint once, commits only that site's registered
data files, and deploys only that QA homepage. When that homepage has an active
Request-to-QA candidate, the workflow bakes that selected site's generated
metrics/resource-feed files directly on the exact candidate branch and
redeploys it; authored content and renderer files remain unchanged. It never
deploys production.

## Agent CI And PR Review

### Homepages Agent CI

`agent-ci.yml` checks out the requested exact Agent ref, compiles source/tests,
and lets the Agent select the smallest test profile from the changed dependency
graph. Playwright is installed only when selected tests need it. Unknown/shared
paths fall back to the complete suite.

The workflow posts the `Homepages Agent CI` status to the exact Agent commit.

### Guarded PR Autopilot

The two public wrappers call `guarded-pr-autopilot.yml`:

- `agent-pr-autopilot.yml` targets `conholdate/homepages-agent`;
- `homepages-pr-autopilot.yml` targets `conholdate/homepages`.

Both resolve the PR head, post a repository-specific pending status, check out
an exact Agent ref, prepare the GitHub App review identity, and run the Agent's
policy-gated autopilot. `apply=false` is the default. The Agent still decides
whether the exact head is reviewable or mergeable.

## Operational Health

### Heartbeat

`homepages-agent-heartbeat.yml` runs at `:07` and `:37` each hour. It checks the
configured QA source, runs all-Aspose staging validation/readiness/metrics
evidence, and uploads the reports. Individual evidence commands continue far
enough to produce a useful combined summary when one check fails.

### Menu Health

`homepages-agent-menu-health.yml` runs daily at `03:17` UTC. It checks all
managed Aspose menus, uploads the reports, and commits changed menu-health
reports to Agent `main` with required co-author trailers.

Manual heartbeat or menu-health runs may override the Agent ref and Homepages
QA ref. Scheduled runs default the Agent to `main` and use repository variable
`HOMEPAGES_QA_SOURCE_REF`, falling back to `qa-homepages-v1`.

## Required Configuration

Store values only in GitHub encrypted secrets or repository/environment
variables. Never commit values to this public repository.

### Secrets

| Purpose | Names |
| --- | --- |
| Source checkout, Agent CI, and Agent PR operations | `HOMEPAGES_SOURCE_PAT` |
| Homepages PR operations | `HOMEPAGES_REPOS_PAT` |
| Review reasoning | `PROFESSIONALIZE_API_SERVICE_KEY`, `PROFESSIONALIZE_BASE_URL` |
| Independent GitHub App review | `HOMEPAGES_REVIEW_APP_ID`, `HOMEPAGES_REVIEW_APP_INSTALLATION_ID`, `HOMEPAGES_REVIEW_APP_PRIVATE_KEY` |
| S3-style deployment | `ACCESS_KEY_SL`, `SECRET_ACCESS_SL`, `ACCESS_KEY`, `SECRET_ACCESS`, `HOMEPAGES_ACCESS_KEY`, `HOMEPAGES_SECRET_ACCESS` |
| Ceph deployment | `CEPH_QA_ACCESS_KEY_ID`, `CEPH_QA_SECRET_ACCESS_KEY`, `CEPH_PRODUCTION_ACCESS_KEY_ID`, `CEPH_PRODUCTION_SECRET_ACCESS_KEY` |
| BunnyCDN purge | `BUNNY_API_KEY` |

### Variables

- `HOMEPAGES_QA_SOURCE_REF`;
- `METRICS_REFRESH_CRON_ENABLED`;
- `METRICS_REFRESH_PRODUCTION_DEPLOY_ENABLED`;
- `ASPOSE_COM_QA_CLOUDFRONT_DISTRIBUTION_ID`;
- `ASPOSE_COM_PRODUCTION_CLOUDFRONT_DISTRIBUTION_ID`;
- `ASPOSE_CLOUD_QA_CLOUDFRONT_DISTRIBUTION_ID`;
- `ASPOSE_CLOUD_PRODUCTION_CLOUDFRONT_DISTRIBUTION_ID`;
- `ASPOSE_APP_QA_CLOUDFRONT_DISTRIBUTION_ID`;
- `ASPOSE_APP_PRODUCTION_CLOUDFRONT_DISTRIBUTION_ID`;
- `ASPOSE_AI_QA_CLOUDFRONT_DISTRIBUTION_ID`;
- `ASPOSE_AI_PRODUCTION_CLOUDFRONT_DISTRIBUTION_ID`;
- `CONHOLDATE_CLOUD_QA_CLOUDFRONT_DISTRIBUTION_ID`.

## Validation And Contribution

`workflow-lint.yml` runs when workflow or workflow-script paths change on a PR
or on `main`, and it can be dispatched manually. It executes:

- `actionlint` for `.github/workflows/*.yml`;
- `shellcheck` for `.github/scripts/*.sh`;
- `.github/scripts/test-deploy-homepage-concurrency.sh`.

For Agent-assisted changes:

- start from current `origin/main`;
- use a `codex/` branch;
- preserve required co-author trailers;
- run focused local syntax/contract checks;
- dispatch one final-head CI/review path;
- never include secret values in commits, logs, PRs, or screenshots.

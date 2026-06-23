# Homepages Workflows

Public GitHub Actions orchestrator for homepage build/deploy jobs.

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
- `invalidate_cache`: set `true` to purge CloudFront or BunnyCDN where mapped.
  BunnyCDN purge failures are warning-only for QA because the deploy has already
  written Ceph origin content; production purge failures still fail the workflow.

Default safe test:

```powershell
site=aspose.com
environment=qa
ref=main
deploy=false
invalidate_cache=false
```

## Safety Rules

- Workflows are `workflow_dispatch` only.
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

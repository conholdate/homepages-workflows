from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "metrics-refresh.yml"


class MetricsRefreshWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_catalog_sync_precedes_all_site_bake_and_validation(self) -> None:
        catalog = self.workflow.index("products-catalog-sync --apply --write")
        bake = self.workflow.index(
            "metrics-bake --site all --apply --skip-source-label-sync --write"
        )
        validate = self.workflow.index('metrics-validate --site "${site}" --write')
        self.assertLess(catalog, bake)
        self.assertLess(bake, validate)

    def test_schedule_runs_after_the_common_upstream_metrics_cycle(self) -> None:
        self.assertIn('cron: "20 1,7,13,19 * * *"', self.workflow)
        self.assertNotIn("METRICS_REFRESH_CRON_ENABLED", self.workflow)

    def test_registry_coverage_is_checked_before_refresh(self) -> None:
        coverage = self.workflow.index("Verify registered metrics schedule coverage")
        refresh = self.workflow.index("Refresh and commit metrics")
        self.assertLess(coverage, refresh)
        self.assertIn(
            "HOMEPAGES_METRICS_COVERED_SITES: aspose.com aspose.cloud aspose.app aspose.ai aspose.net aspose.org",
            self.workflow,
        )

    def test_failed_site_preserves_last_value_without_blocking_successful_sites(self) -> None:
        self.assertIn('if item.get("ok") and item.get("applied")', self.workflow)
        self.assertIn('if not item.get("ok")', self.workflow)
        self.assertIn("Their last verified files are preserved", self.workflow)
        self.assertIn('metrics-validate --site "${site}" --write', self.workflow)
        self.assertIn("QA_REFRESH_SITES: ${{ steps.refresh.outputs.qa_sites }}", self.workflow)
        self.assertIn("METRICS_REFRESH_SITES: ${{ steps.refresh.outputs.qa_sites }}", self.workflow)

    def test_commit_scope_is_limited_to_catalog_and_baked_metrics(self) -> None:
        self.assertIn("git add data/products.json data/metrics/*.json", self.workflow)
        guard = (ROOT / ".github" / "scripts" / "metrics-refresh-scope-guard.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn('"$path" != "data/products.json"', guard)
        self.assertIn("^data/metrics/[^/]+\\.json$", guard)
        self.assertIn("git diff --name-only", guard)
        self.assertIn("git ls-files --others --exclude-standard", guard)

    def test_production_uses_shared_exact_live_publisher_even_if_qa_sync_fails(self) -> None:
        production = self.workflow.split("name: Refresh production metrics from exact live sources", 1)[1]
        self.assertIn("run: bash workflows/.github/scripts/refresh-production-metrics.sh", production)
        condition = next(line for line in production.splitlines() if line.strip().startswith("if:"))
        self.assertIn("!cancelled() && steps.refresh.outcome == 'success' &&", condition)
        self.assertNotIn("always()", condition)
        self.assertIn("METRICS_SOURCE_SHA: ${{ steps.refresh.outputs.qa_sha }}", self.workflow)

    def test_qa_sync_uses_the_shared_generated_data_publisher(self) -> None:
        qa_step = self.workflow.index("name: Synchronize QA homepage deployments")
        production_step = self.workflow.index("name: Refresh production metrics from exact live sources")
        self.assertLess(qa_step, production_step)
        qa = self.workflow[qa_step:production_step]
        self.assertIn("always() && steps.refresh.outcome == 'success'", qa)
        self.assertIn("REFRESHED_SOURCE_SHA: ${{ steps.refresh.outputs.qa_sha }}", qa)
        self.assertIn("REFRESH_BASE_SHA: ${{ steps.refresh.outputs.qa_before_sha }}", qa)
        self.assertIn("REFRESH_SOURCE_REF: qa-homepages-v1", qa)
        self.assertIn("run: bash workflows/.github/scripts/refresh-qa-generated-data.sh", qa)

    def test_active_qa_sources_receive_site_local_metrics_without_aggregate_fallback(self) -> None:
        shared = (ROOT / ".github" / "scripts" / "refresh-qa-generated-data.sh").read_text(encoding="utf-8")
        self.assertIn('"${workflows_repo}/.github/scripts/resolve_active_qa_ref.py"', shared)
        self.assertIn("path: workflows", self.workflow)
        self.assertNotIn("--optional", shared)
        self.assertIn('--recovery-ref "${recovery_ref}"', shared)
        self.assertIn('[ "${current_qa_sha}" = "${REFRESH_BASE_SHA}" ]', shared)
        self.assertIn("default_paths='data/metrics/{site}.json'", shared)
        self.assertEqual(
            self.workflow.count("metrics-bake --site all --apply --skip-source-label-sync --write"),
            1,
        )

    def test_exact_parent_is_rechecked_before_each_qa_dispatch(self) -> None:
        shared = (ROOT / ".github" / "scripts" / "refresh-qa-generated-data.sh").read_text(encoding="utf-8")
        self.assertIn('latest_qa_sha="$(public_qa_source "${site}" "${GITHUB_RUN_ID}-pre-dispatch-', shared)
        self.assertIn('if [ "${latest_qa_sha}" != "${current_qa_sha}" ]', shared)
        self.assertIn("Public QA changed before deploy", shared)
        self.assertIn("push -q --force-with-lease=", shared)
        self.assertIn('-f "expected_live_sha=${current_qa_sha}"', shared)

    def test_exact_parent_commit_has_repository_local_identity(self) -> None:
        qa_step = self.workflow.index("name: Synchronize QA homepage deployments")
        production_step = self.workflow.index("name: Refresh production metrics from exact live sources")
        self.assertIn("GIT_AUTHOR_NAME: Homepages Agent", self.workflow[qa_step:production_step])
        self.assertIn(
            "GIT_COMMITTER_EMAIL: homepages.agent@conholdate.com",
            self.workflow[qa_step:production_step],
        )

    def test_workflow_never_mutates_homepages_main(self) -> None:
        # Production is refreshed on each site's exact live source, never via main.
        self.assertNotIn("refs/heads/main", self.workflow)
        self.assertNotIn("HEAD:main", self.workflow)
        self.assertIn('refresh_branch "${HOMEPAGES_QA_SOURCE_REF}"', self.workflow)


if __name__ == "__main__":
    unittest.main()

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "groupdocs-data-refresh.yml"


class GroupDocsDataRefreshWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_schedules_follow_every_second_upstream_cycle_by_twenty_minutes(self) -> None:
        self.assertIn('cron: "10 1,7,13,19 * * *"', self.workflow)
        self.assertIn('cron: "20 0,6,12,18 * * *"', self.workflow)
        self.assertIn('cron: "15 1,9,17 * * *"', self.workflow)
        self.assertNotIn("GROUPDOCS_DATA_REFRESH_CRON_ENABLED", self.workflow)

    def test_registry_coverage_declares_all_groupdocs_metrics_sites(self) -> None:
        self.assertIn(
            "HOMEPAGES_METRICS_COVERED_SITES: groupdocs.com groupdocs.cloud groupdocs.app",
            self.workflow,
        )
        self.assertIn("Verify registered metrics schedule coverage", self.workflow)

    def test_bakes_only_selected_site_without_a_duplicate_validation_fetch(self) -> None:
        self.assertIn('metrics-bake --site "${SITE}" --apply --skip-source-label-sync', self.workflow)
        self.assertNotIn("metrics-validate", self.workflow)
        self.assertIn('resource-feed-bake --feed "${key}"', self.workflow)

    def test_qa_refresh_is_scoped_and_production_uses_shared_exact_live_publisher(self) -> None:
        self.assertIn('metric_path="data/metrics/${SITE}.json"', self.workflow)
        self.assertIn('feed_path="data/homepage_resource_feeds/${key}.json"', self.workflow)
        self.assertIn('"${metric_path}"|"${feed_path}")', self.workflow)
        self.assertIn("run: bash workflows/.github/scripts/refresh-qa-generated-data.sh", self.workflow)
        self.assertIn(
            'GENERATED_PATHS: "data/metrics/{site}.json data/homepage_resource_feeds/{key}.json"',
            self.workflow,
        )
        self.assertIn("github.event_name == 'schedule' || inputs.deploy_production", self.workflow)
        self.assertIn("default: false", self.workflow)
        self.assertIn("METRICS_SOURCE_SHA: ${{ steps.bake.outputs.source_sha }}", self.workflow)
        self.assertIn("METRICS_REFRESH_SITES: ${{ steps.select.outputs.site }}", self.workflow)
        self.assertIn("run: bash workflows/.github/scripts/refresh-production-metrics.sh", self.workflow)

    def test_active_request_candidate_receives_only_refreshed_generated_data(self) -> None:
        self.assertIn(
            '"${GITHUB_WORKSPACE}/workflows/.github/scripts/resolve_active_qa_ref.py"',
            self.workflow,
        )
        self.assertIn("path: workflows", self.workflow)
        self.assertIn("Baking generated data directly on exact active QA source", self.workflow)
        self.assertIn('git checkout -B active-qa-data-refresh "${current_sha}"', self.workflow)
        self.assertIn('push --force-with-lease="${target_ref}:${target_remote_sha}"', self.workflow)
        # D-068: frozen migration refs are never written; the site's own branch is the fallback.
        self.assertIn('recovery_ref="refs/heads/homepages-agent/qa-refresh/${SITE}"', self.workflow)
        self.assertIn('--recovery-ref "${recovery_ref}"', self.workflow)
        self.assertIn("REFRESHED_SOURCE_SHA: ${{ steps.bake.outputs.source_sha }}", self.workflow)
        self.assertIn("REFRESH_BASE_SHA: ${{ steps.bake.outputs.before_sha }}", self.workflow)
        self.assertNotIn("Preserving active QA candidate", self.workflow)

    def test_active_candidate_refresh_rejects_parent_and_path_drift(self) -> None:
        self.assertIn("Public QA identity names unexpected repository", self.workflow)
        self.assertIn("Selected QA data target does not match public QA", self.workflow)
        self.assertIn("Refresh changed an unapproved path", self.workflow)
        shared = (ROOT / ".github" / "scripts" / "refresh-qa-generated-data.sh").read_text(encoding="utf-8")
        self.assertIn("Public QA changed before deploy", shared)
        self.assertIn('-f "expected_live_sha=${current_qa_sha}"', shared)

    def test_candidate_lookup_reads_all_remote_heads(self) -> None:
        self.assertIn("ls-remote --heads https://github.com/conholdate/homepages.git", self.workflow)
        self.assertNotIn("'refs/heads/homepages-agent/qa-changes/*'", self.workflow)


if __name__ == "__main__":
    unittest.main()

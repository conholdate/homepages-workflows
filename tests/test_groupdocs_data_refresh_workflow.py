from pathlib import Path
import unittest


WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "groupdocs-data-refresh.yml"


class GroupDocsDataRefreshWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_schedules_follow_every_second_upstream_cycle_by_twenty_minutes(self) -> None:
        self.assertIn('cron: "10 1,7,13,19 * * *"', self.workflow)
        self.assertIn('cron: "20 0,6,12,18 * * *"', self.workflow)
        self.assertIn('cron: "15 1,9,17 * * *"', self.workflow)

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

    def test_commit_and_deploy_are_qa_only_and_path_scoped(self) -> None:
        self.assertIn('metric_path="data/metrics/${SITE}.json"', self.workflow)
        self.assertIn('feed_path="data/homepage_resource_feeds/${key}.json"', self.workflow)
        self.assertIn('"${metric_path}"|"${feed_path}")', self.workflow)
        self.assertIn('-f "environment=qa"', self.workflow)
        self.assertNotIn("environment=production", self.workflow)

    def test_active_request_candidate_receives_only_refreshed_generated_data(self) -> None:
        self.assertIn(
            '"${GITHUB_WORKSPACE}/workflows/.github/scripts/resolve_active_qa_ref.py"',
            self.workflow,
        )
        self.assertIn("path: workflows", self.workflow)
        self.assertIn("Baking generated data directly on exact active QA source", self.workflow)
        self.assertIn('git checkout -B active-qa-data-refresh "origin/${target_branch}"', self.workflow)
        self.assertIn('push --force-with-lease="${target_ref}:${before_sha}"', self.workflow)
        self.assertIn('-f "ref=${SOURCE_SHA}"', self.workflow)
        self.assertNotIn("Preserving active QA candidate", self.workflow)

    def test_active_candidate_refresh_rejects_parent_and_path_drift(self) -> None:
        self.assertIn("Public QA identity names unexpected repository", self.workflow)
        self.assertIn("Selected QA data target does not match public QA", self.workflow)
        self.assertIn("Refresh changed an unapproved path", self.workflow)
        self.assertIn("Public QA changed before refreshed deployment", self.workflow)

    def test_candidate_lookup_reads_all_remote_heads(self) -> None:
        self.assertIn("ls-remote --heads https://github.com/conholdate/homepages.git", self.workflow)
        self.assertNotIn("'refs/heads/homepages-agent/qa-changes/*'", self.workflow)


if __name__ == "__main__":
    unittest.main()

from pathlib import Path
import unittest


WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "groupdocs-data-refresh.yml"


class GroupDocsDataRefreshWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_schedules_follow_each_upstream_cycle_by_twenty_minutes(self) -> None:
        self.assertIn('cron: "10 1,4,7,10,13,16,19,22 * * *"', self.workflow)
        self.assertIn('cron: "20 0,3,6,9,12,15,18,21 * * *"', self.workflow)
        self.assertIn('cron: "15 1,5,9,13,17,21 * * *"', self.workflow)

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
        self.assertIn("'refs/heads/homepages-agent/qa-changes/*'", self.workflow)
        self.assertIn("Refreshing generated data on active QA candidate", self.workflow)
        self.assertIn('checkout "${SOURCE_SHA}" -- "${paths[@]}"', self.workflow)
        self.assertIn('push --force-with-lease="${candidate}:${current_sha}"', self.workflow)
        self.assertIn('-f "ref=${deploy_sha}"', self.workflow)
        self.assertNotIn("Preserving active QA candidate", self.workflow)

    def test_active_candidate_refresh_rejects_parent_and_path_drift(self) -> None:
        self.assertIn("Active QA candidate moved before data refresh", self.workflow)
        self.assertIn("Active candidate refresh changed an unapproved path", self.workflow)
        self.assertIn("Public QA changed before refreshed candidate deployment", self.workflow)
        self.assertIn("serves unrecognized source", self.workflow)

    def test_candidate_lookup_consumes_all_remote_output_under_pipefail(self) -> None:
        self.assertIn("$1 == expected && !found { print $2; found=1 }", self.workflow)
        self.assertNotIn("print $2; exit", self.workflow)


if __name__ == "__main__":
    unittest.main()

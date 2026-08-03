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
        self.assertIn("^data/metrics/groupdocs", self.workflow)
        self.assertIn("^data/homepage_resource_feeds/groupdocs_", self.workflow)
        self.assertIn('-f "environment=qa"', self.workflow)
        self.assertNotIn("environment=production", self.workflow)

    def test_active_request_candidate_is_preserved(self) -> None:
        self.assertIn("'refs/heads/homepages-agent/qa-changes/*'", self.workflow)
        self.assertIn("Preserving active QA candidate", self.workflow)


if __name__ == "__main__":
    unittest.main()

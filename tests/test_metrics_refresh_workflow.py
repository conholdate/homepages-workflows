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
        validate = self.workflow.index("metrics-validate --site all --write")
        self.assertLess(catalog, bake)
        self.assertLess(bake, validate)

    def test_commit_scope_is_limited_to_catalog_and_baked_metrics(self) -> None:
        self.assertIn("git add data/products.json data/metrics/*.json", self.workflow)
        guard = (ROOT / ".github" / "scripts" / "metrics-refresh-scope-guard.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn('"$path" != "data/products.json"', guard)
        self.assertIn("^data/metrics/[^/]+\\.json$", guard)
        self.assertIn("git diff --name-only", guard)
        self.assertIn("git ls-files --others --exclude-standard", guard)

    def test_production_uses_and_verifies_exact_main_sha(self) -> None:
        self.assertIn("SOURCE_SHA: ${{ steps.refresh.outputs.main_sha }}", self.workflow)
        self.assertIn('-f "ref=${SOURCE_SHA}"', self.workflow)
        self.assertIn("actions/runs/${run_id}", self.workflow)
        self.assertIn(".well-known/homepages-deployment.json", self.workflow)
        self.assertIn('remote_main_after="$(remote_main_sha)"', self.workflow)

    def test_qa_is_synchronized_to_exact_qa_sha_even_when_metrics_are_unchanged(self) -> None:
        qa_step = self.workflow.index("name: Synchronize QA homepage deployments")
        production_step = self.workflow.index("name: Dispatch production homepage deploys")
        self.assertLess(qa_step, production_step)
        self.assertIn("name: Synchronize QA homepage deployments", self.workflow)
        self.assertIn("always() && steps.refresh.outcome == 'success'", self.workflow)
        self.assertIn("SOURCE_SHA: ${{ steps.refresh.outputs.qa_sha }}", self.workflow)
        self.assertIn('remote_qa="$(remote_qa_sha)"', self.workflow)
        self.assertIn('-f "site=${site}"', self.workflow)
        self.assertIn('-f "environment=qa"', self.workflow)
        self.assertIn('-f "ref=${SOURCE_SHA}"', self.workflow)
        self.assertIn("actions/runs/${run_id}", self.workflow)
        self.assertIn("https://qa.${site}/.well-known/homepages-deployment.json", self.workflow)
        self.assertIn("public_qa_has_noindex", self.workflow)
        self.assertIn("missing robots noindex", self.workflow)
        self.assertIn('remote_qa_after="$(remote_qa_sha)"', self.workflow)

    def test_manual_qa_only_refresh_does_not_mutate_main(self) -> None:
        self.assertIn(
            "REFRESH_MAIN: ${{ (github.event_name == 'schedule' && vars.METRICS_REFRESH_PRODUCTION_DEPLOY_ENABLED == 'true') || (github.event_name == 'workflow_dispatch' && inputs.deploy_production) }}",
            self.workflow,
        )
        self.assertIn('if [ "${REFRESH_MAIN}" = "true" ]; then', self.workflow)
        self.assertIn("Manual QA-only refresh left homepages main unchanged", self.workflow)
        self.assertIn("printf 'main_changed=false\\n'", self.workflow)
        self.assertIn("ls-remote https://github.com/conholdate/homepages.git refs/heads/main", self.workflow)


if __name__ == "__main__":
    unittest.main()

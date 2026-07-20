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
        bake = self.workflow.index("metrics-bake --site all --apply --write")
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

    def test_production_uses_and_verifies_exact_main_sha(self) -> None:
        self.assertIn("SOURCE_SHA: ${{ steps.refresh.outputs.main_sha }}", self.workflow)
        self.assertIn('-f "ref=${SOURCE_SHA}"', self.workflow)
        self.assertIn("actions/runs/${run_id}", self.workflow)
        self.assertIn(".well-known/homepages-deployment.json", self.workflow)
        self.assertIn('remote_main_after="$(remote_main_sha)"', self.workflow)


if __name__ == "__main__":
    unittest.main()

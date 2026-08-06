from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github" / "scripts" / "metrics_registry_coverage.py"


class MetricsRegistryCoverageTests(unittest.TestCase):
    def _run(self, registry: str, coverage: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_path = root / "metrics.yaml"
            workflows = root / "workflows"
            workflows.mkdir()
            registry_path.write_text(registry, encoding="utf-8")
            (workflows / "refresh.yml").write_text(coverage, encoding="utf-8")
            return subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--registry",
                    str(registry_path),
                    "--workflow-dir",
                    str(workflows),
                ],
                text=True,
                capture_output=True,
                check=False,
            )

    def test_accepts_exact_single_owner_coverage(self) -> None:
        result = self._run(
            "sites:\n  example.com:\n    metrics:\n      total:\n        enabled: true\n",
            "jobs:\n  refresh:\n    env:\n      HOMEPAGES_METRICS_COVERED_SITES: example.com\n",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Metrics schedule coverage OK: example.com", result.stdout)

    def test_rejects_registered_site_without_schedule_coverage(self) -> None:
        result = self._run(
            "sites:\n  missing.example:\n    metrics:\n      total:\n        enabled: true\n",
            "jobs:\n  refresh:\n    env:\n      HOMEPAGES_METRICS_COVERED_SITES: covered.example\n",
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("Missing scheduled metrics coverage: missing.example", result.stdout)
        self.assertIn("Scheduled metrics coverage has no enabled registry metrics: covered.example", result.stdout)

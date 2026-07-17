from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github" / "scripts" / "write_deployment_identity.py"
SPEC = importlib.util.spec_from_file_location("write_deployment_identity", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class DeploymentIdentityTests(unittest.TestCase):
    def test_public_identity_is_minimal_versioned_and_non_secret(self) -> None:
        payload = MODULE.deployment_identity(
            source_sha="a" * 40,
            site="aspose.com",
            environment="production",
            run_id=12345,
            run_attempt=2,
            generated_at_utc="2026-07-17T12:00:00+00:00",
        )
        self.assertEqual(
            set(payload),
            {
                "schema_version",
                "kind",
                "repository",
                "source_sha",
                "site",
                "environment",
                "workflow",
                "generated_at_utc",
            },
        )
        rendered = json.dumps(payload).casefold()
        for forbidden in ("secret", "token", "password", "approval", "nonce", "transaction"):
            self.assertNotIn(forbidden, rendered)

    def test_endpoint_and_run_evidence_are_byte_identical(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = MODULE.deployment_identity(
                source_sha="b" * 40,
                site="aspose.net",
                environment="qa",
                run_id=99,
                run_attempt=1,
                generated_at_utc="2026-07-17T12:00:00+00:00",
            )
            endpoint, evidence = MODULE.write_identity(
                output_root=root / "public",
                evidence_dir=root / "evidence",
                payload=payload,
            )
            self.assertEqual(endpoint.read_bytes(), evidence.read_bytes())
            self.assertEqual(endpoint.relative_to(root / "public").as_posix(), ".well-known/homepages-deployment.json")

    def test_invalid_source_sha_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "source_sha"):
            MODULE.deployment_identity(
                source_sha="main",
                site="aspose.com",
                environment="production",
                run_id=1,
                run_attempt=1,
            )

    def test_workflow_resolves_homepages_checkout_and_uploads_identity(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "deploy-homepage.yml").read_text(encoding="utf-8")
        self.assertIn("path: homepages-source", workflow)
        self.assertIn('source_sha="$(git rev-parse HEAD)"', workflow)
        self.assertIn("steps.source.outputs.source_sha", workflow)
        self.assertIn("write_deployment_identity.py", workflow)
        self.assertIn("actions/upload-artifact@v4", workflow)
        self.assertIn("homepages-source/deployment-evidence/homepages-deployment.json", workflow)
        self.assertLess(workflow.index("Write deployment identity"), workflow.index("- name: Deploy\n"))


if __name__ == "__main__":
    unittest.main()

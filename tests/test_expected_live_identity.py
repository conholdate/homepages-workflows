"""D-067: a deploy built on an older live version must never overwrite newer work."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".github" / "scripts"))
EXPECTED_SCRIPT = ROOT / ".github" / "scripts" / "verify_expected_live_identity.py"
EXPECTED_SPEC = importlib.util.spec_from_file_location("verify_expected_live_identity", EXPECTED_SCRIPT)
assert EXPECTED_SPEC and EXPECTED_SPEC.loader
EXPECTED_MODULE = importlib.util.module_from_spec(EXPECTED_SPEC)
EXPECTED_SPEC.loader.exec_module(EXPECTED_MODULE)


class _Completed:
    def __init__(self, returncode: int, stdout: str = "") -> None:
        self.returncode, self.stdout = returncode, stdout


class ExpectedLiveIdentityTests(unittest.TestCase):
    def _run(self, *, live: _Completed, expected: str = "a" * 40) -> tuple[int, list[list[str]]]:
        calls: list[list[str]] = []

        def runner(command, **_kwargs):  # noqa: ANN001, ANN003
            calls.append(command)
            return live

        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.toml"
            config.write_text(
                '[[deployment.targets]]\nname = "qa_ceph"\n'
                'URL = "s3://qa-aspose-org/?endpoint=https://s3.dynabic.com&region=us-east-1"\n',
                encoding="utf-8",
            )
            code = EXPECTED_MODULE.main(
                ["--config", str(config), "--target", "qa_ceph", "--expected", expected],
                runner=runner,
            )
        return code, calls

    def test_matching_live_version_allows_the_deploy(self) -> None:
        code, calls = self._run(live=_Completed(0, json.dumps({"source_sha": "A" * 40})))
        self.assertEqual(0, code)
        self.assertEqual(
            ["aws", "s3", "cp", "s3://qa-aspose-org/.well-known/homepages-deployment.json", "-"],
            calls[0][:5],
        )
        self.assertIn("https://s3.dynabic.com", calls[0])

    def test_newer_live_version_refuses_the_deploy(self) -> None:
        code, _ = self._run(live=_Completed(0, json.dumps({"source_sha": "b" * 40})))
        self.assertEqual(EXPECTED_MODULE.LIVE_CHANGED, code)

    def test_missing_or_unreadable_live_identity_refuses_the_deploy(self) -> None:
        for live in (_Completed(1), _Completed(0, "not json")):
            with self.subTest(live=live.stdout):
                code, _ = self._run(live=live)
                self.assertEqual(EXPECTED_MODULE.LIVE_CHANGED, code)

    def test_expected_version_must_be_a_full_sha(self) -> None:
        code, calls = self._run(live=_Completed(0, "{}"), expected="abc123")
        self.assertEqual(2, code)
        self.assertEqual([], calls)

    def test_deploy_checks_expected_live_version_before_any_upload(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "deploy-homepage.yml").read_text(encoding="utf-8")
        self.assertIn("expected_live_sha:", workflow)
        deploy = workflow.split("- name: Deploy\n", 1)[1]
        check = deploy.index("verify_expected_live_identity.py")
        self.assertLess(check, deploy.index("hugo --config"))
        self.assertLess(check, deploy.index("publish_deployment_identity.py"))
        self.assertIn('if [ -n "${EXPECTED_LIVE_SHA}" ]', deploy)


if __name__ == "__main__":
    unittest.main()

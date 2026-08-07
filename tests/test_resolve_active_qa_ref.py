from __future__ import annotations

from pathlib import Path
import importlib.util
import unittest


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "scripts"
    / "resolve_active_qa_ref.py"
)
SPEC = importlib.util.spec_from_file_location("resolve_active_qa_ref", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ResolveActiveQaRefTests(unittest.TestCase):
    def test_resolves_named_groupdocs_candidate_outside_legacy_namespace(self) -> None:
        sha = "2f5efa03e2f17b56b869ddb55645830119cca6eb"
        self.assertEqual(
            MODULE.resolve_ref(
                [f"{sha}\trefs/heads/codex/return-groupdocs-qa"],
                sha=sha,
                aggregate_ref="refs/heads/qa-homepages-v1",
            ),
            "refs/heads/codex/return-groupdocs-qa",
        )

    def test_prefers_exact_aggregate_qa_ref(self) -> None:
        sha = "a" * 40
        self.assertEqual(
            MODULE.resolve_ref(
                [
                    f"{sha}\trefs/heads/qa-homepages-v1",
                    f"{sha}\trefs/heads/codex/duplicate",
                ],
                sha=sha,
                aggregate_ref="refs/heads/qa-homepages-v1",
            ),
            "refs/heads/qa-homepages-v1",
        )

    def test_rejects_ambiguous_candidate_branches(self) -> None:
        sha = "b" * 40
        with self.assertRaisesRegex(ValueError, "Multiple writable QA branches"):
            MODULE.resolve_ref(
                [
                    f"{sha}\trefs/heads/codex/one",
                    f"{sha}\trefs/heads/homepages-agent/qa-changes/two",
                ],
                sha=sha,
                aggregate_ref="refs/heads/qa-homepages-v1",
            )

    def test_branchless_public_qa_uses_named_recovery_ref_not_aggregate(self) -> None:
        sha = "c" * 40
        self.assertEqual(
            MODULE.resolve_ref(
                [f"{sha}\trefs/heads/main"],
                sha=sha,
                aggregate_ref="refs/heads/qa-homepages-v1",
                recovery_ref="refs/heads/homepages-agent/qa-refresh/aspose.com",
            ),
            "refs/heads/homepages-agent/qa-refresh/aspose.com",
        )

    def test_recovery_ref_must_stay_in_managed_qa_namespace(self) -> None:
        with self.assertRaisesRegex(ValueError, "outside the managed namespace"):
            MODULE.resolve_ref(
                [],
                sha="d" * 40,
                aggregate_ref="refs/heads/qa-homepages-v1",
                recovery_ref="refs/heads/main",
            )

    def test_site_recovery_ref_wins_when_other_candidate_shares_sha(self) -> None:
        sha = "e" * 40
        recovery = "refs/heads/homepages-agent/qa-refresh/aspose.com"
        self.assertEqual(
            MODULE.resolve_ref(
                [
                    f"{sha}\trefs/heads/homepages-agent/qa-changes/other",
                    f"{sha}\t{recovery}",
                ],
                sha=sha,
                aggregate_ref="refs/heads/qa-homepages-v1",
                recovery_ref=recovery,
            ),
            recovery,
        )


if __name__ == "__main__":
    unittest.main()

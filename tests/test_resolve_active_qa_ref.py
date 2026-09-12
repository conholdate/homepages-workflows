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
    def test_ha_30abc04807c05266_ceph_migration_ref_is_not_writable(self) -> None:
        sha = "5a4f9e1b19919de4bf42686fb92fdb69e4780944"
        frozen = "refs/heads/codex/ceph-migration-b0ea5ebc6f9ef02d"
        recovery = "refs/heads/homepages-agent/qa-refresh/aspose.com"
        self.assertEqual(
            MODULE.resolve_ref(
                [f"{sha}\t{frozen}"], sha=sha,
                aggregate_ref="refs/heads/qa-homepages-v1", recovery_ref=recovery,
            ),
            recovery,
        )
        with self.assertRaisesRegex(ValueError, "No writable"):
            MODULE.resolve_ref(
                [f"{sha}\t{frozen}"], sha=sha,
                aggregate_ref="refs/heads/qa-homepages-v1",
            )

    def test_frozen_ceph_ref_cannot_be_configured_as_aggregate_or_recovery(self) -> None:
        frozen = "refs/heads/codex/ceph-migration-b0ea5ebc6f9ef02d"
        for overrides in ({"aggregate_ref": frozen}, {"recovery_ref": frozen}):
            with self.subTest(overrides=overrides), self.assertRaisesRegex(ValueError, "immutable"):
                MODULE.resolve_ref(
                    [], sha="a" * 40,
                    **({"aggregate_ref": "refs/heads/qa-homepages-v1"} | overrides),
                )

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

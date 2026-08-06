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

    def test_optional_lookup_ignores_production_only_source(self) -> None:
        sha = "c" * 40
        self.assertEqual(
            MODULE.resolve_ref(
                [f"{sha}\trefs/heads/main"],
                sha=sha,
                aggregate_ref="refs/heads/qa-homepages-v1",
                optional=True,
            ),
            "",
        )


if __name__ == "__main__":
    unittest.main()

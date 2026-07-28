from pathlib import Path
import unittest


class AgentCiWorkflowTests(unittest.TestCase):
    def test_uses_change_aware_agent_test_profile(self) -> None:
        workflow = (
            Path(__file__).resolve().parents[1] / ".github/workflows/agent-ci.yml"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "python -m homepages_agent.ci_test_profile --base-ref origin/main --run",
            workflow,
        )
        self.assertIn(
            "python -m homepages_agent.ci_test_profile --base-ref origin/main --needs-playwright",
            workflow,
        )
        self.assertIn(
            "if: ${{ steps.test-profile.outputs.needs_playwright == 'true' }}",
            workflow,
        )
        self.assertNotIn("python -m unittest discover -s tests", workflow)


if __name__ == "__main__":
    unittest.main()

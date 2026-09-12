"""Execute the actual scheduled-refresh commit commands at Git's trailer gate."""

from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
COAUTHORS = [
    "Co-authored-by: salmansarfraz <kh.salman.sarfraz@gmail.com>",
    "Co-authored-by: Codex <codex@openai.com>",
    "Co-authored-by: Homepages Agent <homepages.agent@conholdate.com>",
]


class RefreshCommitAuthorshipTests(unittest.TestCase):
    def test_frozen_migration_survives_real_exact_parent_refresh_push(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo, remote = root / "repo", root / "remote.git"
            env = os.environ | {
                "GIT_AUTHOR_NAME": "Homepages Agent", "GIT_COMMITTER_NAME": "Homepages Agent",
                "GIT_AUTHOR_EMAIL": "homepages.agent@conholdate.com",
                "GIT_COMMITTER_EMAIL": "homepages.agent@conholdate.com",
            }
            def git(*args: str) -> str:
                return subprocess.run(["git", *args], cwd=root, env=env, check=True,
                                      capture_output=True, text=True).stdout.strip()
            git("init", "-q", str(repo))
            git("-C", str(repo), "commit", "--allow-empty", "-m", "Confirmed Ceph migration", "-m", "\n".join(COAUTHORS))
            parent = git("-C", str(repo), "rev-parse", "HEAD")
            frozen = "refs/heads/codex/ceph-migration-b0ea5ebc6f9ef02d"
            recovery = "refs/heads/homepages-agent/qa-refresh/aspose.com"
            git("-C", str(repo), "update-ref", frozen, parent)
            git("clone", "--bare", "-q", str(repo), str(remote))
            heads = git("ls-remote", "--heads", str(remote))
            import sys
            selected = subprocess.run([
                sys.executable, str(ROOT / ".github/scripts/resolve_active_qa_ref.py"),
                "--sha", parent, "--aggregate-ref", "refs/heads/qa-homepages-v1",
                "--recovery-ref", recovery,
            ], input=heads, check=True, capture_output=True, text=True).stdout.strip()
            self.assertEqual(selected, recovery)
            git("-C", str(repo), "commit", "--allow-empty", "-m", "Refresh site metrics", "-m", "\n".join(COAUTHORS))
            git("-C", str(repo), "push", "--force-with-lease=" + selected + ":", str(remote), "HEAD:" + selected)
            self.assertEqual(git("--git-dir=" + str(remote), "rev-parse", frozen), parent)
            self.assertNotEqual(git("--git-dir=" + str(remote), "rev-parse", recovery), parent)

    def test_ha_30abc04807c05266_every_generated_commit_passes_real_git_trailers(self) -> None:
        bash = (r"C:\Program Files\Git\bin\bash.exe" if os.name == "nt" else shutil.which("bash"))
        self.assertTrue(bash and Path(bash).is_file(), "Bash is required for workflow proof")
        for filename, expected_count in (("workflows/metrics-refresh.yml", 2),
                                         ("workflows/groupdocs-data-refresh.yml", 1),
                                         ("scripts/refresh-production-metrics.sh", 1)):
            workflow = (ROOT / ".github" / filename).read_text(encoding="utf-8")
            commands = re.findall(r"(?m)^[ \t]*git commit \\\n(?:[ \t]+-m[^\n]*(?:\n|$))+", workflow)
            self.assertEqual(len(commands), expected_count)
            for index, command in enumerate(commands):
                with self.subTest(workflow=filename, command=index), tempfile.TemporaryDirectory() as tmp:
                    repo = Path(tmp)
                    env = os.environ | {
                        "GIT_AUTHOR_NAME": "Homepages Agent", "GIT_COMMITTER_NAME": "Homepages Agent",
                        "GIT_AUTHOR_EMAIL": "homepages.agent@conholdate.com",
                        "GIT_COMMITTER_EMAIL": "homepages.agent@conholdate.com",
                        "site": "aspose.com", "SITE": "groupdocs.com",
                    }
                    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, capture_output=True)
                    (repo / "metric.json").write_text("{}", encoding="utf-8")
                    subprocess.run(["git", "add", "metric.json"], cwd=repo, check=True, capture_output=True)
                    subprocess.run([str(bash), "-c", textwrap.dedent(command)], cwd=repo, env=env,
                                   check=True, capture_output=True, text=True)
                    message = subprocess.run(["git", "log", "-1", "--format=%B"], cwd=repo,
                                             check=True, capture_output=True, text=True).stdout.rstrip()
                    lines = message.splitlines()
                    self.assertEqual(lines[-3:], COAUTHORS)
                    self.assertEqual(lines[-4], "")
                    parsed = subprocess.run(["git", "interpret-trailers", "--parse"], cwd=repo,
                                            input=message, check=True, capture_output=True, text=True).stdout
                    self.assertEqual(parsed.splitlines(), COAUTHORS)


if __name__ == "__main__":
    unittest.main()

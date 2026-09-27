"""Run the real GroupDocs bake step against a frozen-migration QA source (D-068)."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/groupdocs-data-refresh.yml"
FROZEN_REF = "codex/ceph-migration-5a059efa3107b320-qa-groupdocs-app"
RECOVERY_REF = "homepages-agent/qa-refresh/groupdocs.app"

FAKE_CURL = '''#!/usr/bin/env python
import json, os
print(json.dumps({"repository": "conholdate/homepages", "site": "groupdocs.app",
                  "environment": "qa", "source_sha": os.environ["PROOF_LIVE_QA"]}))
'''
FAKE_AGENT = '''import argparse, json, pathlib
parser = argparse.ArgumentParser()
parser.add_argument("--homepages-repo")
parser.add_argument("command")
parser.add_argument("--site", default="")
parser.add_argument("--feed", default="")
args, _ = parser.parse_known_args()
if args.command == "metrics-bake":
    path = pathlib.Path(args.homepages_repo) / f"data/metrics/{args.site}.json"
    path.write_text(json.dumps({"count": 99}) + "\\n", encoding="utf-8")
'''


def bake_step_script() -> str:
    """Return the exact `run:` block of the workflow's bake step."""

    lines = WORKFLOW.read_text(encoding="utf-8").splitlines()
    start = lines.index("      - name: Bake and commit changed data")
    run = next(i for i in range(start, len(lines)) if lines[i].strip() == "run: |")
    body = []
    for line in lines[run + 1:]:
        if line.strip() and not line.startswith("          "):
            break
        body.append(line)
    return textwrap.dedent("\n".join(body)) + "\n"


class GroupDocsBakeFallbackTests(unittest.TestCase):
    def run_bake(self, *, recovery_ref_at_live: bool = False):
        bash = r"C:\Program Files\Git\bin\bash.exe" if os.name == "nt" else shutil.which("bash")
        self.assertTrue(bash and shutil.which("jq"), "Bash and real jq are required")
        with tempfile.TemporaryDirectory(prefix="groupdocs-bake-proof-") as temp:
            root = Path(temp)
            repo, remote, tools = root / "homepages", root / "remote.git", root / "bin"
            agent = root / "homepages-agent" / "homepages_agent"
            repo.mkdir(); tools.mkdir(); agent.mkdir(parents=True)
            env = os.environ | {
                "GIT_AUTHOR_NAME": "Homepages Agent", "GIT_COMMITTER_NAME": "Homepages Agent",
                "GIT_AUTHOR_EMAIL": "homepages.agent@conholdate.com",
                "GIT_COMMITTER_EMAIL": "homepages.agent@conholdate.com",
            }
            git_bin = shutil.which("git")

            def git(*args, cwd=repo):
                return subprocess.run([git_bin, *args], cwd=cwd, env=env, check=True,
                                      capture_output=True, text=True).stdout.strip()

            def write(path, text):
                file = repo / path
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text(text + "\n", encoding="utf-8")

            git("init", "-q", "-b", "qa-homepages-v1")
            write("data/metrics/groupdocs.app.json", '{"count":1}')
            write("content/groupdocs-app/_index.md", "aggregate copy")
            git("add", "."); git("commit", "-qm", "Aggregate QA")
            write("config/config-stage-groupdocs-app.toml", "ceph origin")
            git("add", "."); git("commit", "-qm", "Bind groupdocs.app qa to exact live Ceph origin")
            live = git("rev-parse", "HEAD")
            git("reset", "-q", "--hard", "HEAD~1")
            git("clone", "--bare", "-q", str(repo), str(remote), cwd=root)
            git("--git-dir=" + str(remote), "update-ref", f"refs/heads/{FROZEN_REF}", live, cwd=root)
            if recovery_ref_at_live:
                git("--git-dir=" + str(remote), "update-ref", f"refs/heads/{RECOVERY_REF}", live, cwd=root)
            git("remote", "add", "origin", str(remote))
            git("fetch", "-q", "origin")

            curl = tools / "curl"; curl.write_text(FAKE_CURL, encoding="utf-8"); curl.chmod(0o755)
            if os.name == "nt":
                jq = tools / "jq"
                jq.write_text('#!/usr/bin/env bash\nexec "$PROOF_JQ" --binary "$@"\n', encoding="utf-8")
                jq.chmod(0o755)
            (agent / "__init__.py").write_text("", encoding="utf-8")
            (agent / "__main__.py").write_text(FAKE_AGENT, encoding="utf-8")
            shutil.copytree(ROOT / ".github/scripts", root / "workflows/.github/scripts")
            script = root / "bake.sh"; script.write_text(bake_step_script(), encoding="utf-8")
            outputs = root / "outputs"; outputs.touch()
            env |= {
                "PATH": str(tools) + os.pathsep + env["PATH"],
                "PROOF_BIN": ("/" + tools.drive[0].lower() + tools.as_posix()[2:]) if os.name == "nt" else str(tools),
                "PROOF_JQ": shutil.which("jq") or "", "PROOF_LIVE_QA": live,
                "SITE": "groupdocs.app", "GITHUB_WORKSPACE": root.as_posix(),
                "GITHUB_OUTPUT": outputs.as_posix(), "GITHUB_RUN_ID": "4242",
                "HOMEPAGES_SOURCE_PAT": "fixture-only", "HOMEPAGES_QA_SOURCE_REF": "qa-homepages-v1",
                "GIT_TERMINAL_PROMPT": "0",
                # The step reads heads from the public URL; point it at the fixture remote.
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": f"url.{remote.as_posix()}.insteadOf",
                "GIT_CONFIG_VALUE_0": "https://github.com/conholdate/homepages.git",
            }
            result = subprocess.run(
                [bash, "-c", f'export PATH="$PROOF_BIN:$PATH"; source "{script.as_posix()}"'],
                env=env, capture_output=True, text=True, timeout=120,
            )
            produced = dict(line.split("=", 1) for line in outputs.read_text().splitlines() if "=" in line)
            refs = {
                name: subprocess.run([git_bin, "--git-dir=" + str(remote), "rev-parse", "--verify", "-q",
                                      f"refs/heads/{name}"], env=env, capture_output=True, text=True).stdout.strip()
                for name in (FROZEN_REF, RECOVERY_REF)
            }
            evidence = {}
            if produced.get("source_sha"):
                sha = produced["source_sha"]
                evidence = {
                    "parent": git("--git-dir=" + str(remote), "rev-parse", sha + "^", cwd=root),
                    "changed": git("--git-dir=" + str(remote), "diff", "--name-only", live, sha, cwd=root).split(),
                    "config": git("--git-dir=" + str(remote), "show", f"{sha}:config/config-stage-groupdocs-app.toml", cwd=root),
                }
            return result, produced, refs, evidence, live

    def test_frozen_migration_source_bakes_onto_a_new_site_refresh_branch(self):
        result, produced, refs, evidence, live = self.run_bake()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual("true", produced["changed"])
        self.assertEqual(live, produced["before_sha"])
        self.assertEqual(produced["source_sha"], refs[RECOVERY_REF])
        self.assertEqual(live, refs[FROZEN_REF])  # the frozen migration record is never written
        self.assertEqual(live, evidence["parent"])
        self.assertEqual(["data/metrics/groupdocs.app.json"], evidence["changed"])
        self.assertEqual("ceph origin", evidence["config"])  # live QA content is kept

    def test_existing_site_refresh_branch_is_advanced_with_a_lease(self):
        result, produced, refs, evidence, live = self.run_bake(recovery_ref_at_live=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(produced["source_sha"], refs[RECOVERY_REF])
        self.assertEqual(live, refs[FROZEN_REF])
        self.assertEqual(live, evidence["parent"])


if __name__ == "__main__":
    unittest.main()

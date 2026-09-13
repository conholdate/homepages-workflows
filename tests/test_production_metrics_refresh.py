"""Execute the shared refresh at real commit/push and dispatch boundaries."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github/scripts/refresh-production-metrics.sh"
SITES = ("groupdocs.com", "groupdocs.cloud", "groupdocs.app")


class ProductionMetricsRefreshTests(unittest.TestCase):
    def run_refresh(self, *, mode="success", sites=SITES, source_override=None):
        bash = r"C:\Program Files\Git\bin\bash.exe" if os.name == "nt" else shutil.which("bash")
        self.assertTrue(bash and shutil.which("jq"), "Bash and real jq are required")
        with tempfile.TemporaryDirectory(prefix="production-metrics-proof-") as temp:
            root = Path(temp)
            repo, remote, tools = root / "homepages", root / "remote.git", root / "bin"
            repo.mkdir(); tools.mkdir()
            env = os.environ | {
                "GIT_AUTHOR_NAME": "Homepages Agent", "GIT_COMMITTER_NAME": "Homepages Agent",
                "GIT_AUTHOR_EMAIL": "homepages.agent@conholdate.com",
                "GIT_COMMITTER_EMAIL": "homepages.agent@conholdate.com",
            }
            git_bin = shutil.which("git")
            fixture_sites = tuple(dict.fromkeys((*SITES, *sites)))
            def git(*args):
                return subprocess.run([git_bin, *args], cwd=repo, env=env, check=True,
                                      capture_output=True, text=True).stdout.strip()
            git("init", "-q")
            for site in fixture_sites:
                file = repo / f"data/metrics/{site}.json"
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text('{"count":1}\n', encoding="utf-8")
            content = repo / "content/homepage.md"
            content.parent.mkdir(); content.write_text("approved live copy\n", encoding="utf-8")
            theme = repo / "themes/shared/style.css"
            theme.parent.mkdir(parents=True); theme.write_text("approved live style\n", encoding="utf-8")
            git("add", "."); git("commit", "-qm", "Live source")
            live = git("rev-parse", "HEAD")
            git("clone", "--bare", "-q", str(repo), str(remote))
            git("remote", "add", "origin", str(remote))
            for site in fixture_sites:
                (repo / f"data/metrics/{site}.json").write_text('{"count":2}\n', encoding="utf-8")
            content.write_text("UNAPPROVED QA COPY\n", encoding="utf-8")
            theme.write_text("UNAPPROVED QA STYLE\n", encoding="utf-8")
            git("add", "."); git("commit", "-qm", "Different QA source")
            qa = git("rev-parse", "HEAD")
            state = root / "state.json"
            state.write_text(json.dumps({"sources": {s: live for s in fixture_sites}, "runs": [], "mode": mode}), encoding="utf-8")
            fake = '''#!/usr/bin/env python
import json, os, subprocess, sys
from pathlib import Path
from urllib.parse import urlsplit
p=Path(os.environ["PROOF_STATE"]); state=json.loads(p.read_text()); args=sys.argv[1:]
kind=Path(sys.argv[0]).name
state.setdefault("calls",[]).append([kind,*args])
p.write_text(json.dumps(state))
if kind == "curl":
    url=args[-1]; site=urlsplit(url).hostname.removeprefix("www.")
    sha=state["sources"][site]
    if state["mode"] == "drift" and "pre-dispatch" in url: sha="f"*40
    print(json.dumps({"repository":"conholdate/homepages", "site":site, "environment":"production", "source_sha":sha}))
elif args[:2] == ["workflow","run"]:
    fields=dict(a.split("=",1) for n,a in enumerate(args) if n and args[n-1] == "-f")
    assert fields["environment"] == "production" and len(fields["ref"]) == 40
    run={"id":len(state["runs"])+91,"display_title":"Deploy tx="+fields["transaction_id"],"created_at":"2026-09-13", **fields}
    state["runs"].append(run)
    if state["mode"] != "failed": state["sources"][fields["site"]]=fields["ref"]
    p.write_text(json.dumps(state))
elif args[0] == "api":
    if "actions/workflows/" in args[1]: print(json.dumps({"workflow_runs":state["runs"]}))
    else: print(json.dumps({"status":"completed", "conclusion":"failure" if state["mode"] == "failed" else "success"}))
else: raise SystemExit("Unexpected external boundary: "+repr(args))
'''
            for name in ("curl", "gh"):
                file = tools / name; file.write_text(fake, encoding="utf-8"); file.chmod(0o755)
            if os.name == "nt":
                # Native Windows jq otherwise emits CRLF into Bash variables;
                # use the real binary in binary mode, matching Linux stdout.
                file = tools / "jq"
                file.write_text('#!/usr/bin/env bash\nexec "$PROOF_JQ" --binary "$@"\n', encoding="utf-8")
                file.chmod(0o755)
            shutil.copytree(ROOT / ".github/scripts", root / "workflows/.github/scripts")
            output = root / "outputs"; output.touch()
            env |= {
                "PATH": str(tools) + os.pathsep + env["PATH"],
                "GITHUB_WORKSPACE": root.as_posix(), "GITHUB_OUTPUT": output.as_posix(),
                "GITHUB_REPOSITORY": "conholdate/homepages-workflows", "GITHUB_RUN_ID": "12345",
                "HOMEPAGES_SOURCE_PAT": "fixture-only", "METRICS_SOURCE_SHA": source_override or qa,
                "METRICS_REFRESH_SITES": " ".join(sites), "PROOF_STATE": str(state),
                "PROOF_REMOTE": str(remote), "PROOF_GIT": git_bin,
                "PROOF_BIN": ("/" + tools.drive[0].lower() + tools.as_posix()[2:]) if os.name == "nt" else str(tools),
                "PROOF_SCRIPT": SCRIPT.as_posix(), "GIT_TERMINAL_PROMPT": "0",
                "PROOF_JQ": shutil.which("jq"),
            }
            result = subprocess.run([bash, "-c", 'export PATH="$PROOF_BIN:$PATH"; source "$PROOF_SCRIPT"'], env=env, capture_output=True,
                                    text=True, timeout=60)
            delivered = json.loads(state.read_text())
            if mode == "success" and source_override is None:
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                self.assertEqual(len(sites), len(delivered["runs"]))
                for run in delivered["runs"]:
                    sha, site = run["ref"], run["site"]
                    self.assertEqual(live, git("rev-parse", sha + "^"))
                    self.assertEqual(f"data/metrics/{site}.json", git("diff", "--name-only", live, sha))
                    self.assertEqual("approved live copy", git("show", sha + ":content/homepage.md"))
                    self.assertEqual("approved live style", git("show", sha + ":themes/shared/style.css"))
                    self.assertEqual('{"count":2}', git("show", sha + f":data/metrics/{site}.json"))
                    self.assertEqual(sha, git("--git-dir=" + str(remote), "rev-parse", "refs/heads/homepages-agent/production-metrics-refresh/" + site))
                    message = git("log", "-1", "--format=%B", sha)
                    parsed = subprocess.run([git_bin, "interpret-trailers", "--parse"], input=message,
                                            capture_output=True, text=True, check=True).stdout
                    self.assertEqual(3, parsed.count("Co-authored-by:"))
            else:
                self.assertNotEqual(0, result.returncode, result.stdout + result.stderr)
            return delivered, result

    def test_groupdocs_exact_live_parents_never_promote_qa_copy_theme_or_sibling_metrics(self):
        self.run_refresh()

    def test_aspose_caller_uses_same_exact_parent_boundary(self):
        self.run_refresh(sites=("aspose.com",))

    def test_public_parent_drift_stops_before_dispatch(self):
        state, _ = self.run_refresh(mode="drift", sites=("groupdocs.com",))
        self.assertEqual([], state["runs"])

    def test_failed_deployment_is_not_reported_as_verified(self):
        _, result = self.run_refresh(mode="failed", sites=("groupdocs.com",))
        self.assertNotIn("Verified groupdocs.com production", result.stdout)

    def test_abbreviated_source_stops_before_any_dispatch(self):
        state, _ = self.run_refresh(source_override="abcdef0")
        self.assertEqual([], state["runs"])


if __name__ == "__main__":
    unittest.main()

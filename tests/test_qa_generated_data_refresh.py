"""Execute the shared QA generated-data publisher at real git and dispatch boundaries (D-067)."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github/scripts/refresh-qa-generated-data.sh"
ACTIVE_REF = "homepages-agent/qa-changes/active"

FAKE = '''#!/usr/bin/env python
import json, os, sys
from pathlib import Path
from urllib.parse import urlsplit
p=Path(os.environ["PROOF_STATE"]); state=json.loads(p.read_text()); args=sys.argv[1:]
kind=Path(sys.argv[0]).name
if kind == "curl":
    url=urlsplit(args[-1]); site=url.hostname.removeprefix("qa.")
    if url.path.endswith("homepages-deployment.json"):
        sha=state["sources"][site]
        if state["mode"] == "drift" and "pre-dispatch" in url.query: sha="f"*40
        print(json.dumps({"repository":"conholdate/homepages","site":site,"environment":"qa","source_sha":sha}))
    else:
        print('<html><head><meta name="robots" content="noindex"></head></html>')
elif args[:2] == ["workflow","run"]:
    fields=dict(a.split("=",1) for n,a in enumerate(args) if n and args[n-1] == "-f")
    assert fields["environment"] == "qa" and len(fields["ref"]) == 40, fields
    site=fields["site"]
    assert fields["expected_live_sha"] == state["sources"][site], (fields, state["sources"][site])
    prior=[r for r in state["runs"] if r["site"] == site]
    conflict = state["mode"] == "conflict_always" or (state["mode"] == "conflict_once" and not prior)
    run={"id":len(state["runs"])+91,"display_title":"Deploy tx="+fields["transaction_id"],
         "created_at":"2026-09-27","conclusion":"failure" if conflict else "success", **fields}
    state["runs"].append(run)
    if conflict:
        users=state["user_shas"]; state["sources"][site]=users[len(prior) % len(users)]
    else:
        state["sources"][site]=fields["ref"]
    p.write_text(json.dumps(state))
elif args[0] == "api":
    if "actions/workflows/" in args[1]:
        print(json.dumps({"workflow_runs":state["runs"]}))
    else:
        run=[r for r in state["runs"] if args[1].endswith("/" + str(r["id"]))][0]
        print(json.dumps({"status":"completed","conclusion":run["conclusion"]}))
else:
    raise SystemExit("Unexpected external boundary: "+repr(args))
'''


class QAGeneratedDataRefreshTests(unittest.TestCase):
    def run_refresh(self, *, mode="success", site="aspose.org", live="active",
                    templates="", source_ref_ok=True):
        bash = r"C:\Program Files\Git\bin\bash.exe" if os.name == "nt" else shutil.which("bash")
        self.assertTrue(bash and shutil.which("jq"), "Bash and real jq are required")
        with tempfile.TemporaryDirectory(prefix="qa-generated-data-proof-") as temp:
            root = Path(temp)
            repo, remote, tools = root / "homepages", root / "remote.git", root / "bin"
            repo.mkdir(); tools.mkdir()
            env = os.environ | {
                "GIT_AUTHOR_NAME": "Homepages Agent", "GIT_COMMITTER_NAME": "Homepages Agent",
                "GIT_AUTHOR_EMAIL": "homepages.agent@conholdate.com",
                "GIT_COMMITTER_EMAIL": "homepages.agent@conholdate.com",
            }
            git_bin = shutil.which("git")

            def git(*args):
                return subprocess.run([git_bin, *args], cwd=repo, env=env, check=True,
                                      capture_output=True, text=True).stdout.strip()

            def write(path, text):
                file = repo / path
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text(text + "\n", encoding="utf-8")

            key = site.replace(".", "_")
            git("init", "-q", "-b", "qa-homepages-v1")
            write(f"data/metrics/{site}.json", '{"count":1}')
            write(f"data/homepage_resource_feeds/{key}.json", '{"feed":1}')
            write("data/products.json", '{"catalog":1}')
            write("content/homepage.md", "base qa copy")
            git("add", "."); git("commit", "-qm", "QA base")
            base = git("rev-parse", "HEAD")
            # The aggregate refresh: new metrics/feed plus a catalog change that
            # must never leak onto a different active QA version.
            write(f"data/metrics/{site}.json", '{"count":2}')
            write(f"data/homepage_resource_feeds/{key}.json", '{"feed":2}')
            write("data/products.json", '{"catalog":2}')
            git("commit", "-qam", "Refresh generated data")
            refreshed = git("rev-parse", "HEAD")
            # An agent QA change currently live on QA, and two newer user QA versions.
            git("checkout", "-q", "-b", "active", base)
            write("content/homepage.md", "ACTIVE QA CHANGE")
            git("commit", "-qam", "Active QA change")
            active = git("rev-parse", "HEAD")
            user_shas = []
            for index in (1, 2):
                git("checkout", "-q", "-b", f"user{index}", active)
                write("content/homepage.md", f"USER QA {index}")
                git("commit", "-qam", f"User QA {index}")
                user_shas.append(git("rev-parse", "HEAD"))
            git("checkout", "-q", "qa-homepages-v1")
            git("clone", "--bare", "-q", str(repo), str(remote))
            git("remote", "add", "origin", str(remote))
            git("--git-dir=" + str(remote), "update-ref", f"refs/heads/{ACTIVE_REF}", active)
            for index, sha in enumerate(user_shas, 1):
                git("--git-dir=" + str(remote), "update-ref", f"refs/heads/homepages-agent/qa-changes/user{index}", sha)
            if not source_ref_ok:
                git("--git-dir=" + str(remote), "update-ref", "refs/heads/qa-homepages-v1", base)

            live_sha = {"base": base, "active": active}[live]
            state = root / "state.json"
            state.write_text(json.dumps({"sources": {site: live_sha}, "runs": [], "mode": mode,
                                         "user_shas": user_shas}), encoding="utf-8")
            for name in ("curl", "gh"):
                file = tools / name; file.write_text(FAKE, encoding="utf-8"); file.chmod(0o755)
            if os.name == "nt":
                file = tools / "jq"
                file.write_text('#!/usr/bin/env bash\nexec "$PROOF_JQ" --binary "$@"\n', encoding="utf-8")
                file.chmod(0o755)
            shutil.copytree(ROOT / ".github/scripts", root / "workflows/.github/scripts")
            env |= {
                "PATH": str(tools) + os.pathsep + env["PATH"],
                "GITHUB_WORKSPACE": root.as_posix(), "GITHUB_REPOSITORY": "conholdate/homepages-workflows",
                "GITHUB_RUN_ID": "777", "HOMEPAGES_SOURCE_PAT": "fixture-only",
                "HOMEPAGES_QA_SOURCE_REF": "qa-homepages-v1", "QA_REFRESH_SITES": site,
                "REFRESHED_SOURCE_SHA": refreshed, "REFRESH_BASE_SHA": base,
                "REFRESH_SOURCE_REF": "qa-homepages-v1", "GENERATED_PATHS": templates,
                "PROOF_STATE": str(state), "PROOF_JQ": shutil.which("jq") or "",
                "PROOF_BIN": ("/" + tools.drive[0].lower() + tools.as_posix()[2:]) if os.name == "nt" else str(tools),
                "PROOF_SCRIPT": SCRIPT.as_posix(), "GIT_TERMINAL_PROMPT": "0",
            }
            if not templates:
                env.pop("GENERATED_PATHS")
            result = subprocess.run([bash, "-c", 'export PATH="$PROOF_BIN:$PATH"; source "$PROOF_SCRIPT"'],
                                    env=env, capture_output=True, text=True, timeout=120)
            delivered = json.loads(state.read_text())
            refs = {"base": base, "refreshed": refreshed, "active": active, "users": user_shas}
            # Read the evidence while the fixture repository still exists.
            cache: dict[tuple, object] = {}
            for run in delivered["runs"]:
                sha, parent = run["ref"], run["expected_live_sha"]
                cache[("changed", parent, sha)] = git(
                    "--git-dir=" + str(remote), "diff", "--name-only", parent, sha).split()
                for path in ("content/homepage.md", "data/products.json",
                             f"data/metrics/{site}.json", f"data/homepage_resource_feeds/{key}.json"):
                    cache[("show", sha, path)] = git("--git-dir=" + str(remote), "show", f"{sha}:{path}")

            def show(sha, path):
                return cache[("show", sha, path)]

            def changed(parent, sha):
                return cache[("changed", parent, sha)]

            return delivered, result, refs, show, changed

    def test_live_base_deploys_the_refreshed_source_as_is(self):
        state, result, refs, _show, _changed = self.run_refresh(live="base")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        (run,) = state["runs"]
        self.assertEqual(refs["refreshed"], run["ref"])
        self.assertEqual(refs["base"], run["expected_live_sha"])

    def test_active_qa_change_receives_only_generated_files(self):
        state, result, refs, show, changed = self.run_refresh(live="active")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        (run,) = state["runs"]
        self.assertEqual(refs["active"], run["expected_live_sha"])
        self.assertEqual(["data/metrics/aspose.org.json"], changed(refs["active"], run["ref"]))
        self.assertEqual("ACTIVE QA CHANGE", show(run["ref"], "content/homepage.md"))
        self.assertEqual('{"catalog":1}', show(run["ref"], "data/products.json"))

    def test_groupdocs_templates_also_carry_the_resource_feed(self):
        state, result, refs, show, changed = self.run_refresh(
            site="groupdocs.com",
            templates="data/metrics/{site}.json data/homepage_resource_feeds/{key}.json",
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        (run,) = state["runs"]
        self.assertEqual(
            ["data/homepage_resource_feeds/groupdocs_com.json", "data/metrics/groupdocs.com.json"],
            sorted(changed(refs["active"], run["ref"])),
        )
        self.assertEqual('{"feed":2}', show(run["ref"], "data/homepage_resource_feeds/groupdocs_com.json"))

    def test_retry_rebuilds_on_the_newer_qa_version_without_overwriting_it(self):
        state, result, refs, show, changed = self.run_refresh(mode="conflict_once")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        first, retry = state["runs"]
        user = refs["users"][0]
        self.assertEqual(refs["active"], first["expected_live_sha"])
        self.assertEqual(user, retry["expected_live_sha"])
        self.assertIn("-r2", retry["transaction_id"])
        self.assertEqual("USER QA 1", show(retry["ref"], "content/homepage.md"))
        self.assertEqual(["data/metrics/aspose.org.json"], changed(user, retry["ref"]))
        self.assertEqual('{"count":2}', show(retry["ref"], "data/metrics/aspose.org.json"))
        self.assertEqual(retry["ref"], state["sources"]["aspose.org"])

    def test_refresh_stops_loudly_after_three_conflicts(self):
        state, result, *_ = self.run_refresh(mode="conflict_always")
        self.assertNotEqual(0, result.returncode)
        self.assertEqual(3, len(state["runs"]))
        self.assertIn("after 3 attempts", result.stdout + result.stderr)

    def test_qa_changing_before_every_dispatch_never_deploys(self):
        state, result, *_ = self.run_refresh(mode="drift")
        self.assertNotEqual(0, result.returncode)
        self.assertEqual([], state["runs"])

    def test_drifted_aggregate_source_ref_stops_before_any_dispatch(self):
        state, result, *_ = self.run_refresh(source_ref_ok=False)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual([], state["runs"])


if __name__ == "__main__":
    unittest.main()

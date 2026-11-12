"""A site sharing its bucket with another owner's pages deploys only its home pages (D-136).

aspose.info's bucket also holds the Info Agent's ~55,000 article pages. The deployment profile's
`scope: home-pages` makes the resolver require a Hugo `include` of exactly the home page in every
language, the identity file and /homepage/**, turns deletes off and purges only those URLs.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github" / "scripts" / "resolve_deployment_profile.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("resolve_deployment_profile_scope", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

MANIFEST = """sites:
  example.info:
    production_config: config/site.toml
    stage_config: config/site.toml
    production_hugo: 0.162.0
    stage_hugo: 0.162.0
"""
HOME_PAGES = "{index.html,de/index.html,ar/index.html,.well-known/homepages-deployment.json,homepage/**}"


def _config(include: str | None = HOME_PAGES, extra: str = "", asset_base: str = "/homepage") -> str:
    target = '[[deployment.targets]]\nname = "staging_ceph"\nURL = "s3://qa-example-info"\n'
    if include is not None:
        target += f"include = {json.dumps(include)}\n"
    return (
        'defaultContentLanguage = "en"\n'
        "defaultContentLanguageInSubdir = false\n"
        f"[params]\nasset_base = {json.dumps(asset_base)}\n"
        "[languages.en]\nweight = 1\n[languages.de]\nweight = 2\n[languages.ar]\nweight = 3\n"
        "[deployment]\n" + target + extra
    )


def _profiles(scope: str | None = "home-pages", url: str = "https://qa.example.info/") -> dict:
    profile = {"credential_set": "ceph_qa", "targets": ["staging_ceph"], "cache": {"kind": "bunny", "url": url}}
    if scope is not None:
        profile["scope"] = scope
    return {"schema_version": 1, "sites": {"example.info": {"qa": profile, "production": profile}}}


class SharedBucketScopeTests(unittest.TestCase):
    def _resolve(self, config: str, profiles: dict) -> dict[str, str]:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config").mkdir()
            (root / "config" / "site.toml").write_text(config, encoding="utf-8")
            return MODULE.resolve_profile(
                manifest_text=MANIFEST, profiles=profiles, config_root=root, site="example.info", environment="qa"
            )

    def test_home_pages_scope_deletes_nothing_and_purges_only_home_pages(self) -> None:
        result = self._resolve(_config(), _profiles())
        self.assertEqual("0", result["max_deletes"])
        self.assertEqual(
            [
                "https://qa.example.info/",
                "https://qa.example.info/de/",
                "https://qa.example.info/ar/",
                "https://qa.example.info/.well-known/homepages-deployment.json",
            ],
            result["cache_url"].split(","),
        )

    def test_unscoped_site_keeps_full_sync(self) -> None:
        result = self._resolve(_config(include=None), _profiles(scope=None, url="https://qa.example.info/*"))
        self.assertEqual("-1", result["max_deletes"])
        self.assertEqual("https://qa.example.info/*", result["cache_url"])

    def test_scope_refuses_any_include_that_could_reach_other_pages(self) -> None:
        for include in (
            None,
            "",
            "**",
            "{index.html,*/index.html,.well-known/homepages-deployment.json,homepage/**}",
            HOME_PAGES.replace("}", ",data/index.html}"),
            HOME_PAGES.replace("ar/index.html,", ""),
            HOME_PAGES.replace("de/index.html", "de/index.html,de/index.html"),
        ):
            with self.subTest(include=include):
                with self.assertRaisesRegex(ValueError, "include"):
                    self._resolve(_config(include=include), _profiles())
        with self.assertRaisesRegex(ValueError, "include"):
            self._resolve(_config(extra='exclude = "x"\n'), _profiles())

    def test_assets_folder_comes_from_the_site_config(self) -> None:
        include = HOME_PAGES.replace("homepage/**", "home-assets/**")
        self.assertEqual("0", self._resolve(_config(include=include, asset_base="/home-assets"), _profiles())["max_deletes"])
        with self.assertRaisesRegex(ValueError, "include"):
            self._resolve(_config(asset_base="/home-assets"), _profiles())
        for bad in ("", "/", "/a/b", "homepage", "/../x"):
            with self.subTest(asset_base=bad), self.assertRaisesRegex(ValueError, "asset_base"):
                self._resolve(_config(asset_base=bad), _profiles())

    def test_scope_refuses_wildcard_purge_and_unknown_scope(self) -> None:
        with self.assertRaisesRegex(ValueError, "Bunny site root"):
            self._resolve(_config(), _profiles(url="https://qa.example.info/*"))
        with self.assertRaisesRegex(ValueError, "unsupported deployment scope"):
            self._resolve(_config(), _profiles(scope="everything"))

    def test_registered_shared_bucket_site_is_scoped_in_both_environments(self) -> None:
        profiles = json.loads((SCRIPT.parent / "deployment-profiles.json").read_text(encoding="utf-8"))
        for environment in ("qa", "production"):
            profile = profiles["sites"]["aspose.info"][environment]
            self.assertEqual("home-pages", profile["scope"])
            self.assertRegex(profile["cache"]["url"], r"^https://(qa|www)\.aspose\.info/$")

    def test_workflow_passes_the_profile_max_deletes_to_hugo_deploy(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "deploy-homepage.yml").read_text(encoding="utf-8")
        self.assertIn('--maxDeletes "$MAX_DELETES"', workflow)
        self.assertNotIn("--maxDeletes -1", workflow)
        self.assertIn("MAX_DELETES: ${{ steps.map.outputs.max_deletes }}", workflow)
        self.assertTrue(re.search(r'IFS=\',\' read -ra purge_urls <<< "\$CACHE_URL"', workflow))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import re
import sys
import tomllib

from resolve_manifest_hugo import resolve_manifest_hugo


_SAFE_VALUE = re.compile(r"[^\r\n]*")
_CREDENTIAL_SETS = {"sl", "standard", "homepages", "ceph_qa", "ceph_production"}
_CACHE_SELECTORS = {
    "none": set(),
    "cloudfront": {"variable", "alias"},
    "cloudfront-deploy-account": {"alias"},
    "bunny": {"url"},
}


def _site_lines(text: str, site: str) -> list[str]:
    lines = text.replace("\r\n", "\n").splitlines()
    header = f"  {site}:"
    try:
        start = lines.index(header) + 1
    except ValueError as exc:
        raise ValueError(f"site is not registered: {site}") from exc
    end = len(lines)
    for index in range(start, len(lines)):
        if lines[index].startswith("  ") and not lines[index].startswith("    "):
            end = index
            break
    return lines[start:end]


def _manifest_scalar(lines: list[str], key: str) -> str:
    pattern = re.compile(rf"    {re.escape(key)}:\s*['\"]?([^\s'\"]+)['\"]?\s*")
    values = [match.group(1) for line in lines if (match := pattern.fullmatch(line))]
    if len(values) != 1:
        raise ValueError(f"site has no unique {key} contract")
    return values[0]


def _validated_config_path(config_root: Path, value: str) -> Path:
    relative = PurePosixPath(value)
    if relative.is_absolute() or ".." in relative.parts or relative.suffix != ".toml":
        raise ValueError(f"unsafe homepage config path: {value}")
    path = config_root.joinpath(*relative.parts)
    if not path.is_file():
        raise ValueError(f"homepage config does not exist: {value}")
    return path


def _validate_targets(config_path: Path, targets: list[str]) -> dict[str, dict[str, object]]:
    data = tomllib.loads(config_path.read_text(encoding="utf-8-sig"))
    configured = {
        str(item.get("name", "")): item
        for item in data.get("deployment", {}).get("targets", [])
        if isinstance(item, dict)
    }
    missing = [target for target in targets if target not in configured]
    if missing:
        raise ValueError(
            f"deployment target(s) missing from {config_path.name}: {', '.join(missing)}"
        )
    return configured


# A site that shares its bucket with another owner's pages (aspose.info, D-136) deploys only its
# home page in every language, its identity file and its own assets under /homepage/.
HOME_PAGES_SCOPE = "home-pages"
_HOME_PAGES_FIXED = ("index.html", ".well-known/homepages-deployment.json", "homepage/**")


def _home_page_languages(config_path: Path) -> list[str]:
    data = tomllib.loads(config_path.read_text(encoding="utf-8-sig"))
    default = str(data.get("defaultContentLanguage") or "en")
    languages = data.get("languages")
    if not isinstance(languages, dict) or default not in languages:
        raise ValueError(f"{config_path.name} has no language list with its default language")
    if data.get("defaultContentLanguageInSubdir"):
        raise ValueError(f"{config_path.name} serves its default language in a folder")
    codes = [str(code) for code in languages if str(code) != default]
    if any(not re.fullmatch(r"[a-z]{2,3}(?:-[a-z]{2,4})?", code) for code in codes):
        raise ValueError(f"{config_path.name} has a language code that is not a plain folder name")
    return codes


def _validate_home_pages_scope(
    config_path: Path, configured: dict[str, dict[str, object]], targets: list[str]
) -> list[str]:
    """Every target uploads and deletes exactly the home pages; returns the non-default languages."""

    codes = _home_page_languages(config_path)
    expected = set(_HOME_PAGES_FIXED) | {f"{code}/index.html" for code in codes}
    for target in targets:
        item = configured[target]
        include = str(item.get("include") or "")
        if item.get("exclude") or not (include.startswith("{") and include.endswith("}")):
            raise ValueError(f"{target} must list its home pages in one `include` and no `exclude`")
        listed = include[1:-1].split(",")
        if len(listed) != len(set(listed)) or set(listed) != expected:
            extra = sorted(set(listed) - expected)
            absent = sorted(expected - set(listed))
            raise ValueError(
                f"{target} `include` must be exactly the home pages: extra {extra}, missing {absent}"
            )
    return codes


def resolve_profile(
    *,
    manifest_text: str,
    profiles: dict[str, object],
    config_root: Path,
    site: str,
    environment: str,
) -> dict[str, str]:
    if environment not in {"qa", "production"}:
        raise ValueError("environment must be qa or production")
    if profiles.get("schema_version") != 1 or not isinstance(profiles.get("sites"), dict):
        raise ValueError("deployment profiles must use schema_version 1")

    lines = _site_lines(manifest_text, site)
    config_key = "stage_config" if environment == "qa" else "production_config"
    config = _manifest_scalar(lines, config_key)
    hugo_version = resolve_manifest_hugo(
        manifest_text, site=site, environment=environment
    )
    config_path = _validated_config_path(config_root, config)

    site_profiles = profiles["sites"]
    site_profile = site_profiles.get(site)
    if not isinstance(site_profile, dict):
        raise ValueError(f"site has no deployment profile: {site}")
    profile = site_profile.get(environment)
    if not isinstance(profile, dict) or set(profile) - {"scope"} != {"credential_set", "targets", "cache"}:
        raise ValueError(f"{site}/{environment} has an invalid deployment profile")
    scope = profile.get("scope", "")
    if scope not in {"", HOME_PAGES_SCOPE}:
        raise ValueError(f"{site}/{environment} has an unsupported deployment scope")
    credential_set = profile["credential_set"]
    if credential_set not in _CREDENTIAL_SETS:
        raise ValueError(f"{site}/{environment} has an unsupported credential set")
    targets = profile["targets"]
    if (
        not isinstance(targets, list)
        or not targets
        or any(not isinstance(target, str) or not target.strip() for target in targets)
    ):
        raise ValueError(f"{site}/{environment} has invalid deployment targets")
    configured = _validate_targets(config_path, targets)
    languages = (
        _validate_home_pages_scope(config_path, configured, targets) if scope == HOME_PAGES_SCOPE else []
    )
    cache = profile["cache"]
    if not isinstance(cache, dict) or "kind" not in cache:
        raise ValueError(f"{site}/{environment} has an invalid cache profile")
    cache_kind = cache["kind"]
    if cache_kind not in _CACHE_SELECTORS:
        raise ValueError(f"{site}/{environment} has an unsupported cache kind")
    selectors = set(cache) - {"kind"}
    allowed = _CACHE_SELECTORS[cache_kind]
    if cache_kind == "cloudfront":
        if len(selectors) != 1 or not selectors <= allowed:
            raise ValueError(f"{site}/{environment} cloudfront cache needs one selector")
    elif selectors != allowed:
        raise ValueError(f"{site}/{environment} has an invalid cache selector")
    cache_url = str(cache.get("url", ""))
    if scope == HOME_PAGES_SCOPE:
        # Purge only the home pages and the identity file, never the other owner's pages.
        if cache_kind != "bunny" or not re.fullmatch(r"https://[a-z0-9.-]+/", cache_url):
            raise ValueError(f"{site}/{environment} home-pages scope needs a Bunny site root URL")
        cache_url = ",".join(
            [cache_url, *(f"{cache_url}{code}/" for code in languages),
             f"{cache_url}.well-known/homepages-deployment.json"]
        )

    result = {
        "config": config,
        "targets": ",".join(targets),
        "credential_set": str(credential_set),
        "cache_kind": str(cache_kind),
        "cache_variable": str(cache.get("variable", "")),
        "cache_alias": str(cache.get("alias", "")),
        "cache_url": cache_url,
        "hugo_version": hugo_version,
        # Hugo deploy deletes stale files only inside a scoped target's `include`; a shared bucket
        # deletes nothing at all, so a wrong matcher can never remove another owner's page.
        "max_deletes": "0" if scope == HOME_PAGES_SCOPE else "-1",
    }
    if any(not _SAFE_VALUE.fullmatch(value) for value in result.values()):
        raise ValueError("deployment profile contains an unsafe output value")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--profiles", type=Path, required=True)
    parser.add_argument("--config-root", type=Path, required=True)
    parser.add_argument("--site", required=True)
    parser.add_argument("--environment", choices=("qa", "production"), required=True)
    args = parser.parse_args()
    try:
        result = resolve_profile(
            manifest_text=args.manifest.read_text(encoding="utf-8-sig"),
            profiles=json.loads(args.profiles.read_text(encoding="utf-8")),
            config_root=args.config_root,
            site=args.site.strip(),
            environment=args.environment,
        )
    except (OSError, ValueError, json.JSONDecodeError, tomllib.TOMLDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for key, value in result.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

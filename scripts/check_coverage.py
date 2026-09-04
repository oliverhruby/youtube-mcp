"""Verify that the generated YouTube API operations matrix covers all
methods published in the upstream Google discovery documents.

Exit code 0 = all discovery methods accounted for (generated or ignored).
Exit code 1 = missing methods or stale ignores.
"""

import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATED_FILE = ROOT / "src" / "youtube_mcp" / "data" / "youtube_api_operations.json"
IGNORE_FILE = ROOT / "scripts" / "youtube_api_ignored_methods.json"

DISCOVERY_URLS = {
    "youtube_data_v3": "https://www.googleapis.com/discovery/v1/apis/youtube/v3/rest",
    "youtube_analytics_v2": "https://youtubeanalytics.googleapis.com/$discovery/rest?version=v2",
    "youtube_reporting_v1": "https://youtubereporting.googleapis.com/$discovery/rest?version=v1",
}


def _sanitize(name: str) -> str:
    return re.sub(r"[^a-z0-9_]", "_", name.lower())


def _fetch_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def collect_discovery_method_ids() -> set[str]:
    """Return set of tool_names that the discovery docs would generate."""
    method_ids: set[str] = set()
    for api_key, url in DISCOVERY_URLS.items():
        doc = _fetch_json(url)
        _walk(doc.get("methods", {}), api_key, [], method_ids)
        _walk_resources(doc.get("resources", {}), api_key, [], method_ids)
    return method_ids


def _walk(methods: dict, api_key: str, chain: list[str], out: set[str]):
    for method_name in methods:
        tool_name = _sanitize("_".join([api_key, *chain, method_name]))
        out.add(tool_name)


def _walk_resources(resources: dict, api_key: str, chain: list[str], out: set[str]):
    for resource_name, resource in resources.items():
        next_chain = [*chain, resource_name]
        _walk(resource.get("methods", {}), api_key, next_chain, out)
        _walk_resources(resource.get("resources", {}), api_key, next_chain, out)


def load_generated_tool_names() -> set[str]:
    data = json.loads(GENERATED_FILE.read_text(encoding="utf-8"))
    return {item["tool_name"] for item in data}


def load_ignored() -> dict:
    if not IGNORE_FILE.exists():
        return {}
    data = json.loads(IGNORE_FILE.read_text(encoding="utf-8"))
    ignored = data.get("ignored_methods", {})
    if not isinstance(ignored, dict):
        raise ValueError("ignored_methods must be an object of tool_name -> reason")
    return ignored


def main() -> int:
    print("Fetching discovery documents...")
    discovery_names = collect_discovery_method_ids()
    generated_names = load_generated_tool_names()
    ignored = load_ignored()

    missing = sorted(discovery_names - generated_names - set(ignored))
    stale = sorted(set(ignored) - discovery_names)
    extra = sorted(generated_names - discovery_names - set(ignored))

    print(f"Discovery methods: {len(discovery_names)}")
    print(f"Generated tools:   {len(generated_names)}")
    print(f"Ignored:           {len(ignored)}")
    print(f"Missing:           {len(missing)}")
    print(f"Stale ignores:     {len(stale)}")
    print(f"Extra generated:   {len(extra)}")

    failed = False

    if missing:
        print("\nERROR: discovery methods not in generated matrix or ignore list:")
        for name in missing:
            print(f"  - {name}")
        failed = True

    if stale:
        print("\nERROR: ignored methods no longer in discovery docs:")
        for name in stale:
            print(f"  - {name}")
        failed = True

    if extra:
        print("\nWARNING: generated tools not in discovery docs (may be intentional):")
        for name in extra:
            print(f"  - {name}")

    if failed:
        print("\nFAILED: coverage drift detected.")
        return 1

    print("\nOK: all discovery methods are covered.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

import json
import re
import urllib.request
from pathlib import Path


DISCOVERY_URLS = {
    "youtube_data_v3": "https://www.googleapis.com/discovery/v1/apis/youtube/v3/rest",
    "youtube_analytics_v2": "https://youtubeanalytics.googleapis.com/$discovery/rest?version=v2",
    "youtube_reporting_v1": "https://youtubereporting.googleapis.com/$discovery/rest?version=v1",
}

OUTPUT_PATH = Path("src/youtube_mcp/data/youtube_api_operations.json")


def _sanitize(name: str) -> str:
    return re.sub(r"[^a-z0-9_]", "_", name.lower())


def _fetch_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _collect_methods(api_key: str, service_name: str, methods: dict, chain: list[str], out: list[dict]):
    for method_name, method in methods.items():
        resource_chain = list(chain)
        tool_name = _sanitize("_".join([api_key, *resource_chain, method_name]))
        params = method.get("parameters", {})
        required = sorted(k for k, v in params.items() if v.get("required"))
        scopes_raw = method.get("scopes", {})
        if isinstance(scopes_raw, dict):
            scopes = sorted(scopes_raw.keys())
        elif isinstance(scopes_raw, list):
            scopes = sorted(scopes_raw)
        else:
            scopes = []

        out.append(
            {
                "api": api_key,
                "service_name": service_name,
                "method_id": method.get("id", ""),
                "tool_name": tool_name,
                "resource_chain": resource_chain,
                "method_name": method_name,
                "http_method": method.get("httpMethod", "GET"),
                "path": method.get("path", ""),
                "description": method.get("description", ""),
                "supports_media_upload": bool(method.get("supportsMediaUpload")),
                "supports_media_download": bool(method.get("supportsMediaDownload")),
                "required_parameters": required,
                "all_parameters": sorted(params.keys()),
                "scopes": scopes,
            }
        )


def _walk_resources(api_key: str, service_name: str, resources: dict, chain: list[str], out: list[dict]):
    for resource_name, resource in resources.items():
        next_chain = [*chain, resource_name]
        _collect_methods(api_key, service_name, resource.get("methods", {}), next_chain, out)
        _walk_resources(api_key, service_name, resource.get("resources", {}), next_chain, out)


def collect_operation_specs() -> list[dict]:
    collected: list[dict] = []
    for api_key, url in DISCOVERY_URLS.items():
        doc = _fetch_json(url)
        service_name = doc.get("name", api_key)
        _collect_methods(api_key, service_name, doc.get("methods", {}), [], collected)
        _walk_resources(api_key, service_name, doc.get("resources", {}), [], collected)

    seen = set()
    deduped = []
    for item in sorted(collected, key=lambda x: x["tool_name"]):
        key = item["tool_name"]
        if key in seen:
            raise RuntimeError(f"Duplicate tool name generated: {key}")
        seen.add(key)
        deduped.append(item)
    return deduped


def main():
    specs = collect_operation_specs()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(specs, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(specs)} operations to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()

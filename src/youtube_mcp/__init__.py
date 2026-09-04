import json
import os
import sys
from datetime import datetime, timezone
from importlib import resources

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

try:
    from mcp.server.fastmcp import FastMCP
except Exception:
    FastMCP = None

MCP_TRANSPORT = os.environ.get("MCP_TRANSPORT", "stdio")
MCP_HOST = os.environ.get("MCP_HOST", "0.0.0.0")
_MCP_PORT_RAW = os.environ.get("MCP_PORT", "8000")

try:
    MCP_PORT = int(_MCP_PORT_RAW)
except ValueError:
    MCP_PORT = 8000
    _MCP_PORT_ERROR = f"Error: MCP_PORT must be an integer, got {_MCP_PORT_RAW!r}."
else:
    _MCP_PORT_ERROR = None

if FastMCP:
    server = FastMCP("youtube", host=MCP_HOST, port=MCP_PORT)
else:
    server = None

_SERVICE_BUILDERS = {
    "youtube_data_v3": ("youtube", "v3"),
    "youtube_analytics_v2": ("youtubeAnalytics", "v2"),
    "youtube_reporting_v1": ("youtubereporting", "v1"),
}
_SERVICE_CACHE = {}
GENERATED_TOOL_NAMES = []


def _tool(fn):
    if server is not None:
        return server.tool()(fn)
    return fn


def _run(fn, error_label="youtube call"):
    try:
        return fn()
    except Exception as e:  # noqa: BLE001
        return fail(f"{error_label} failed: {type(e).__name__}: {e}")


def ok(data):
    return {
        "ok": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }


def fail(message, code="runtime_error"):
    return {
        "isError": True,
        "ok": False,
        "error": {
            "code": code,
            "message": message,
        },
    }


def _parse_json_object(raw: str, label: str) -> dict:
    raw = raw.strip() if raw else "{}"
    if not raw:
        return {}
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError(f"{label} must be a JSON object")
    return parsed


def _load_operation_specs() -> list[dict]:
    text = resources.files("youtube_mcp").joinpath("data/youtube_api_operations.json").read_text(encoding="utf-8")
    return json.loads(text)


OPERATION_SPECS = _load_operation_specs()
OPERATION_BY_TOOL = {item["tool_name"]: item for item in OPERATION_SPECS}


def _api_counts() -> dict:
    counts = {}
    for spec in OPERATION_SPECS:
        api = spec["api"]
        counts[api] = counts.get(api, 0) + 1
    return counts


def _oauth_credentials() -> Credentials | None:
    client_id = os.environ.get("YOUTUBE_CLIENT_ID", "")
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET", "")
    refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN", "")
    if not (client_id and client_secret and refresh_token):
        return None
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
    )
    creds.refresh(Request())
    return creds


def _build_service(api: str):
    if api in _SERVICE_CACHE:
        return _SERVICE_CACHE[api]

    service_name, version = _SERVICE_BUILDERS[api]
    creds = _oauth_credentials()
    api_key = os.environ.get("YOUTUBE_API_KEY", "")
    if creds is not None:
        service = build(service_name, version, credentials=creds, cache_discovery=False)
    elif api_key:
        service = build(service_name, version, developerKey=api_key, cache_discovery=False)
    else:
        raise RuntimeError(
            "No credentials configured. Set YOUTUBE_API_KEY for public calls or "
            "YOUTUBE_CLIENT_ID/YOUTUBE_CLIENT_SECRET/YOUTUBE_REFRESH_TOKEN for OAuth."
        )
    _SERVICE_CACHE[api] = service
    return service


def _resolve_method(service, resource_chain: list[str], method_name: str):
    obj = service
    for resource_name in resource_chain:
        obj = getattr(obj, resource_name)()
    return getattr(obj, method_name)


def _execute_operation(spec: dict, params_json: str, body_json: str) -> dict:
    params = _parse_json_object(params_json, "params_json")
    body = _parse_json_object(body_json, "body_json") if body_json.strip().lower() not in {"", "null"} else None

    service = _build_service(spec["api"])
    method = _resolve_method(service, spec["resource_chain"], spec["method_name"])
    kwargs = dict(params)
    if body is not None:
        kwargs["body"] = body
    response = method(**kwargs).execute()
    return {
        "tool": spec["tool_name"],
        "api": spec["api"],
        "http_method": spec["http_method"],
        "path": spec["path"],
        "response": response,
    }


def _register_generated_tool(spec: dict):
    tool_name = spec["tool_name"]
    http_method = spec["http_method"]
    path = spec["path"]
    required_params = ", ".join(spec["required_parameters"]) if spec["required_parameters"] else "none"
    desc = f"{http_method} {path} ({spec['api']})"

    def _generated(params_json: str = "{}", body_json: str = "null") -> dict:
        def go():
            return ok(_execute_operation(spec, params_json=params_json, body_json=body_json))

        return _run(go, tool_name)

    _generated.__name__ = tool_name
    _generated.__doc__ = (
        f"Endpoint wrapper for {http_method} {path}. "
        f"Required query/path params: {required_params}. "
        "Pass endpoint params as JSON object via params_json and request body via body_json."
    )

    globals()[tool_name] = _generated
    GENERATED_TOOL_NAMES.append(tool_name)
    if server is not None:
        server.tool(name=tool_name, description=desc)(_generated)


for _spec in OPERATION_SPECS:
    _register_generated_tool(_spec)


@_tool
def health() -> dict:
    """Basic server runtime info."""

    def go():
        return ok(
            {
                "name": "youtube-mcp-full",
                "version": "0.1.0",
                "transport": MCP_TRANSPORT,
                "supported_transports": ["stdio", "sse", "streamable-http"],
                "generated_tools": len(GENERATED_TOOL_NAMES),
            }
        )

    return _run(go, "health")


@_tool
def auth_status() -> dict:
    """Report whether auth-related environment variables are configured."""

    def go():
        configured = {
            "youtube_api_key": bool(os.environ.get("YOUTUBE_API_KEY")),
            "youtube_client_id": bool(os.environ.get("YOUTUBE_CLIENT_ID")),
            "youtube_client_secret": bool(os.environ.get("YOUTUBE_CLIENT_SECRET")),
            "youtube_refresh_token": bool(os.environ.get("YOUTUBE_REFRESH_TOKEN")),
        }
        oauth_ready = (
            configured["youtube_client_id"]
            and configured["youtube_client_secret"]
            and configured["youtube_refresh_token"]
        )
        return ok({"configured": configured, "oauth_ready": oauth_ready})

    return _run(go, "auth_status")


@_tool
def list_supported_apis() -> dict:
    """Return declared API surfaces and scaffold status."""

    def go():
        counts = _api_counts()
        return ok(
            {
                "coverage_mode": "endpoint_to_tool_near_1_to_1",
                "total_generated_operations": len(OPERATION_SPECS),
                "apis": [
                    {"name": "youtube_data_v3", "status": "generated", "operations": counts.get("youtube_data_v3", 0)},
                    {
                        "name": "youtube_analytics_v2",
                        "status": "generated",
                        "operations": counts.get("youtube_analytics_v2", 0),
                    },
                    {
                        "name": "youtube_reporting_v1",
                        "status": "generated",
                        "operations": counts.get("youtube_reporting_v1", 0),
                    },
                ],
            }
        )

    return _run(go, "list_supported_apis")


def _validate_startup_config(transport: str):
    if _MCP_PORT_ERROR:
        return _MCP_PORT_ERROR
    allowed = {"stdio", "sse", "streamable-http"}
    if transport not in allowed:
        return (
            f"Error: invalid MCP_TRANSPORT '{MCP_TRANSPORT}'. "
            f"Expected one of: {', '.join(sorted(allowed))}."
        )
    return None


def main():
    if server is None:
        raise SystemExit("The 'mcp' python package is not installed.")
    transport = MCP_TRANSPORT.strip().lower()
    startup_error = _validate_startup_config(transport)
    if startup_error:
        sys.stderr.write(f"{startup_error}\n")
        raise SystemExit(1)
    server.run(transport=transport)


if __name__ == "__main__":
    main()

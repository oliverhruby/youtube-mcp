import json
import os
import sys
from datetime import datetime, timezone

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
        return ok(
            {
                "coverage_mode": "endpoint_to_tool_near_1_to_1",
                "apis": [
                    {"name": "youtube_data_v3", "status": "planned"},
                    {"name": "youtube_analytics", "status": "planned"},
                    {"name": "youtube_reporting", "status": "planned"},
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

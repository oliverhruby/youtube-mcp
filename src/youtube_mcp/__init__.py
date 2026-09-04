import json
import os
import secrets
import sys
import threading
import time
import webbrowser
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from importlib import resources
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

try:
    from mcp.server.fastmcp import FastMCP
    from mcp.server.auth.provider import AccessToken, TokenVerifier
    from mcp.server.auth.settings import AuthSettings
except Exception:
    FastMCP = None
    AccessToken = None
    TokenVerifier = None
    AuthSettings = None

MCP_TRANSPORT = os.environ.get("MCP_TRANSPORT", "stdio")
MCP_HOST = os.environ.get("MCP_HOST", "0.0.0.0")
MCP_API_KEY = os.environ.get("MCP_API_KEY", "")
_MCP_PORT_RAW = os.environ.get("MCP_PORT", "8000")

try:
    MCP_PORT = int(_MCP_PORT_RAW)
except ValueError:
    MCP_PORT = 8000
    _MCP_PORT_ERROR = f"Error: MCP_PORT must be an integer, got {_MCP_PORT_RAW!r}."
else:
    _MCP_PORT_ERROR = None

class _StaticApiKeyTokenVerifier:
    """Simple bearer token verifier backed by MCP_API_KEY."""

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def verify_token(self, token: str):
        if token != self.api_key:
            return None
        return AccessToken(token=token, client_id="mcp-api-key", scopes=["mcp"])  # type: ignore[misc]


if FastMCP:
    token_verifier = None
    auth_settings = None
    if MCP_API_KEY:
        token_verifier = _StaticApiKeyTokenVerifier(MCP_API_KEY)
        auth_settings = AuthSettings(
            issuer_url=f"http://{MCP_HOST}:{MCP_PORT}",
            resource_server_url=f"http://{MCP_HOST}:{MCP_PORT}",
            required_scopes=["mcp"],
        )
    server = FastMCP(
        "youtube",
        host=MCP_HOST,
        port=MCP_PORT,
        auth=auth_settings,
        token_verifier=token_verifier,
    )
else:
    server = None

_SERVICE_BUILDERS = {
    "youtube_data_v3": ("youtube", "v3"),
    "youtube_analytics_v2": ("youtubeAnalytics", "v2"),
    "youtube_reporting_v1": ("youtubereporting", "v1"),
}
_SERVICE_CACHE = {}
GENERATED_TOOL_NAMES = []

OAUTH_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
OAUTH_SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/yt-analytics-monetary.readonly",
]
OAUTH_REDIRECT_PORT = 8080
OAUTH_REDIRECT_HOST = "127.0.0.1"
OAUTH_REDIRECT_URI = f"http://{OAUTH_REDIRECT_HOST}:{OAUTH_REDIRECT_PORT}/callback"
OAUTH_CALLBACK_TIMEOUT_SECONDS = 300


@dataclass
class SessionState:
    access_token: str
    refresh_token: str
    client_id: str
    client_secret: str
    expires_at: str | None = None
    scopes: list[str] | None = None


@dataclass
class OAuthPendingState:
    state: str
    client_id: str
    client_secret: str
    redirect_uri: str
    scopes: list[str]
    created_at: str
    expires_at: str
    authorization_code: str | None = None
    error: str | None = None
    error_description: str | None = None
    listener_started: bool = False
    listener_address: str | None = None


_SESSION: SessionState | None = None
_PENDING_OAUTH: dict[str, OAuthPendingState] = {}
_PENDING_OAUTH_LOCK = threading.Lock()


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


def _expire_pending_oauth() -> None:
    now = datetime.now(UTC)
    stale: list[str] = []
    with _PENDING_OAUTH_LOCK:
        for state, pending in _PENDING_OAUTH.items():
            if datetime.fromisoformat(pending.expires_at) < now:
                stale.append(state)
        for s in stale:
            _PENDING_OAUTH.pop(s, None)


def _start_callback_listener(state_value: str, redirect_uri: str) -> dict:
    parsed = urlparse(redirect_uri)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        return {"started": False, "reason": "callback listener supports only localhost http redirect URIs"}

    host = parsed.hostname
    port = parsed.port
    path = parsed.path or "/"
    if port is None:
        return {"started": False, "reason": "redirect_uri must include explicit port"}

    class OAuthCallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            request = urlparse(self.path)
            if request.path != path:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"Not found")
                return

            query = parse_qs(request.query)
            callback_state = (query.get("state") or [""])[0]
            code = (query.get("code") or [""])[0]
            error = (query.get("error") or [""])[0]
            error_description = (query.get("error_description") or [""])[0]

            with _PENDING_OAUTH_LOCK:
                pending = _PENDING_OAUTH.get(callback_state)
                if pending:
                    pending.authorization_code = code or None
                    pending.error = error or None
                    pending.error_description = error_description or None

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            if error:
                self.wfile.write(b"<html><body><h2>YouTube authorization failed.</h2><p>You can close this window.</p></body></html>")
            else:
                self.wfile.write(b"<html><body><h2>YouTube authorization received.</h2><p>You can return to your MCP client.</p></body></html>")

            threading.Thread(target=self.server.shutdown, daemon=True).start()

        def log_message(self, format, *args):
            return

    def _run_server():
        try:
            server = HTTPServer((host, port), OAuthCallbackHandler)
            server.timeout = float(OAUTH_CALLBACK_TIMEOUT_SECONDS)
            server.handle_request()
            server.server_close()
        except OSError:
            with _PENDING_OAUTH_LOCK:
                pending = _PENDING_OAUTH.get(state_value)
                if pending:
                    pending.error = "callback_listener_error"
                    pending.error_description = "Could not bind local callback listener; port may be in use."

    threading.Thread(target=_run_server, daemon=True).start()
    return {"started": True, "listener_address": f"{host}:{port}{path}"}


def _request_form(url: str, data: dict[str, str]) -> dict:
    with httpx.Client(timeout=30.0) as client:
        response = client.post(url=url, data=data)
    out: dict = {
        "ok": response.is_success,
        "status_code": response.status_code,
        "url": url,
    }
    try:
        out["data"] = response.json()
    except json.JSONDecodeError:
        out["text"] = response.text
    return out


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
    if _SESSION is not None:
        creds = Credentials(
            token=_SESSION.access_token,
            refresh_token=_SESSION.refresh_token,
            token_uri=OAUTH_TOKEN_URL,
            client_id=_SESSION.client_id,
            client_secret=_SESSION.client_secret,
        )
        if creds.expired or not creds.token:
            creds.refresh(Request())
        return creds

    client_id = os.environ.get("YOUTUBE_CLIENT_ID", "")
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET", "")
    refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN", "")
    if not (client_id and client_secret and refresh_token):
        return None
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri=OAUTH_TOKEN_URL,
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
                "convenience_tools": len(CONVENIENCE_TOOL_NAMES),
                "total_tools": len(GENERATED_TOOL_NAMES) + len(CONVENIENCE_TOOL_NAMES),
            }
        )

    return _run(go, "health")


@_tool
def auth_status() -> dict:
    """Report current authentication state."""

    def go():
        env_api_key = bool(os.environ.get("YOUTUBE_API_KEY"))
        env_client_id = bool(os.environ.get("YOUTUBE_CLIENT_ID"))
        env_client_secret = bool(os.environ.get("YOUTUBE_CLIENT_SECRET"))
        env_refresh_token = bool(os.environ.get("YOUTUBE_REFRESH_TOKEN"))

        session_active = _SESSION is not None
        session_safe = None
        if session_active:
            session_safe = asdict(_SESSION)
            session_safe["access_token"] = "***redacted***"
            session_safe["refresh_token"] = "***redacted***"

        _expire_pending_oauth()
        return ok({
            "session_active": session_active,
            "session": session_safe,
            "env_configured": {
                "api_key": env_api_key,
                "client_id": env_client_id,
                "client_secret": env_client_secret,
                "refresh_token": env_refresh_token,
            },
            "pending_oauth_states": sorted(_PENDING_OAUTH.keys()),
        })

    return _run(go, "auth_status")


@_tool
def auth_start(
    client_id: str = "",
    client_secret: str = "",
    scopes_csv: str = "",
    open_browser: bool = False,
    auto_listen_callback: bool = True,
) -> dict:
    """Start OAuth authorization by generating Google consent URL and optional localhost callback listener.

    Provide client_id and client_secret (or set YOUTUBE_CLIENT_ID/YOUTUBE_CLIENT_SECRET env vars).
    Default scopes include YouTube read/write and analytics access.
    """
    final_client_id = client_id.strip() or os.environ.get("YOUTUBE_CLIENT_ID", "").strip()
    final_client_secret = client_secret.strip() or os.environ.get("YOUTUBE_CLIENT_SECRET", "").strip()
    if not final_client_id:
        raise RuntimeError("client_id is required (argument or YOUTUBE_CLIENT_ID env var)")
    if not final_client_secret:
        raise RuntimeError("client_secret is required (argument or YOUTUBE_CLIENT_SECRET env var)")

    _expire_pending_oauth()
    state_value = secrets.token_urlsafe(24)

    if scopes_csv.strip():
        scope_list = [s.strip() for s in scopes_csv.split(",") if s.strip()]
    else:
        scope_list = list(OAUTH_SCOPES)

    redirect_uri = OAUTH_REDIRECT_URI
    now = datetime.now(UTC)
    expires = now.timestamp() + OAUTH_CALLBACK_TIMEOUT_SECONDS

    pending = OAuthPendingState(
        state=state_value,
        client_id=final_client_id,
        client_secret=final_client_secret,
        redirect_uri=redirect_uri,
        scopes=scope_list,
        created_at=now.isoformat(),
        expires_at=datetime.fromtimestamp(expires, UTC).isoformat(),
    )
    with _PENDING_OAUTH_LOCK:
        _PENDING_OAUTH[state_value] = pending

    params = {
        "response_type": "code",
        "client_id": final_client_id,
        "redirect_uri": redirect_uri,
        "state": state_value,
        "scope": " ".join(scope_list),
        "access_type": "offline",
        "prompt": "consent",
    }
    auth_url = f"{OAUTH_AUTH_URL}?{urlencode(params)}"

    listener = {"started": False}
    if auto_listen_callback:
        listener = _start_callback_listener(state_value=state_value, redirect_uri=redirect_uri)
        with _PENDING_OAUTH_LOCK:
            current = _PENDING_OAUTH.get(state_value)
            if current and listener.get("started"):
                current.listener_started = True
                current.listener_address = listener.get("listener_address")

    browser_opened = False
    if open_browser:
        browser_opened = webbrowser.open(auth_url)

    return {
        "ok": True,
        "state": state_value,
        "authorization_url": auth_url,
        "browser_opened": browser_opened,
        "listener": listener,
        "expires_at": pending.expires_at,
        "next": "Complete consent in browser, then call auth_poll(state) and auth_finish(state).",
    }


@_tool
def auth_poll(state: str) -> dict:
    """Poll pending OAuth state for callback status and auth code availability."""
    _expire_pending_oauth()
    with _PENDING_OAUTH_LOCK:
        pending = _PENDING_OAUTH.get(state)
    if pending is None:
        return {"ok": False, "state": state, "found": False}
    return {
        "ok": True,
        "found": True,
        "state": state,
        "has_code": pending.authorization_code is not None,
        "error": pending.error,
        "error_description": pending.error_description,
        "listener_started": pending.listener_started,
        "listener_address": pending.listener_address,
        "expires_at": pending.expires_at,
    }


@_tool
def auth_finish(state: str, code: str = "") -> dict:
    """Exchange authorization code for tokens and activate session."""
    _expire_pending_oauth()
    with _PENDING_OAUTH_LOCK:
        pending = _PENDING_OAUTH.get(state)
    if pending is None:
        raise RuntimeError("OAuth state not found or expired. Start again with auth_start.")
    if pending.error:
        raise RuntimeError(f"OAuth callback returned error: {pending.error} ({pending.error_description or 'no details'})")

    final_code = code.strip() or (pending.authorization_code or "")
    if not final_code:
        raise RuntimeError("Authorization code not available yet. Call auth_poll or provide code directly.")

    token_response = _request_form(
        OAUTH_TOKEN_URL,
        {
            "grant_type": "authorization_code",
            "code": final_code,
            "redirect_uri": pending.redirect_uri,
            "client_id": pending.client_id,
            "client_secret": pending.client_secret,
        },
    )
    if not token_response["ok"]:
        return {"ok": False, "state": state, "token_exchange": token_response}

    data = token_response.get("data", {})
    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")
    if not access_token:
        raise RuntimeError("Token exchange succeeded without access_token.")
    if not refresh_token:
        raise RuntimeError("Token exchange succeeded without refresh_token. Ensure access_type=offline and prompt=consent.")

    expires_in = data.get("expires_in")
    expires_at = None
    if isinstance(expires_in, int):
        expires_at = datetime.fromtimestamp(time.time() + expires_in, UTC).isoformat()

    global _SESSION
    _SESSION = SessionState(
        access_token=access_token,
        refresh_token=refresh_token,
        client_id=pending.client_id,
        client_secret=pending.client_secret,
        expires_at=expires_at,
        scopes=pending.scopes,
    )

    with _PENDING_OAUTH_LOCK:
        _PENDING_OAUTH.pop(state, None)

    _SERVICE_CACHE.clear()

    return {
        "ok": True,
        "authenticated": True,
        "expires_at": expires_at,
        "scopes": pending.scopes,
    }


@_tool
def auth_refresh() -> dict:
    """Refresh access token using the session's refresh token."""
    if _SESSION is None:
        raise RuntimeError("No active session. Authenticate first with auth_start/auth_finish.")

    creds = Credentials(
        token=_SESSION.access_token,
        refresh_token=_SESSION.refresh_token,
        token_uri=OAUTH_TOKEN_URL,
        client_id=_SESSION.client_id,
        client_secret=_SESSION.client_secret,
    )
    creds.refresh(Request())

    _SESSION.access_token = creds.token
    if creds.expiry:
        _SESSION.expires_at = creds.expiry.isoformat()

    return {
        "ok": True,
        "authenticated": True,
        "expires_at": _SESSION.expires_at,
    }


@_tool
def auth_clear() -> dict:
    """Clear active session and pending OAuth states from memory."""
    global _SESSION
    _SESSION = None
    with _PENDING_OAUTH_LOCK:
        _PENDING_OAUTH.clear()
    _SERVICE_CACHE.clear()
    return {"ok": True, "authenticated": False}


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


CONVENIENCE_TOOL_NAMES = []


def _convenience(fn):
    if server is not None:
        server.tool()(fn)
    CONVENIENCE_TOOL_NAMES.append(fn.__name__)
    return fn


def _spec_by_tool_name(name: str) -> dict:
    spec = OPERATION_BY_TOOL.get(name)
    if spec is None:
        raise RuntimeError(f"Generated tool spec not found: {name}")
    return spec


def _execute_generated(tool_name: str, params: dict, body: dict | None = None) -> dict:
    spec = _spec_by_tool_name(tool_name)
    params_json = json.dumps(params)
    body_json = json.dumps(body) if body is not None else "null"
    return ok(_execute_operation(spec, params_json=params_json, body_json=body_json))


@_convenience
def search_videos(
    query: str = None,
    channel_id: str = None,
    max_results: int = 5,
    order: str = "relevance",
    region_code: str = None,
    video_duration: str = None,
    published_after: str = None,
    published_before: str = None,
    safe_search: str = "moderate",
    page_token: str = None,
    part: str = "snippet",
) -> dict:
    """Search YouTube videos. Returns matching videos with snippet data.

    Use query for keyword search. Filter by channel_id, video_duration
    (short/medium/long), date range, and region. Order by relevance,
    date, viewCount, or rating.
    """
    params: dict = {"part": part}
    if query:
        params["q"] = query
    if channel_id:
        params["channelId"] = channel_id
    params["maxResults"] = max_results
    params["order"] = order
    if region_code:
        params["regionCode"] = region_code
    if video_duration:
        params["videoDuration"] = video_duration
    if published_after:
        params["publishedAfter"] = published_after
    if published_before:
        params["publishedBefore"] = published_before
    params["safeSearch"] = safe_search
    if page_token:
        params["pageToken"] = page_token
    return _run(lambda: _execute_generated("youtube_data_v3_search_list", params), "search_videos")


@_convenience
def get_video(
    video_id: str,
    part: str = "snippet,statistics,contentDetails",
) -> dict:
    """Get details for a single video by ID.

    Returns snippet (title, description, tags), statistics (views, likes,
    comment count), and contentDetails (duration, definition, license).
    """
    return _run(
        lambda: _execute_generated("youtube_data_v3_videos_list", {"part": part, "id": video_id}),
        "get_video",
    )


@_convenience
def list_videos(
    chart: str = "mostPopular",
    region_code: str = "US",
    video_category_id: str = None,
    max_results: int = 25,
    part: str = "snippet,statistics",
    page_token: str = None,
) -> dict:
    """List videos by chart (mostPopular, recent) or category.

    Defaults to most popular videos in the US. Set chart to 'recent' for
    latest uploads from authenticated user's subscriptions.
    """
    params: dict = {"part": part, "chart": chart, "regionCode": region_code, "maxResults": max_results}
    if video_category_id:
        params["videoCategoryId"] = video_category_id
    if page_token:
        params["pageToken"] = page_token
    return _run(lambda: _execute_generated("youtube_data_v3_videos_list", params), "list_videos")


@_convenience
def get_channel(
    channel_id: str = None,
    handle: str = None,
    username: str = None,
    part: str = "snippet,statistics,contentDetails",
) -> dict:
    """Get channel details by ID, handle (@name), or username.

    Exactly one of channel_id, handle, or username must be provided.
    Returns snippet (title, description, thumbnails), statistics
    (subscriberCount, videoCount), and contentDetails (relatedPlaylists).
    """
    params: dict = {"part": part}
    if channel_id:
        params["id"] = channel_id
    elif handle:
        params["forHandle"] = handle
    elif username:
        params["forUsername"] = username
    return _run(lambda: _execute_generated("youtube_data_v3_channels_list", params), "get_channel")


@_convenience
def get_my_channel(part: str = "snippet,statistics,contentDetails") -> dict:
    """Get the authenticated user's own channel details.

    Requires OAuth. Returns snippet, statistics, and contentDetails
    including relatedPlaylists (uploads, likes, favorites).
    """
    return _run(
        lambda: _execute_generated("youtube_data_v3_channels_list", {"part": part, "mine": "true"}),
        "get_my_channel",
    )


@_convenience
def list_playlists(
    channel_id: str = None,
    mine: bool = False,
    max_results: int = 25,
    part: str = "snippet,contentDetails",
    page_token: str = None,
) -> dict:
    """List playlists for a channel or the authenticated user.

    Set mine=true with OAuth to get your own playlists, or provide
    channel_id for any public channel's playlists.
    """
    params: dict = {"part": part, "maxResults": max_results}
    if mine:
        params["mine"] = "true"
    elif channel_id:
        params["channelId"] = channel_id
    if page_token:
        params["pageToken"] = page_token
    return _run(lambda: _execute_generated("youtube_data_v3_playlists_list", params), "list_playlists")


@_convenience
def list_playlist_items(
    playlist_id: str,
    max_results: int = 25,
    part: str = "snippet,contentDetails",
    page_token: str = None,
) -> dict:
    """List items (videos) in a playlist.

    Provide the playlist_id (e.g. PL...). Returns each item's snippet
    and contentDetails (videoId, videoPublishedAt).
    """
    params: dict = {"part": part, "playlistId": playlist_id, "maxResults": max_results}
    if page_token:
        params["pageToken"] = page_token
    return _run(lambda: _execute_generated("youtube_data_v3_playlistitems_list", params), "list_playlist_items")


@_convenience
def list_comment_threads(
    video_id: str = None,
    channel_id: str = None,
    order: str = "time",
    max_results: int = 20,
    search_terms: str = None,
    part: str = "snippet,replies",
    page_token: str = None,
) -> dict:
    """List top-level comment threads for a video or channel.

    Filter by video_id or channel_id. Optionally search by keywords.
    Order by time or relevance. Returns comment text, author, and
    engagement counts.
    """
    params: dict = {"part": part, "order": order, "maxResults": max_results}
    if video_id:
        params["videoId"] = video_id
    if channel_id:
        params["channelId"] = channel_id
    if search_terms:
        params["searchTerms"] = search_terms
    if page_token:
        params["pageToken"] = page_token
    return _run(lambda: _execute_generated("youtube_data_v3_commentthreads_list", params), "list_comment_threads")


@_convenience
def list_comments(
    parent_id: str,
    max_results: int = 20,
    order: str = "time",
    part: str = "snippet",
    page_token: str = None,
) -> dict:
    """List replies to a parent comment or comment thread.

    Provide parent_id (comment thread ID or parent comment ID).
    Returns reply comments with author and text.
    """
    params: dict = {"part": part, "parentId": parent_id, "maxResults": max_results, "order": order}
    if page_token:
        params["pageToken"] = page_token
    return _run(lambda: _execute_generated("youtube_data_v3_comments_list", params), "list_comments")


@_convenience
def analytics_query(
    ids: str = "channel==MINE",
    metrics: str = "views,likes,subscribersGained",
    dimensions: str = None,
    start_date: str = None,
    end_date: str = None,
    filters: str = None,
    sort: str = None,
    max_results: int = None,
    currency: str = None,
) -> dict:
    """Query YouTube Analytics for channel or video performance.

    Default ids='channel==MINE' uses the authenticated channel.
    Metrics examples: views, likes, comments, estimatedMinutesWatched,
    subscribersGained, subscribersLost, revenue.
    Dimensions examples: day, month, video, country, trafficSource.
    Filters examples: video==VIDEO_ID, country==US.
    Dates are YYYY-MM-DD format.
    """
    params: dict = {"ids": ids, "metrics": metrics}
    if dimensions:
        params["dimensions"] = dimensions
    if start_date:
        params["startDate"] = start_date
    if end_date:
        params["endDate"] = end_date
    if filters:
        params["filters"] = filters
    if sort:
        params["sort"] = sort
    if max_results:
        params["maxResults"] = max_results
    if currency:
        params["currency"] = currency
    return _run(lambda: _execute_generated("youtube_analytics_v2_reports_query", params), "analytics_query")


@_convenience
def list_reporting_jobs(
    include_system_managed: bool = False,
    page_size: int = None,
    page_token: str = None,
) -> dict:
    """List YouTube Reporting API jobs.

    Jobs define which reports YouTube generates daily. Use this to
    discover available report types and their IDs before fetching
    report data.
    """
    params: dict = {}
    if include_system_managed:
        params["includeSystemManaged"] = "true"
    if page_size:
        params["pageSize"] = page_size
    if page_token:
        params["pageToken"] = page_token
    return _run(lambda: _execute_generated("youtube_reporting_v1_jobs_list", params), "list_reporting_jobs")


@_convenience
def list_reporting_job_reports(
    job_id: str,
    page_size: int = None,
    page_token: str = None,
    start_time_at_or_after: str = None,
    start_time_before: str = None,
) -> dict:
    """List reports generated by a specific reporting job.

    Provide job_id from list_reporting_jobs. Each report contains
    a reportId and download URL. Use list_report_types to see what
    data each report contains.
    """
    params: dict = {"jobId": job_id}
    if page_size:
        params["pageSize"] = page_size
    if page_token:
        params["pageToken"] = page_token
    if start_time_at_or_after:
        params["startTimeAtOrAfter"] = start_time_at_or_after
    if start_time_before:
        params["startTimeBefore"] = start_time_before
    return _run(
        lambda: _execute_generated("youtube_reporting_v1_jobs_reports_list", params),
        "list_reporting_job_reports",
    )


@_convenience
def list_report_types(
    include_system_managed: bool = False,
    page_size: int = None,
) -> dict:
    """List available YouTube Reporting report types.

    Each report type has an id and name describing what data it
    contains (e.g. channel_basic_a2 for basic channel analytics).
    """
    params: dict = {}
    if include_system_managed:
        params["includeSystemManaged"] = "true"
    if page_size:
        params["pageSize"] = page_size
    return _run(lambda: _execute_generated("youtube_reporting_v1_reporttypes_list", params), "list_report_types")


@_convenience
def list_subscriptions(
    mine: bool = False,
    channel_id: str = None,
    max_results: int = 25,
    order: str = "relevance",
    part: str = "snippet",
    page_token: str = None,
) -> dict:
    """List subscriptions. Use mine=true for authenticated user's subs.

    Filter by channel_id to check if you're subscribed to a channel.
    Returns channel title, description, and thumbnails of subscribed
    channels.
    """
    params: dict = {"part": part, "maxResults": max_results, "order": order}
    if mine:
        params["mine"] = "true"
    if channel_id:
        params["channelId"] = channel_id
    if page_token:
        params["pageToken"] = page_token
    return _run(lambda: _execute_generated("youtube_data_v3_subscriptions_list", params), "list_subscriptions")


@_convenience
def set_thumbnail(video_id: str, on_behalf_of_content_owner: str = None) -> dict:
    """Upload and set a custom thumbnail for a video.

    Requires OAuth with youtube.upload scope. The thumbnail image
    should be provided via the raw body of the request. Note: the
    underlying endpoint uses media upload; this tool sends the request
    but the actual image upload requires multipart handling.
    """
    params: dict = {"videoId": video_id}
    if on_behalf_of_content_owner:
        params["onBehalfOfContentOwner"] = on_behalf_of_content_owner
    return _run(lambda: _execute_generated("youtube_data_v3_thumbnails_set", params), "set_thumbnail")


@_convenience
def list_video_categories(
    region_code: str = "US",
    hl: str = "en_US",
    part: str = "snippet",
) -> dict:
    """List YouTube video categories for a region.

    Returns category IDs and titles (e.g. 22 = People & Blogs,
    24 = Entertainment, 27 = Education). Useful for filtering
    or classifying videos.
    """
    params: dict = {"part": part, "regionCode": region_code, "hl": hl}
    return _run(lambda: _execute_generated("youtube_data_v3_videocategories_list", params), "list_video_categories")


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

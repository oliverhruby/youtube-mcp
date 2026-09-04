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
                "convenience_tools": len(CONVENIENCE_TOOL_NAMES),
                "total_tools": len(GENERATED_TOOL_NAMES) + len(CONVENIENCE_TOOL_NAMES),
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

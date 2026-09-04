import os

import pytest

import youtube_mcp

pytestmark = pytest.mark.live

HAS_API_KEY = bool(os.environ.get("YOUTUBE_API_KEY"))
HAS_OAUTH = all(
    os.environ.get(var)
    for var in ["YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"]
)
skip_no_key = pytest.mark.skipif(not HAS_API_KEY, reason="YOUTUBE_API_KEY not set")
skip_no_oauth = pytest.mark.skipif(not HAS_OAUTH, reason="OAuth credentials not set")


@skip_no_key
def test_data_api_search_videos():
    result = youtube_mcp.search_videos(query="python", max_results=3)
    assert result["ok"] is True
    items = result["data"]["response"].get("items", [])
    assert len(items) >= 1


@skip_no_key
def test_data_api_get_video():
    result = youtube_mcp.search_videos(query="python tutorial", max_results=1)
    assert result["ok"] is True
    items = result["data"]["response"].get("items", [])
    if not items:
        pytest.skip("No search results to use as video ID")
    video_id = items[0]["id"]["videoId"]

    detail = youtube_mcp.get_video(video_id)
    assert detail["ok"] is True
    video_items = detail["data"]["response"].get("items", [])
    assert len(video_items) == 1
    assert video_items[0]["id"] == video_id


@skip_no_key
def test_data_api_list_videos_most_popular():
    result = youtube_mcp.list_videos(chart="mostPopular", region_code="US", max_results=5)
    assert result["ok"] is True
    items = result["data"]["response"].get("items", [])
    assert len(items) >= 1


@skip_no_key
def test_data_api_get_channel():
    result = youtube_mcp.get_channel(handle="@Google")
    assert result["ok"] is True
    items = result["data"]["response"].get("items", [])
    assert len(items) == 1
    assert items[0]["id"].startswith("UC")


@skip_no_key
def test_data_api_list_playlists():
    result = youtube_mcp.get_channel(handle="@Google")
    assert result["ok"] is True
    items = result["data"]["response"].get("items", [])
    if not items:
        pytest.skip("Could not resolve channel ID")
    channel_id = items[0]["id"]

    playlists = youtube_mcp.list_playlists(channel_id=channel_id, max_results=5)
    assert playlists["ok"] is True
    assert isinstance(playlists["data"]["response"].get("items", []), list)


@skip_no_key
def test_data_api_list_comment_threads():
    result = youtube_mcp.search_videos(query="python", max_results=1)
    assert result["ok"] is True
    items = result["data"]["response"].get("items", [])
    if not items:
        pytest.skip("No search results")
    video_id = items[0]["id"]["videoId"]

    comments = youtube_mcp.list_comment_threads(video_id=video_id, max_results=5)
    assert comments["ok"] is True
    assert isinstance(comments["data"]["response"].get("items", []), list)


@skip_no_key
def test_data_api_list_video_categories():
    result = youtube_mcp.list_video_categories(region_code="US")
    assert result["ok"] is True
    items = result["data"]["response"].get("items", [])
    assert len(items) >= 10


@skip_no_key
def test_data_api_list_subscriptions():
    result = youtube_mcp.youtube_data_v3_subscriptions_list(
        params_json='{"part":"snippet","mine":"true","maxResults":1}'
    )
    if result.get("isError"):
        pytest.skip("Subscriptions list requires OAuth or returns error without it")
    assert result["ok"] is True


@skip_no_key
def test_generated_tool_search_list():
    result = youtube_mcp.youtube_data_v3_search_list(
        params_json='{"part":"snippet","q":"mcp server","maxResults":2}'
    )
    assert result["ok"] is True
    items = result["data"]["response"].get("items", [])
    assert len(items) >= 1


@skip_no_key
def test_generated_tool_channels_list():
    result = youtube_mcp.youtube_data_v3_channels_list(
        params_json='{"part":"snippet","forHandle":"@Google","maxResults":1}'
    )
    assert result["ok"] is True
    items = result["data"]["response"].get("items", [])
    assert len(items) == 1


@skip_no_oauth
def test_analytics_query():
    result = youtube_mcp.analytics_query(
        metrics="views",
        start_date="2025-01-01",
        end_date="2025-01-31",
    )
    assert result["ok"] is True
    assert "rows" in result["data"]["response"] or "rows" in str(result["data"])


@skip_no_oauth
def test_reporting_list_jobs():
    result = youtube_mcp.list_reporting_jobs()
    assert result["ok"] is True


@skip_no_oauth
def test_reporting_list_report_types():
    result = youtube_mcp.list_report_types()
    assert result["ok"] is True
    report_types = result["data"]["response"].get("reportTypes", [])
    assert len(report_types) >= 1

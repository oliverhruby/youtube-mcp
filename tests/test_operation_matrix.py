import youtube_mcp


def test_generated_operation_count_is_nontrivial():
    assert len(youtube_mcp.OPERATION_SPECS) >= 90
    assert len(youtube_mcp.GENERATED_TOOL_NAMES) == len(youtube_mcp.OPERATION_SPECS)


def test_key_tools_exist():
    assert "youtube_data_v3_videos_list" in youtube_mcp.GENERATED_TOOL_NAMES
    assert "youtube_analytics_v2_reports_query" in youtube_mcp.GENERATED_TOOL_NAMES
    assert "youtube_reporting_v1_reporttypes_list" in youtube_mcp.GENERATED_TOOL_NAMES


def test_convenience_tools_registered():
    assert len(youtube_mcp.CONVENIENCE_TOOL_NAMES) >= 15
    expected = [
        "search_videos",
        "get_video",
        "list_videos",
        "get_channel",
        "get_my_channel",
        "list_playlists",
        "list_playlist_items",
        "list_comment_threads",
        "list_comments",
        "analytics_query",
        "list_reporting_jobs",
        "list_reporting_job_reports",
        "list_report_types",
        "list_subscriptions",
        "set_thumbnail",
        "list_video_categories",
    ]
    for name in expected:
        assert name in youtube_mcp.CONVENIENCE_TOOL_NAMES, f"Missing convenience tool: {name}"


def test_convenience_tools_callable():
    assert callable(getattr(youtube_mcp, "search_videos"))
    assert callable(getattr(youtube_mcp, "get_video"))
    assert callable(getattr(youtube_mcp, "analytics_query"))


def test_health_reports_totals():
    result = youtube_mcp.health()
    assert result["ok"] is True
    data = result["data"]
    assert data["generated_tools"] == len(youtube_mcp.GENERATED_TOOL_NAMES)
    assert data["convenience_tools"] == len(youtube_mcp.CONVENIENCE_TOOL_NAMES)
    assert data["total_tools"] == data["generated_tools"] + data["convenience_tools"]


def test_list_supported_apis_reports_generated_state():
    result = youtube_mcp.list_supported_apis()
    assert result["ok"] is True
    data = result["data"]
    assert data["total_generated_operations"] == len(youtube_mcp.OPERATION_SPECS)

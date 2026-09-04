import youtube_mcp


def test_generated_operation_count_is_nontrivial():
    assert len(youtube_mcp.OPERATION_SPECS) >= 90
    assert len(youtube_mcp.GENERATED_TOOL_NAMES) == len(youtube_mcp.OPERATION_SPECS)


def test_key_tools_exist():
    assert "youtube_data_v3_videos_list" in youtube_mcp.GENERATED_TOOL_NAMES
    assert "youtube_analytics_v2_reports_query" in youtube_mcp.GENERATED_TOOL_NAMES
    assert "youtube_reporting_v1_reporttypes_list" in youtube_mcp.GENERATED_TOOL_NAMES


def test_list_supported_apis_reports_generated_state():
    result = youtube_mcp.list_supported_apis()
    assert result["ok"] is True
    data = result["data"]
    assert data["total_generated_operations"] == len(youtube_mcp.OPERATION_SPECS)

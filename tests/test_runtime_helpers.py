import pytest

import youtube_mcp


def test_parse_json_object_valid():
    parsed = youtube_mcp._parse_json_object('{"part":"snippet"}', "params_json")
    assert parsed["part"] == "snippet"


def test_parse_json_object_rejects_non_object():
    with pytest.raises(ValueError):
        youtube_mcp._parse_json_object("[]", "params_json")


def test_generated_tool_uses_executor(monkeypatch):
    tool_name = "youtube_data_v3_videos_list"
    tool = getattr(youtube_mcp, tool_name)

    def fake_execute(spec, params_json, body_json):
        return {
            "tool": spec["tool_name"],
            "params_json": params_json,
            "body_json": body_json,
        }

    monkeypatch.setattr(youtube_mcp, "_execute_operation", fake_execute)

    result = tool(params_json='{"part":"snippet"}', body_json="null")
    assert result["ok"] is True
    assert result["data"]["tool"] == tool_name


def test_convenience_search_videos_builds_correct_params(monkeypatch):
    captured = {}

    def fake_execute(spec, params_json, body_json):
        captured["spec"] = spec
        captured["params_json"] = params_json
        captured["body_json"] = body_json
        return {"kind": "youtube#searchListResponse", "items": []}

    monkeypatch.setattr(youtube_mcp, "_execute_operation", fake_execute)

    result = youtube_mcp.search_videos(
        query="python tutorial",
        max_results=10,
        order="viewCount",
        region_code="CZ",
    )
    assert result["ok"] is True
    params = youtube_mcp._parse_json_object(captured["params_json"], "test")
    assert params["q"] == "python tutorial"
    assert params["maxResults"] == 10
    assert params["order"] == "viewCount"
    assert params["regionCode"] == "CZ"
    assert params["part"] == "snippet"


def test_convenience_get_video_builds_correct_params(monkeypatch):
    captured = {}

    def fake_execute(spec, params_json, body_json):
        captured["params_json"] = params_json
        return {"kind": "youtube#videoListResponse", "items": []}

    monkeypatch.setattr(youtube_mcp, "_execute_operation", fake_execute)

    result = youtube_mcp.get_video("dQw4w9WgXcQ")
    assert result["ok"] is True
    params = youtube_mcp._parse_json_object(captured["params_json"], "test")
    assert params["id"] == "dQw4w9WgXcQ"
    assert "snippet" in params["part"]


def test_convenience_analytics_query_builds_correct_params(monkeypatch):
    captured = {}

    def fake_execute(spec, params_json, body_json):
        captured["params_json"] = params_json
        return {"kind": "youtubeAnalytics#resultTable", "columnHeaders": [], "rows": []}

    monkeypatch.setattr(youtube_mcp, "_execute_operation", fake_execute)

    result = youtube_mcp.analytics_query(
        metrics="views,likes",
        dimensions="day",
        start_date="2025-01-01",
        end_date="2025-01-31",
    )
    assert result["ok"] is True
    params = youtube_mcp._parse_json_object(captured["params_json"], "test")
    assert params["metrics"] == "views,likes"
    assert params["dimensions"] == "day"
    assert params["startDate"] == "2025-01-01"
    assert params["endDate"] == "2025-01-31"

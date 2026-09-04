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

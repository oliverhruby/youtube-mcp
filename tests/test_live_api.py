import os

import pytest

import youtube_mcp


@pytest.mark.live
def test_live_data_api_videos_list():
    if not os.environ.get("YOUTUBE_API_KEY"):
        pytest.skip("YOUTUBE_API_KEY is not set")

    result = youtube_mcp.youtube_data_v3_videos_list(
        params_json='{"part":"snippet","chart":"mostPopular","maxResults":1,"regionCode":"US"}'
    )
    assert result["ok"] is True
    response = result["data"]["response"]
    assert isinstance(response.get("items", []), list)

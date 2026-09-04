# youtube-mcp-full

[![PyPI version](https://img.shields.io/pypi/v/youtube-mcp-full.svg)](https://pypi.org/project/youtube-mcp-full/)
[![Downloads](https://img.shields.io/pypi/dm/youtube-mcp-full.svg)](https://pypi.org/project/youtube-mcp-full/)
[![Quality gates](https://img.shields.io/github/actions/workflow/status/oliverhruby/youtube-mcp/quality-gates.yml.svg?label=quality%20gates)](https://github.com/oliverhruby/youtube-mcp/actions/workflows/quality-gates.yml)
[![Security](https://img.shields.io/github/actions/workflow/status/oliverhruby/youtube-mcp/security.yml.svg?label=security)](https://github.com/oliverhruby/youtube-mcp/actions/workflows/security.yml)
[![Container security](https://img.shields.io/github/actions/workflow/status/oliverhruby/youtube-mcp/container-security.yml.svg?label=container%20security)](https://github.com/oliverhruby/youtube-mcp/actions/workflows/container-security.yml)
[![Coverage drift](https://img.shields.io/github/actions/workflow/status/oliverhruby/youtube-mcp/coverage-drift.yml.svg?label=coverage%20drift)](https://github.com/oliverhruby/youtube-mcp/actions/workflows/coverage-drift.yml)

A Model Context Protocol (MCP) server that provides near 1:1 coverage of the
YouTube Data API v3, YouTube Analytics API, and YouTube Reporting API as MCP
tools for AI agents such as opencode, Claude, Cursor and any other MCP client.

Search videos, read channel stats, query analytics, manage playlists, read
comments, pull reporting data — all directly from your agent with a single
server that covers all three YouTube API surfaces.

---

## Table of Contents

- [Why another YouTube MCP server?](#why-another-youtube-mcp-server)
- [What it provides](#what-it-provides)
- [Getting started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [1. Install](#1-install)
  - [2. Configure credentials](#2-configure-credentials)
  - [3. Register with your MCP client](#3-register-with-your-mcp-client)
- [Prompt examples](#prompt-examples)
- [Tool reference](#tool-reference)
- [Data & safety notes](#data--safety-notes)
- [Contributing](#contributing)
- [Limitations](#limitations)
- [Support](#support)
- [License](#license)

---

## Why another YouTube MCP server?

Three other YouTube MCP servers exist:

- [`kimtaeyoon83/mcp-server-youtube-transcript`](https://github.com/kimtaeyoon83/mcp-server-youtube-transcript) —
  592 ★, focused on transcript/subtitle extraction only
- [`ZubeidHendricks/youtube-mcp-server`](https://github.com/ZubeidHendricks/youtube-mcp-server) —
  568 ★, 10 tools covering search and basic read operations
- [`pauling-ai/youtube-mcp-server`](https://github.com/pauling-ai/youtube-mcp-server) —
  19 ★, 40 tools with broad but early-stage coverage

All are good projects and I have **no affiliation** with them — they are
referenced here for honest comparison. They primarily focus on the **transcript**
or **read/search** surface of the YouTube Data API.

This project deliberately goes further:

| Capability | kimtaeyoon83 | ZubeidHendricks | pauling-ai | **this project** |
|---|---|---|---|---|
| Transcript / subtitle extraction | ✅ | ❌ | ❌ | ✅ (via captions API) |
| Video search | ❌ | ✅ | ✅ | ✅ |
| Video details (snippet, stats) | ❌ | ✅ | ✅ | ✅ |
| Channel details | ❌ | partial | ✅ | ✅ |
| Playlist management | ❌ | ❌ | ✅ | ✅ |
| Comment threads & replies | ❌ | ❌ | partial | ✅ |
| **YouTube Analytics API** | ❌ | ❌ | ❌ | ✅ |
| **YouTube Reporting API** | ❌ | ❌ | ❌ | ✅ |
| OAuth support (write operations) | ❌ | ❌ | ❌ | ✅ |
| Generated 1:1 endpoint tools | ❌ | ❌ | ❌ | ✅ (99 tools) |
| Typed convenience tools | ❌ | ✅ (10) | ✅ (40) | ✅ (16) |
| Docker support | ❌ | ❌ | ❌ | ✅ |
| HTTP transport + optional auth | ❌ | ❌ | ❌ | ✅ |

**Key differentiators:**

- **Full three-API coverage.** The only YouTube MCP server that covers Data API
  v3, Analytics API, and Reporting API in a single server. Analytics queries
  (views, likes, watch time by day/video/country) and Reporting jobs (automated
  daily CSV reports) are not available in any other YouTube MCP project.
- **Two tool layers.** 99 auto-generated 1:1 endpoint tools guarantee no API
  method is missed, while 16 typed convenience tools provide ergonomic access to
  the most common operations with sensible defaults and proper type hints.
- **OAuth support.** Enables write operations (upload, comment, rate) and
  Analytics/Reporting access that require user authorization — not just API key
  read-only access.
- **Production infrastructure.** Docker with HEALTHCHECK, optional HTTP
  transport with bearer token auth, Trivy container scanning, and dependency
  audit in CI.

---

## What it provides

A single stdio (or HTTP) MCP server exposing **115 tools** (published on PyPI as
[`youtube-mcp-full`](https://pypi.org/project/youtube-mcp-full/)):

- **Search** — `search_videos` (keyword search with filters for channel,
  duration, date range, region, safe search)
- **Videos** — `get_video` (single video by ID), `list_videos` (chart-based:
  mostPopular, recent)
- **Channels** — `get_channel` (by ID, handle, or username),
  `get_my_channel` (authenticated user's channel)
- **Playlists** — `list_playlists` (by channel or authenticated user),
  `list_playlist_items` (videos in a playlist)
- **Comments** — `list_comment_threads` (top-level comments for a video/channel,
  with search), `list_comments` (replies to a thread)
- **Analytics** — `analytics_query` (views, likes, subscribers, watch time,
  revenue with dimensions and filters)
- **Reporting** — `list_reporting_jobs`, `list_reporting_job_reports`,
  `list_report_types` (automated daily report management)
- **Subscriptions** — `list_subscriptions` (authenticated user's subscriptions)
- **Thumbnails** — `set_thumbnail` (upload custom thumbnail)
- **Video categories** — `list_video_categories` (region-specific category IDs)
- **Auth / meta** — `health`, `auth_status`, `list_supported_apis`
- **99 generated endpoint tools** — full 1:1 mapping of every YouTube API method
  with `params_json`/`body_json` interface for maximum flexibility

---

## Getting started

### Prerequisites

- Python **3.10+**
- A [Google Cloud](https://console.cloud.google.com/) project with YouTube
  Data API v3 enabled (and optionally Analytics + Reporting APIs)
- An MCP-capable client (opencode, Claude Desktop, Cursor, etc.)

### 1. Install

If you are using an AI coding client, a simple prompt is often enough to get
started, for example: "Install the YouTube MCP as described in this GitHub
repository oliverhruby/youtube-mcp". Most MCP-capable clients can then guide
you through the available setup options.

**Option A — from PyPI (recommended)**

```bash
uvx youtube-mcp-full
# or, if you prefer pip:
pip install youtube-mcp-full
```

`uvx` runs the package without a persistent install. If `uvx` is unavailable,
install `uv` first (`pip install uv` or `winget install astral-sh.uv`).

**Option B — from GitHub (latest source)**

```bash
uvx --from "git+https://github.com/oliverhruby/youtube-mcp.git" youtube-mcp-full
# or
pip install "git+https://github.com/oliverhruby/youtube-mcp.git"
```

**Option C — development from source**

```bash
git clone https://github.com/oliverhruby/youtube-mcp.git
cd youtube-mcp
uv sync
uv run youtube-mcp-full
```

**Option D — Docker**

Pull a prebuilt image (recommended):

```bash
docker pull ghcr.io/oliverhruby/youtube-mcp:latest

docker run --rm -i \
  -e YOUTUBE_API_KEY=your_api_key \
  ghcr.io/oliverhruby/youtube-mcp:latest
```

Build locally from source (fallback):

```bash
docker build -t youtube-mcp-full .

docker run --rm -i \
  -e YOUTUBE_API_KEY=your_api_key \
  youtube-mcp-full
```

The container uses the same environment variables described in
[Configure credentials](#2-configure-credentials). It includes a `HEALTHCHECK`
for container orchestration.

For HTTP transports, set additional vars:

- `MCP_TRANSPORT`: `stdio` (default), `sse`, or `streamable-http`
- `MCP_HOST`: bind host (default `0.0.0.0`)
- `MCP_PORT`: bind port (default `8000`)
- `MCP_API_KEY`: optional bearer token for HTTP auth

When `MCP_API_KEY` is set, HTTP requests must include `Authorization: Bearer <key>`.
If `MCP_API_KEY` is not set, HTTP endpoints are unauthenticated. For production,
prefer proper authentication and TLS via a reverse proxy or API gateway.

> `pyproject.toml` pins `mcp<2` (the stable FastMCP v1 API).

### 2. Configure credentials

**API key only (read-only access):**

Get an API key from [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
with YouTube Data API v3 enabled.

```bash
# Windows (persistent, per-user)
setx YOUTUBE_API_KEY "your_api_key"

# macOS / Linux
export YOUTUBE_API_KEY="your_api_key"
```

**OAuth (full access including Analytics, Reporting, and write operations):**

Create OAuth 2.0 credentials in Google Cloud Console with the YouTube Data API
and YouTube Analytics API scopes. You'll need a client ID, client secret, and
a refresh token.

```bash
# Windows
setx YOUTUBE_CLIENT_ID "your_client_id"
setx YOUTUBE_CLIENT_SECRET "your_client_secret"
setx YOUTUBE_REFRESH_TOKEN "your_refresh_token"

# macOS / Linux
export YOUTUBE_CLIENT_ID="your_client_id"
export YOUTUBE_CLIENT_SECRET="your_client_secret"
export YOUTUBE_REFRESH_TOKEN="your_refresh_token"
```

**API key + OAuth:** Both can be set. OAuth credentials take priority when
present; API key is used as fallback for public endpoints.

### 3. Register with your MCP client

**opencode** — add to `~/.config/opencode/opencode.json` (or `opencode.jsonc`):

```jsonc
{
  "mcp": {
    "youtube": {
      "type": "local",
      "enabled": true,
      "command": ["uvx", "youtube-mcp-full"],
      "env": {
        "YOUTUBE_API_KEY": "{env:YOUTUBE_API_KEY}"
      }
    }
  }
}
```

> Put credentials in your shell/environment (or a `.env`) and reference them with
> `{env:VAR}`, or hardcode them under `env:` directly.

**Claude Desktop / Cursor** — use `claude_desktop_config.json` /
`.mcp.json` with a `mcpServers` entry in the standard shape, pointing
`command`/`args` at the venv python and the `youtube_mcp` path, plus an
`env` block with your credentials.

After editing client config, **restart the client** so the MCP server is loaded.

---

## Prompt examples

| User prompt | Likely tool call(s) | Expected response |
|---|---|---|
| "Are we connected?" | `auth_status` | Whether API key / OAuth credentials are configured. |
| "Search for MCP server tutorials" | `search_videos query="MCP server tutorial"` | Top video results with titles, channel names, and video IDs. |
| "What are the most popular videos in the US right now?" | `list_videos chart="mostPopular" region_code="US"` | Trending videos with snippet and stats. |
| "Tell me about this video" (with video ID) | `get_video video_id="dQw4w9WgXcQ"` | Full video details: title, description, view/like counts, duration. |
| "Show me the @Google channel stats" | `get_channel handle="@Google"` | Subscriber count, video count, description, creation date. |
| "What playlists does @Google have?" | `get_channel handle="@Google"` → `list_playlists channel_id="UC..."` | Channel playlists with item counts. |
| "What are people saying about this video?" | `list_comment_threads video_id="..."` | Top-level comments with author, text, like counts. |
| "How many views did my channel get in January?" | `analytics_query metrics="views" start_date="2025-01-01" end_date="2025-01-31"` | Views total or daily breakdown. |
| "What reporting jobs do I have?" | `list_reporting_jobs` | Active reporting jobs with report type IDs. |

---

## Tool reference

### Convenience tools (16)

| Tool | Description | Writes? |
|---|---|---|
| `search_videos` | Search videos by keyword with filters (channel, duration, date, region) | |
| `get_video` | Get single video details by ID (snippet, stats, contentDetails) | |
| `list_videos` | List videos by chart (mostPopular, recent) or category | |
| `get_channel` | Get channel by ID, handle (@name), or username | |
| `get_my_channel` | Get authenticated user's own channel | |
| `list_playlists` | List playlists for a channel or authenticated user | |
| `list_playlist_items` | List videos in a playlist | |
| `list_comment_threads` | List top-level comments for a video or channel | |
| `list_comments` | List replies to a comment thread | |
| `analytics_query` | Query YouTube Analytics (views, likes, watch time, revenue) | |
| `list_reporting_jobs` | List YouTube Reporting API jobs | |
| `list_reporting_job_reports` | List reports from a specific reporting job | |
| `list_report_types` | List available report types | |
| `list_subscriptions` | List subscriptions (authenticated user or by channel) | |
| `set_thumbnail` | Upload and set a custom thumbnail for a video | ✅ |
| `list_video_categories` | List video categories for a region | |

### Generated endpoint tools (99)

Auto-generated 1:1 wrappers for every method in the YouTube Data API v3,
Analytics API v2, and Reporting API v1. Each tool accepts `params_json` and
`body_json` string arguments matching the REST API parameters.

Examples: `youtube_data_v3_search_list`, `youtube_data_v3_videos_list`,
`youtube_analytics_v2_reports_query`, `youtube_reporting_v1_jobs_list`.

Run `list_supported_apis` to see the full count and per-API breakdown.

### Meta tools

| Tool | Description |
|---|---|
| `health` | Server version, transport, tool counts |
| `auth_status` | Which credentials are configured |
| `list_supported_apis` | API surfaces and operation counts |

---

## Data & safety notes

- **API quotas.** YouTube Data API has a default quota of 10,000 units/day per
  project. Search costs 100 units; video list costs 1 unit. Analytics and
  Reporting API calls have separate quotas. Monitor usage in
  [Google Cloud Console](https://console.cloud.google.com/apis/dashboard).
- **OAuth scopes.** Write operations (upload, comment, rate) and Analytics
  access require OAuth with the appropriate scopes. API key access is read-only
  and limited to public data.
- **Rate limiting.** The YouTube API enforces per-second rate limits. The server
  does not add additional throttling — if you hit a rate limit, retry after the
  backoff period.
- **Generated tools are raw.** The 99 generated endpoint tools pass parameters
  as JSON strings. For ergonomic access, use the 16 convenience tools which
  have typed parameters and sensible defaults.

---

## Contributing

Contributor and maintainer guidance is in [CONTRIBUTING.md](CONTRIBUTING.md).

- Contribution workflow and local setup
- Architecture and tool layers
- Release process (PyPI, GitHub Releases, GHCR)
- CI quality gates and coverage drift checks

---

## Limitations

- **API quota dependent.** YouTube enforces daily and per-second quotas. Heavy
  usage (especially search) can exhaust the daily quota quickly.
- **OAuth complexity.** Full Analytics/Reporting access requires OAuth 2.0 with
  refresh tokens, which involves creating credentials in Google Cloud Console
  and handling token refresh. API key access is simpler but read-only.
- **No live streaming tools.** The liveBroadcasts/liveStreams endpoints are
  generated but not wrapped with convenience tools — use the raw generated
  tools with `params_json` for live stream management.
- **No video upload via convenience tool.** Video upload requires multipart
  media upload which the generated tool layer handles at the REST level but
  is not exposed through a convenience tool yet.
- The server processes requests synchronously. Large analytics queries may
  take several seconds.

---

## Support

If you like this project and want to support or request a feature, send me a
beer, it keeps my mind relaxed and ideas will come :-)

[![Support via PayPal](https://www.paypalobjects.com/en_US/i/btn/btn_donateCC_LG.gif)](https://www.paypal.me/oliverhruby/)

---

## License

[MIT](LICENSE) © Oliver Hrubý

YouTube is a trademark of Google LLC. This project is **not affiliated with or
endorsed by** Google or YouTube.

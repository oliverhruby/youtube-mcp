# Contributing

Thanks for contributing to `youtube-mcp`.

## Local setup

```bash
git clone https://github.com/oliverhruby/youtube-mcp.git
cd youtube-mcp
uv sync
```

Alternative setup:

```bash
python -m venv .venv
. .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -e .
```

Quick checks:

```bash
python -m py_compile src/youtube_mcp/__init__.py
python -m youtube_mcp
pytest -m "not live"
```

Live API checks (optional, requires credentials):

```bash
YOUTUBE_API_KEY=... pytest -m live
```

## Architecture and implementation

### High-level design

```text
MCP client (opencode / Claude / Cursor ...)
        |  stdio JSON-RPC
        v
youtube-mcp-full (FastMCP server, mcp<2, console entry point youtube-mcp-full)
        |  two tool layers
        +-- generated tools (1:1 endpoint mapping from discovery docs)
        +-- convenience tools (typed wrappers for common operations)
        v
google-api-python-client (Google's official Python client)
        v
YouTube Data API v3 / Analytics API v2 / Reporting API v1 (HTTPS)
```

### Tool layers

**Generated tools (99).** Auto-generated from Google discovery documents by
`scripts/generate_youtube_api_matrix.py`. Each YouTube API method becomes a
tool with `params_json`/`body_json` string arguments. Stored in
`src/youtube_mcp/data/youtube_api_operations.json`.

**Convenience tools (16).** Hand-written tools with explicit typed parameters
for the most commonly used operations. Each delegates to the generated
execution layer. Use `@_convenience` decorator and add to
`CONVENIENCE_TOOL_NAMES`.

### Key files

- `src/youtube_mcp/__init__.py`: MCP server runtime, generated tools, convenience tools, `main()`.
- `src/youtube_mcp/__main__.py`: `python -m youtube_mcp` entry.
- `src/youtube_mcp/data/youtube_api_operations.json`: generated endpoint matrix.
- `scripts/generate_youtube_api_matrix.py`: regenerates matrix from Google discovery docs.
- `scripts/check_coverage.py`: verifies matrix covers all discovery methods.
- `scripts/youtube_api_ignored_methods.json`: intentionally excluded methods.
- `pyproject.toml`: package metadata + console script.

### Auth and service building

```python
_SERVICE_BUILDERS = {
    "youtube_data_v3": ("youtube", "v3"),
    "youtube_analytics_v2": ("youtubeAnalytics", "v2"),
    "youtube_reporting_v1": ("youtubereporting", "v1"),
}
```

Services are built lazily via `_build_service(api)` and cached in
`_SERVICE_CACHE`. OAuth credentials take priority; API key is fallback.

### Serialization and errors

- `ok(data)` wraps successful responses with timestamp.
- `fail(message)` returns MCP-friendly error payloads.
- `_run()` catches exceptions and returns error responses.

### Dependency isolation

`mcp<2` is intentionally pinned. `uvx` and editable installs run in isolated
environments to avoid global package conflicts.

## Release process

Version source of truth is `pyproject.toml`.

- Tag format: `vX.Y.Z`
- PyPI publish: `.github/workflows/publish.yml` (OIDC trusted publishing)
- GitHub release notes: `.github/workflows/release.yml` (auto-generated)
- GHCR image publish: `.github/workflows/publish-container.yml`

Tag/version mismatch checks are enforced in publish and container workflows
via `scripts/check_tag_matches_version.py`.

## CI quality gates

`main` branch requires these checks:

- `quality-gates / python-sanity` — compile + install + unit tests
- `quality-gates / docker-mcp-smoke` — Docker build + MCP handshake
- `coverage-drift / coverage-drift` — discovery doc coverage check
- `security / pip-audit` — dependency vulnerability scan
- `container-security / trivy-image` — container vulnerability scan

## Coverage drift check

CI runs `scripts/check_coverage.py` to verify that every method in the
YouTube API discovery documents has a corresponding generated tool (or is
explicitly listed in `scripts/youtube_api_ignored_methods.json` with a reason).

Run locally:

```bash
python scripts/check_coverage.py
```

To regenerate the matrix after an upstream API change:

```bash
python scripts/generate_youtube_api_matrix.py
```

Then run the coverage check to confirm no drift:

```bash
python scripts/check_coverage.py
```

## Upstream coverage drift

Unlike edupage-mcp (which wraps a Python library), youtube-mcp generates tools
directly from Google's discovery documents. The coverage check fetches the live
discovery docs and compares against the generated matrix, so it catches new API
methods as soon as Google publishes them.

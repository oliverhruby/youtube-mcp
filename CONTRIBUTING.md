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
MCP client (OpenCode / Claude / Cursor ...)
        |  stdio JSON-RPC
        v
youtube-mcp-full (FastMCP server, mcp<2)
        |  endpoint-to-tool mapping layer
        v
Google YouTube APIs (Data v3 / Analytics / Reporting)
```

This project should stay close to YouTube REST API semantics and naming.

### Key files

- `src/youtube_mcp/__init__.py`: MCP server runtime + tools + `main()`.
- `src/youtube_mcp/__main__.py`: `python -m youtube_mcp` entry.
- `pyproject.toml`: package metadata + console script.
- `requirements.txt`: editable/dev install support.

## Release process

Version source of truth is `pyproject.toml`.

- Tag format: `vX.Y.Z`
- PyPI publish: `.github/workflows/publish.yml` (OIDC trusted publishing)
- GitHub release notes: `.github/workflows/release.yml` (auto-generated)
- GHCR image publish: `.github/workflows/publish-container.yml`

Tag/version mismatch checks are enforced in publish workflows.

# AGENTS.md

Guidance for maintainers and coding agents working on this repository.

## What this project is

A Model Context Protocol server that aims to provide near 1:1 coverage for
YouTube APIs as MCP tools.

Published to PyPI as `youtube-mcp-full`; GitHub repo is `youtube-mcp`.

## Core rule

Map YouTube API operations to MCP tools with minimal abstraction.

- prefer endpoint parity over custom wrappers
- preserve request/response structure where possible
- document every intentional deviation

## Layout

- `src/youtube_mcp/__init__.py`: server, generated tools, and convenience tools
- `src/youtube_mcp/__main__.py`: module entrypoint
- `src/youtube_mcp/data/youtube_api_operations.json`: generated endpoint matrix
- `scripts/generate_youtube_api_matrix.py`: regenerates matrix from discovery docs
- `scripts/check_coverage.py`: verifies matrix covers all discovery methods
- `scripts/youtube_api_ignored_methods.json`: intentionally excluded methods
- `.github/workflows/`: CI, security, release automation

## Tool layers

### Generated tools (1:1 endpoint mapping)

Auto-generated from Google discovery documents. Each YouTube API method
becomes a tool with `params_json`/`body_json` string args. ~99 tools.

### Convenience tools (ergonomic wrappers)

Typed-parameter tools for the most commonly used operations. ~16 tools.
Each delegates to the generated execution layer. Examples: `search_videos`,
`get_video`, `analytics_query`. Use `@_convenience` decorator and add to
`CONVENIENCE_TOOL_NAMES`.

## Tool design conventions

- All tools use `@_tool` or `@_convenience` and return JSON-serializable objects.
- Wrap tool logic in `_run(...)` to emit MCP-friendly error payloads.
- Docstrings must clearly say if the tool mutates state.
- Convenience tools must have explicit typed params and sensible defaults.

## Packaging and dependency rules

- Keep `mcp<2` until an explicit migration is done.
- Keep package name `youtube-mcp-full` and import module `youtube_mcp`.

## Commit policy

Use Conventional Commits:

- `feat`, `fix`, `docs`, `refactor`, `ci`, `build`, `chore`, `test`, `perf`

## Quality gates

Required baseline checks:

- python compile + install sanity
- unit tests (`pytest -m "not live"`)
- docker MCP handshake smoke test (expects >=100 tools)
- discovery doc coverage drift check (`scripts/check_coverage.py`, standalone workflow)
- dependency audit
- container scan

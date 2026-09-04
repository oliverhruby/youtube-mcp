# AGENTS.md - youtube-mcp-full

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

- `src/youtube_mcp/__init__.py`: server and tools
- `src/youtube_mcp/__main__.py`: module entrypoint
- `scripts/`: release and validation scripts
- `.github/workflows/`: CI, security, release automation

## Tool design conventions

- All tools use `@_tool` and return JSON-serializable objects.
- Wrap tool logic in `_run(...)` to emit MCP-friendly error payloads.
- Docstrings must clearly say if the tool mutates state.

## Packaging and dependency rules

- Keep `mcp<2` until an explicit migration is done.
- Keep package name `youtube-mcp-full` and import module `youtube_mcp`.

## Commit policy

Use Conventional Commits:

- `feat`, `fix`, `docs`, `refactor`, `ci`, `build`, `chore`, `test`, `perf`

## Quality gates

Required baseline checks:

- python compile + install sanity
- docker MCP handshake smoke test
- dependency audit
- container scan

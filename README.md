# youtube-mcp

Full-coverage YouTube MCP server project.

This repository is the canonical source for the PyPI package
`youtube-mcp-full`.

## Project goal

Implement a near 1:1 mapping of YouTube REST API functionality into MCP tools
across:

- YouTube Data API v3
- YouTube Analytics API
- YouTube Reporting API

## Current status

Initial scaffold is in place with:

- package + CLI entrypoint
- Docker support
- CI quality and security workflows
- release workflows for PyPI, GitHub Releases, and GHCR
- generated endpoint matrix with near 1:1 tool wrappers

## Install

```bash
uvx youtube-mcp-full
```

or:

```bash
pip install youtube-mcp-full
youtube-mcp-full
```

## Local development

```bash
git clone https://github.com/oliverhruby/youtube-mcp.git
cd youtube-mcp
uv sync
python -m py_compile src/youtube_mcp/__init__.py
python -m youtube_mcp
```

## Tool reference (scaffold)

- `health`: basic server runtime info
- `auth_status`: env-based auth configuration status
- `list_supported_apis`: declared API surfaces and current scaffold status
- generated endpoint tools from `src/youtube_mcp/data/youtube_api_operations.json`

## Testing

Standard testing approach used across this MCP portfolio:

- unit tests (no live credentials required)
- optional live integration tests gated by marker and env vars

Run unit tests:

```bash
pytest -m "not live"
```

Run live tests (requires `YOUTUBE_API_KEY` at minimum):

```bash
pytest -m live
```

## Environment variables

- `MCP_TRANSPORT`: `stdio` (default), `sse`, or `streamable-http`
- `MCP_HOST`: host for HTTP transports (default: `0.0.0.0`)
- `MCP_PORT`: port for HTTP transports (default: `8000`)
- `YOUTUBE_API_KEY`: optional API key for public endpoints
- `YOUTUBE_CLIENT_ID`: optional OAuth client id
- `YOUTUBE_CLIENT_SECRET`: optional OAuth client secret
- `YOUTUBE_REFRESH_TOKEN`: optional OAuth refresh token

## Contributing

See `CONTRIBUTING.md` for local setup and maintainer workflow.

## License

[MIT](LICENSE)

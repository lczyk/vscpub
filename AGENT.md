# vscpub

CLI tool for publishing and managing solutions on Broadcom's VCF Solutions Catalog API.

## Setup

```bash
uv sync --all-extras --dev
```

## Common commands

```bash
uv run tox -e py313   # run tests
uv run tox -e lint    # check formatting and linting
uv run tox -e fix     # auto-fix formatting and linting
uv run vscpub --help  # run the CLI
```

## Authentication

Set exactly one of these in the environment before running any command:

```bash
export VSCPUB_API_TOKEN=<refresh-token>
# or
export VSCPUB_CLIENT_ID=<id>
export VSCPUB_CLIENT_SECRET=<secret>
```

## Architecture

```
vscpub/
  exceptions.py   — VscpubError, ConfigError, ApiError
  config.py       — load_config(): YAML → typed dataclasses
  client.py       — VscClient: thin requests wrapper, 1:1 with API endpoints
  upload.py       — GCS pre-signed POST upload + hash computation
  workflows.py    — business logic orchestrating client + upload
  cli.py          — Click command tree, calls workflows
```

The layering is strict: `cli → workflows → client/upload`. The CLI never calls the client or upload directly; workflows never call Click.

## API

Single production endpoint: `https://eapi.broadcom.com/vcf/vsc/gtw/api/v3`

The swagger spec is at `swagger/VSC-API-Spec.yaml`. The CLI specification (YAML config schema, command behaviour, upload workflow) is at `specs/vscpub-spec.md`.

## Key conventions

- YAML config files use `snake_case`; API wire format uses `camelCase`. Translation happens inside `workflows.py` (`_build_*_payload` functions).
- Local file paths in YAML (logo, assets, screenshots) are resolved relative to the YAML file's directory, not the CWD.
- `--dry-run` suppresses all mutating HTTP calls (`PATCH`, `POST`) and file uploads; read-only `GET` calls always execute so the workflow can produce meaningful output.
- `--storage <file>` accepts the JSON output of `vscpub storage create`, skipping a repeat call to `GET /storage-location`.
- Credentials are never stored in config files; environment variables only.

## Testing

Tests use `unittest.mock` — no network calls are made. Fixtures are in `tests/fixtures/`.

When adding a test that exercises a workflow with a VM asset config, patch both `vscpub.workflows.upload_file` and `vscpub.workflows.validate_hash` to avoid hitting the filesystem.

# vscpub

CLI tool for publishing and managing solutions on Broadcom's VCF Solutions Catalog API.
VCF Solutions Catalog is a public cloud marketplace for advertising virtual machine
and OCI container products.

## Setup

```bash
uv sync --all-extras --dev
```

## Common commands

```bash
uv run tox -e py313   # run tests
uv run tox -e lint    # check formatting and linting
uv run tox -e fix     # auto-fix formatting and linting
uv run vscpub --help  # get CLI help text
```

Only use `vscpub` with `--help`. All functional commands require
authentication.

## API

Single production endpoint: `https://eapi.broadcom.com/vcf/vsc/gtw/api/v3`

The swagger spec is at `swagger/VSC-API-Spec.yaml`. The CLI specification (YAML config schema, command behaviour, upload workflow) is at `specs/vscpub-spec.md`.

## Key conventions

- YAML config files use `snake_case`; API wire format uses `camelCase`. Translation happens
  inside `workflows.py` (`_build_*_payload` functions).
- Local file paths in YAML (logo, assets, screenshots) are resolved relative to the YAML
  file's directory, not the CWD.
- `--dry-run` suppresses all mutating HTTP calls (`PATCH`, `POST`) and file uploads; read-only
  `GET` calls always execute so the workflow can produce meaningful output.
- `--storage <file>` accepts the JSON output of `vscpub storage create`, skipping a repeat call
  to `GET /storage-location`.
- Credentials are never stored in config files; environment variables only.

## Testing

Tests use `unittest.mock` — no network calls are made. Fixtures are in `tests/fixtures/`.

When adding a test that exercises a workflow with a VM asset config, patch both `vscpub.workflows.upload_file` and `vscpub.workflows.validate_hash` to avoid hitting the filesystem.

## Custom agents

Specific personas can be activated by including `@<name>` anywhere in a message. When the AI
sees this token it must:

1. **Locate** `kb/agents/<name>.md`. If the file does not exist, list the available agents from
   the table below and stop.
2. **Parse** the YAML frontmatter (`name`, `description`, `tools`). The `tools:` list is
   VS Code-specific metadata — non-VS Code consumers should ignore it, but must honour the
   `<constraints>` and `<thinking_process>` blocks in the markdown body.
3. **Adopt** the full persona described in the file: identity, thinking process, and
   constraints. Remain in that persona for the duration of the request.
4. **Enforce scope** — respect any directory or file restrictions stated in the agent's
   `<constraints>` block (e.g., write to `tests/` only). Do not perform actions outside those
   boundaries, even if asked.

Agent files in `kb/agents/` are symlinks to their canonical definitions in `.github/agents/`,
so there is a single source of truth.

### Available agents

| Agent | Description | Invocation | File |
|---|---|---|---|
| `test-agent` | QA engineer — writes and runs pytest tests; never modifies source code | `@test-agent` | `kb/agents/test-agent.md` |

### Adding a new agent

1. Create the canonical definition at `.github/agents/<name>.md` using the VS Code custom agent
   format (YAML frontmatter + markdown body with `## Identity`, `<thinking_process>`, and
   `<constraints>` sections).
2. Symlink it into `kb/agents/` so non-VS Code consumers can find it:
   ```bash
   ln -s ../../.github/agents/<name>.md kb/agents/<name>.md
   ```
3. Add a row to the **Available agents** table above.

# Contributing

Thanks for helping make xray-sync safer and more useful.

## Principles

- Keep source environments read-only.
- Keep exports, plans, logs, checkpoints, and fixtures free of secrets.
- Do not add speculative Xray mutations. Confirm capabilities with the schema probe and fixtures first.
- Prefer small, testable changes.

## Local Checks

```bash
uv run pytest
uv run ruff check .
uv run mypy src tools
```

Integration tests must be marked with `@pytest.mark.integration` and must require explicit credentials.

# xray-sync

xray-sync synchronises Xray Test Management data between Jira Cloud environments.

Its primary use case is restoring Xray application data after a Jira production project has been copied to an Atlassian sandbox. Atlassian sandbox copies do not automatically recreate all Marketplace application-owned data. xray-sync uses the Jira Cloud REST API together with the Xray Cloud GraphQL and REST APIs to inspect, compare, plan, synchronise and verify Xray state.

This project is not affiliated with or endorsed by Xray or Atlassian.

## Status

The current implementation supports a conservative production-to-sandbox workflow:

- inspect and export both environments
- compare supported Xray-owned structures
- generate an explicit dry-run plan
- apply target-only GraphQL operations for supported Manual Test steps and relationships

It does not delete target data and it does not mutate the source environment.

## Install

```bash
uv sync
```

## Configure

Create `xray-sync.yaml`:

```yaml
environments:
  prod:
    jira:
      url: https://company.atlassian.net
      email_env: JIRA_PROD_EMAIL
      token_env: JIRA_PROD_TOKEN
    xray:
      client_id_env: XRAY_PROD_CLIENT_ID
      client_secret_env: XRAY_PROD_CLIENT_SECRET
  sandbox:
    jira:
      url: https://company-sandbox.atlassian.net
      email_env: JIRA_SANDBOX_EMAIL
      token_env: JIRA_SANDBOX_TOKEN
    xray:
      client_id_env: XRAY_SANDBOX_CLIENT_ID
      client_secret_env: XRAY_SANDBOX_CLIENT_SECRET
```

Then export the referenced secrets. `.env.example` lists the expected names, but credentials are read from environment variables and are never written to exports, plans, logs, or fixtures.

## Commands

```bash
xray-sync doctor
xray-sync inspect --environment prod --project ABC
xray-sync export --environment prod --project ABC --output ./abc-export
python tools/schema_probe.py --environment prod
xray-sync diff --source prod --target sandbox --project ABC
xray-sync plan --source prod --target sandbox --project ABC --output plan.json
xray-sync apply plan.json
xray-sync verify --source prod --target sandbox --project ABC
```

## Sandbox Refresh Workflow

```bash
python tools/schema_probe.py --environment prod
python tools/schema_probe.py --environment sandbox

xray-sync diff --source prod --target sandbox --project ABC

xray-sync plan \
  --source prod \
  --target sandbox \
  --project ABC \
  --output plan.json

xray-sync apply plan.json

xray-sync verify --source prod --target sandbox --project ABC
```

`plan` is the dry run. It reads both environments and writes explicit proposed operations without mutating anything.

`apply` is the only command that mutates Xray, and it uses only the plan's target environment. It writes a checkpoint beside the plan after each completed operation so interrupted runs can be resumed by running the same apply command again.

During apply, the CLI shows a progress bar with the current operation, completed/total counts, percentage, elapsed time, and estimated remaining time. If Xray rate-limits the run, the status line changes to show the retry wait before continuing from the same checkpoint.

## Current Sync Support

Supported apply operations:

- add missing Manual Test steps
- update changed Manual Test steps when the target step id is known
- add Tests to Preconditions
- add Tests to Test Sets
- add Tests to Test Plans
- add Tests to Test Executions
- add Tests to Test Repository folders

Unsupported by design today:

- source mutations
- deletions
- replacing target step lists when the target has extra steps
- creating missing Jira issues after sandbox copy
- speculative Xray mutations not confirmed by schema/docs
- Test Runs, defects, attachments, and evidence

## Development

```bash
uv run pytest
uv run ruff check .
uv run mypy src tools
```

## API Capability Discovery

Run:

```bash
python tools/schema_probe.py --environment prod
```

The probe authenticates with Xray Cloud, confirms GraphQL access, attempts introspection, records Query and Mutation fields, runs conservative sample reads where a key or issue id is supplied, and writes sanitised responses to `tests/fixtures/xray_schema/`.

The project rule is strict: do not invent Xray API operations. Unknown create/update/delete capabilities remain unknown until the schema probe or captured fixtures confirm them.

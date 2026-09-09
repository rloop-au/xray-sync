# xray-sync

xray-sync synchronises Xray Test Management data between Jira Cloud environments.

Its primary use case is restoring Xray application data after a Jira project has been copied from one Jira Cloud environment to another. Jira Cloud copies do not automatically recreate all Marketplace application-owned data. xray-sync uses the Jira Cloud REST API together with the Xray Cloud GraphQL and REST APIs to inspect, compare, plan, synchronise and verify Xray state.

This project is not affiliated with or endorsed by Xray or Atlassian.

## Status

The current implementation supports a conservative source-to-target workflow:

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
env_file: .env

environments:
  source:
    jira:
      url: https://source-company.atlassian.net
      email_env: JIRA_SOURCE_EMAIL
      token_env: JIRA_SOURCE_TOKEN
    xray:
      client_id_env: XRAY_SOURCE_CLIENT_ID
      client_secret_env: XRAY_SOURCE_CLIENT_SECRET
  target:
    jira:
      url: https://target-company.atlassian.net
      email_env: JIRA_TARGET_EMAIL
      token_env: JIRA_TARGET_TOKEN
    xray:
      client_id_env: XRAY_TARGET_CLIENT_ID
      client_secret_env: XRAY_TARGET_CLIENT_SECRET
```

Then export the referenced secrets or place them in the configured `env_file`.
`.env.example` lists the expected names, but credentials are never written to exports,
plans, logs, or fixtures. If `env_file` is omitted, xray-sync will auto-load `.env`
beside the config file when it exists. You can also override the configured file with
`XRAY_SYNC_ENV_FILE=.env.ampol`.

## Commands

```bash
xray-sync doctor
xray-sync inspect --environment source --project ABC
xray-sync export --environment source --project ABC --output ./abc-export
python tools/schema_probe.py --environment source
xray-sync diff --source source --target target --project ABC
xray-sync plan --source source --target target --project ABC --output plan.json
xray-sync apply plan.json
xray-sync verify --source source --target target --project ABC
```

## Refresh Workflow

```bash
python tools/schema_probe.py --environment source
python tools/schema_probe.py --environment target

xray-sync diff --source source --target target --project ABC

xray-sync plan \
  --source source \
  --target target \
  --project ABC \
  --output plan.json

xray-sync apply plan.json

xray-sync verify --source source --target target --project ABC
```

`plan` is the dry run. It reads both environments and writes explicit proposed operations without mutating anything.

`apply` is the only command that mutates Xray, and it uses only the plan's target environment. It writes a checkpoint beside the plan after each completed operation so interrupted runs can be resumed by running the same apply command again.

During apply, the CLI shows a progress bar with the current operation, completed/total counts, percentage, elapsed time, and estimated remaining time. If Xray rate-limits the run, the status line changes to show the retry wait before continuing from the same checkpoint.

## Project Style Preflight

`inspect`, `diff`, `plan` and `verify` read the Jira project's `style`/`simplified` flags and
report whether each side is team-managed or company-managed. `inspect` shows it as a
`Project style` row and exports record it as `projectStyle` in `manifest.json`.

Discovery itself is project-style agnostic - it drives everything from Xray GraphQL with
`project = "KEY"` - but team-managed projects scope their work item types to the project, so the
Xray types (Test, Precondition, Test Set, Test Plan, Test Execution) have to be configured in each
team-managed project separately. When they are not, that environment discovers zero Xray entities
and `plan` fails reporting every Test as missing from the target. The preflight warns about this
before you reach `plan`:

```
Warning: Team-managed project detected in: source (LOY), target (LOY).
Warning: No Xray entities were discovered in: target (LOY). Configure the Xray work item
types for that project in Jira before running plan or apply, otherwise planning fails with
every Test reported as missing.
```

The warning is advisory. It never blocks a command, and `plan` still refuses to build a plan when
the target is genuinely missing issues.

## Current Sync Support

Supported apply operations:

- add missing Manual Test steps
- update changed Manual Test steps when the target step id is known
- add Tests to Preconditions
- add Tests to Test Sets
- add Tests to Test Plans
- add Tests to Test Executions
- add Test Executions to Test Plans
- update existing Test Run status
- add Tests to Test Repository folders

Unsupported by design today:

- source mutations
- deletions
- replacing target step lists when the target has extra steps
- creating missing Jira issues after the Jira project copy
- speculative Xray mutations not confirmed by schema/docs
- Test Run comments, dates, defects, attachments/evidence, and step-level results

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

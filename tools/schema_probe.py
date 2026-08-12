from __future__ import annotations

import argparse
import asyncio
import re
from collections.abc import Awaitable
from pathlib import Path
from typing import Any, cast

from rich.console import Console

from xray_sync.api.xray_auth import XrayAuthClient
from xray_sync.api.xray_graphql import XrayGraphQLClient
from xray_sync.config import load_config
from xray_sync.exceptions import XraySyncError
from xray_sync.storage.filesystem import write_json

console = Console()
DEFAULT_OUTPUT = Path("tests/fixtures/xray_schema")
SECRET_KEYS = {"authorization", "client_secret", "clientSecret", "token", "access_token"}

INTROSPECTION_QUERY = """
query IntrospectionQuery {
  __schema {
    queryType {
      name
      fields {
        name
        args { name type { kind name ofType { kind name } } }
        type { kind name ofType { kind name } }
      }
    }
    mutationType {
      name
      fields {
        name
        args { name type { kind name ofType { kind name } } }
        type { kind name ofType { kind name } }
      }
    }
  }
}
"""

CONFIRM_QUERY = "query { __typename }"

SAMPLE_QUERIES = {
    "test": """
      query ProbeTest($issueId: String!) {
        getTest(issueId: $issueId) { issueId jira(fields: ["key"]) }
      }
    """,
    "precondition": """
      query ProbePrecondition($issueId: String!) {
        getPrecondition(issueId: $issueId) { issueId jira(fields: ["key"]) }
      }
    """,
    "test_set": """
      query ProbeTestSet($issueId: String!) {
        getTestSet(issueId: $issueId) { issueId jira(fields: ["key"]) }
      }
    """,
    "test_plan": """
      query ProbeTestPlan($issueId: String!) {
        getTestPlan(issueId: $issueId) { issueId jira(fields: ["key"]) }
      }
    """,
    "test_execution": """
      query ProbeTestExecution($issueId: String!) {
        getTestExecution(issueId: $issueId) { issueId jira(fields: ["key"]) }
      }
    """,
}


async def main() -> int:
    parser = argparse.ArgumentParser(description="Probe current Xray Cloud GraphQL capabilities.")
    parser.add_argument("--environment", required=True)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--sample-issue-id",
        help="Optional Xray/Jira issue id to use for entity probes.",
    )
    args = parser.parse_args()

    app_config = load_config(args.config)
    env = app_config.environment(args.environment)
    args.output.mkdir(parents=True, exist_ok=True)

    async with XrayAuthClient(env.xray) as auth:
        async with XrayGraphQLClient(env.xray, auth) as graphql:
            report = await probe(graphql, output=args.output, sample_issue_id=args.sample_issue_id)

    report_text = render_report(report)
    (args.output / "capability_report.txt").write_text(report_text, encoding="utf-8")
    console.print(report_text)
    return 0


async def probe(
    graphql: XrayGraphQLClient,
    *,
    output: Path,
    sample_issue_id: str | None,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "graphql_access": False,
        "introspection": "UNKNOWN",
        "query_fields": [],
        "mutation_fields": [],
        "sample_reads": {},
        "rest_required": [],
    }
    confirm = await _capture("confirm_graphql", graphql.query(CONFIRM_QUERY), output)
    report["graphql_access"] = "__typename" in confirm

    try:
        introspection = await _capture("introspection", graphql.query(INTROSPECTION_QUERY), output)
        schema = introspection["__schema"]
        report["introspection"] = "YES"
        report["query_fields"] = _field_summaries(schema.get("queryType", {}).get("fields") or [])
        mutation_type = schema.get("mutationType") or {}
        report["mutation_fields"] = _field_summaries(mutation_type.get("fields") or [])
    except XraySyncError as exc:
        write_json(output / "introspection_error.json", sanitise(exc.detail or {"error": str(exc)}))
        report["introspection"] = "NO"

    if sample_issue_id:
        for name, query in SAMPLE_QUERIES.items():
            try:
                data = await _capture(
                    f"sample_{name}",
                    graphql.query(query, {"issueId": sample_issue_id}),
                    output,
                )
                report["sample_reads"][name] = "YES" if data else "UNKNOWN"
            except XraySyncError as exc:
                write_json(
                    output / f"sample_{name}_error.json",
                    sanitise(exc.detail or {"error": str(exc)}),
                )
                report["sample_reads"][name] = "NO"
    else:
        report["sample_reads"] = {name: "SKIPPED" for name in SAMPLE_QUERIES}

    write_json(output / "capability_report.json", sanitise(report))
    return report


async def _capture(
    name: str, awaitable: Awaitable[dict[str, Any]], output: Path
) -> dict[str, Any]:
    data = await awaitable
    write_json(output / f"{name}.json", sanitise(data))
    return data


def _field_summaries(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries = []
    for field in sorted(fields, key=lambda item: item.get("name", "")):
        summaries.append(
            {
                "name": field.get("name"),
                "args": [
                    {"name": arg.get("name"), "type": _type_name(arg.get("type"))}
                    for arg in field.get("args", [])
                ],
                "type": _type_name(field.get("type")),
            }
        )
    return summaries


def _type_name(value: dict[str, Any] | None) -> str | None:
    if not value:
        return None
    if value.get("name"):
        return cast(str, value["name"])
    nested = value.get("ofType")
    if nested:
        nested_name = _type_name(nested)
        return f"{value.get('kind')}[{nested_name}]"
    return value.get("kind")


def sanitise(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "<redacted>" if key in SECRET_KEYS else sanitise(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitise(item) for item in value]
    if isinstance(value, str):
        return re.sub(r"Bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer <redacted>", value)
    return value


def render_report(report: dict[str, Any]) -> str:
    lines = [
        "XRAY API CAPABILITY REPORT",
        "Entity              Read     Create     Update     Delete",
        "---------------------------------------------------------",
    ]
    entities = {
        "Test": report["sample_reads"].get("test", "?"),
        "Precondition": report["sample_reads"].get("precondition", "?"),
        "Test Set": report["sample_reads"].get("test_set", "?"),
        "Test Plan": report["sample_reads"].get("test_plan", "?"),
        "Test Execution": report["sample_reads"].get("test_execution", "?"),
        "Test Run": "?",
        "Repository Folder": "?",
        "Evidence": "?",
    }
    for entity, read in entities.items():
        lines.append(f"{entity:<19} {read:<8} ?          ?          ?")
    lines.append("")
    lines.append("GraphQL:")
    lines.append(f"  Access: {'YES' if report['graphql_access'] else 'NO'}")
    lines.append(f"  Introspection: {report['introspection']}")
    lines.append(f"  Query fields: {len(report['query_fields'])}")
    lines.append(f"  Mutation fields: {len(report['mutation_fields'])}")
    lines.append("REST required:")
    lines.append("  UNKNOWN until schema and REST fixtures confirm unsupported GraphQL operations.")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

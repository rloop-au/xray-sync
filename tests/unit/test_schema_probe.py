from __future__ import annotations

from tools.schema_probe import render_report, sanitise


def test_sanitise_redacts_secret_keys_and_bearer_tokens() -> None:
    value = {
        "token": "secret",
        "nested": {"message": "Authorization: Bearer abc123"},
    }

    assert sanitise(value) == {
        "token": "<redacted>",
        "nested": {"message": "Authorization: Bearer <redacted>"},
    }


def test_render_report_keeps_unknown_mutations_unknown() -> None:
    report = {
        "graphql_access": True,
        "introspection": "YES",
        "query_fields": [{"name": "getTests"}],
        "mutation_fields": [{"name": "someMutation"}],
        "sample_reads": {"test": "YES"},
    }

    text = render_report(report)

    assert "Test                YES      ?          ?          ?" in text
    assert "Mutation fields: 1" in text

from __future__ import annotations

from typing import Any

from xray_sync.discovery.source import _connection_keys, _jira_key, _nested_test_keys


def _entry(key: str) -> dict[str, Any]:
    return {"issueId": "10001", "jira": {"key": key}}


def test_jira_key_reads_nested_key() -> None:
    assert _jira_key(_entry("LOY-1")) == "LOY-1"


def test_jira_key_tolerates_null_entry() -> None:
    assert _jira_key(None) is None


def test_jira_key_tolerates_null_jira_object() -> None:
    assert _jira_key({"issueId": "10001", "jira": None}) is None


def test_nested_test_keys_skips_null_entries() -> None:
    execution = {"tests": {"results": [_entry("LOY-2"), None, _entry("LOY-1")]}}

    assert _nested_test_keys(execution) == ["LOY-1", "LOY-2"]


def test_nested_test_keys_tolerates_null_connection() -> None:
    assert _nested_test_keys({"tests": None}) == []


def test_nested_test_keys_tolerates_null_results() -> None:
    assert _nested_test_keys({"tests": {"results": None}}) == []


def test_nested_test_keys_tolerates_missing_connection() -> None:
    assert _nested_test_keys({}) == []


def test_connection_keys_skips_null_entries() -> None:
    test = {"preconditions": {"results": [None, _entry("LOY-9")]}}

    assert _connection_keys(test, "preconditions") == ["LOY-9"]

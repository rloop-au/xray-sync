from __future__ import annotations

from xray_sync.diff.normalise import normalise_test
from xray_sync.model.test import TestStep, XrayTest


def test_normalise_test_drops_internal_ids_and_sorts_unordered_relationships() -> None:
    test = XrayTest(
        jira_key="ABC-1",
        jira_id="10001",
        xray_id="x1",
        test_type="Manual",
        steps=[TestStep(id="step-1", action="Do", data=None, expected_result="Done")],
        preconditions=["ABC-3", "ABC-2"],
    )

    data = normalise_test(test)

    assert "jira_id" not in data
    assert "xray_id" not in data
    assert data["preconditions"] == ["ABC-2", "ABC-3"]
    assert data["steps"] == [{"action": "Do", "data": "", "expected_result": "Done"}]

import json

from cs_voice.state import SessionState


def test_initial_state_is_incomplete():
    assert not SessionState().is_complete()


def test_state_is_complete_only_when_all_four_slots_confirmed():
    state = SessionState()
    for slot in (state.employee_id, state.issue_category, state.description):
        slot.status = "confirmed"
    assert not state.is_complete(), "three of four confirmed is not complete"

    state.urgency.status = "confirmed"
    assert state.is_complete()


def test_snapshot_is_valid_json_and_omits_empty_fields():
    snap = json.loads(SessionState().snapshot())
    assert set(snap) == {"employee_id", "issue_category", "description", "urgency", "escalated"}
    assert snap["escalated"] is False
    assert "candidate" not in snap["employee_id"]
    assert "value" not in snap["employee_id"]

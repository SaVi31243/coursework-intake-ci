import json
import sqlite3

import pytest

from service import create_app


@pytest.mark.parametrize(("enabled", "status"), [("1", 201), ("0", 503)])
def test_confirmation_runs_after_storage(tmp_path, monkeypatch, capsys, enabled, status):
    db_file = tmp_path / "separate.sqlite"
    monkeypatch.setenv("SUBMIT_DB", str(db_file))
    monkeypatch.setenv("CONFIRMATION_ENABLED", enabled)
    client = create_app().test_client()
    payload = {"group_code": "SE-64", "submission_key": "ack-demo"}
    response = client.post("/submissions", json=payload)

    assert response.status_code == status
    assert response.json["id"] == 1
    if enabled == "1":
        assert response.json["confirmation"] == "ACK-000001"
    with sqlite3.connect(db_file) as db:
        assert db.execute("SELECT id, submission_key FROM submissions").fetchall() == [(1, "ack-demo")]

    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    outcome = "confirmation_sent" if status == 201 else "confirmation_failed"
    assert [event["event"] for event in events] == ["submission_saved", outcome, "submission_response"]
    assert {event["request_id"] for event in events} == {response.headers["X-Request-Id"]}
    assert client.get("/health").status_code == 200
    assert client.get("/submissions/1").json == {"id": 1, **payload}
    replay = client.post("/submissions", json=payload)
    assert (replay.status_code, replay.json) == (200, {"id": 1})

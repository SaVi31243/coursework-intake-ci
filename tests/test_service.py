import sqlite3

import pytest

from service import create_app


@pytest.fixture
def api(tmp_path, monkeypatch):
    database = tmp_path / "local-test.sqlite"
    monkeypatch.setenv("SUBMIT_DB", str(database))
    monkeypatch.setenv("CONFIRMATION_ENABLED", "1")
    return create_app().test_client(), database


@pytest.mark.parametrize(
    "group, accepted",
    [("SE-64", True), ("SE-08", True), ("se-64", False),
     ("SE-640", False), ("SE-6Z", False), (None, False)],
)
def test_validation_before_insert(api, group, accepted):
    client, database = api
    answer = client.post("/submissions", json={"group_code": group, "submission_key": "format"})
    assert answer.status_code == (201 if accepted else 400)
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT COUNT(*) FROM submissions").fetchone() == (int(accepted),)


def test_retry_resolves_existing_row(api):
    client, database = api
    payload = {"group_code": "SE-64", "submission_key": "repeat-17"}
    first = client.post("/submissions", json=payload)
    assert first.status_code == 201
    number = first.json["id"]
    assert client.get(f"/submissions/{number}").json == {"id": number, **payload}

    second = client.post("/submissions", json=payload)
    assert (second.status_code, second.json) == (200, {"id": number})
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT id FROM submissions").fetchall() == [(number,)]


def test_health_status(api):
    client, _ = api
    answer = client.get("/health")
    assert answer.status_code == 429
    assert answer.json["status"] == "ok"

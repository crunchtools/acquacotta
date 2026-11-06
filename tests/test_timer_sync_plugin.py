"""Tests for timer_sync_plugin: remaining time, stale owner, validation, last-writer-wins."""

from datetime import datetime, timedelta, timezone

import pytest

import timer_sync_plugin as tsp

NOW = datetime(2026, 6, 23, 15, 10, 0, tzinfo=timezone.utc)


class FakeTransport:
    files: dict = {}

    def download_file(self, name):
        return self.files.get(name)

    def upload_file(self, name, content):
        self.files[name] = content


@pytest.fixture(autouse=True)
def fake_drive(monkeypatch):
    FakeTransport.files = {}
    monkeypatch.setattr(tsp, "_transport", lambda *_: FakeTransport())


def running(owner="a", start=None):
    start = start or NOW - timedelta(minutes=5)
    return {
        "state": "running",
        "type": "focus",
        "name": "Write",
        "duration_minutes": 25,
        "start_time": start.isoformat(),
        "owner_client_id": owner,
    }


def test_constants():
    assert tsp.CHECKIN_INTERVAL_SECONDS == 60
    assert tsp.STALE_AFTER_SECONDS == 180


def test_missing_file_is_idle():
    assert tsp.read_sync(None, "f", NOW)["timer"] == {"state": "idle"}


def test_remaining_computed_from_start_not_stored():
    tsp.write_sync(None, "f", running(), NOW)
    assert "remaining_seconds" not in FakeTransport.files[tsp.SYNC_FILE]
    timer = tsp.read_sync(None, "f", NOW + timedelta(seconds=90))["timer"]
    assert timer["remaining_seconds"] == 20 * 60 - 90


def test_stale_owner_reads_idle():
    tsp.write_sync(None, "f", running(), NOW)
    ok = tsp.read_sync(None, "f", NOW + timedelta(seconds=tsp.STALE_AFTER_SECONDS))
    assert ok["timer"]["state"] == "running"
    late = tsp.read_sync(None, "f", NOW + timedelta(seconds=tsp.STALE_AFTER_SECONDS + 1))
    assert late["timer"] == {"state": "idle"}


def test_finished_timer_reads_idle():
    tsp.write_sync(None, "f", running(start=NOW - timedelta(minutes=30)), NOW)
    assert tsp.read_sync(None, "f", NOW)["timer"] == {"state": "idle"}


def test_last_writer_wins():
    tsp.write_sync(None, "f", running("a"), NOW)
    tsp.write_sync(None, "f", running("b"), NOW)
    assert tsp.read_sync(None, "f", NOW)["timer"]["owner_client_id"] == "b"


def test_idle_write_clears_timer():
    tsp.write_sync(None, "f", running(), NOW)
    tsp.write_sync(None, "f", {"state": "idle"}, NOW)
    assert tsp.read_sync(None, "f", NOW)["timer"] == {"state": "idle"}


def test_corrupt_file_reads_idle():
    FakeTransport.files[tsp.SYNC_FILE] = "{not json"
    assert tsp.read_sync(None, "f", NOW)["timer"] == {"state": "idle"}


@pytest.mark.parametrize(
    "mutate",
    [
        {"state": "paused"},
        {"type": "nap"},
        {"duration_minutes": 0},
        {"duration_minutes": True},
        {"start_time": "yesterday"},
        {"owner_client_id": ""},
        {"name": 5},
    ],
)
def test_invalid_timer_rejected(mutate):
    with pytest.raises(ValueError):
        tsp.validate_timer({**running(), **mutate})


def test_sync_endpoints_require_auth(client):
    assert client.get("/api/timer-sync").status_code == 401
    assert client.post("/api/timer-sync", json={"timer": {"state": "idle"}}).status_code == 401

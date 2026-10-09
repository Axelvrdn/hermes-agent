import json
from pathlib import Path

import pytest

from cron.calendar_approvals import register_calendar_approval, resolve_calendar_approval


BRIEF = """**Révision conseillée**
- Travailler le cadrage.

📅 **DEMANDE CALENDRIER — EN ATTENTE**
- **ID** : `REV-20261011-1700`
- **Action** : créer un événement
- **Titre** : `Révision — Innovation — cadrage`
- **Début** : dimanche 11 octobre 2026, 17 h 00, Europe/Paris
- **Fin** : dimanche 11 octobre 2026, 17 h 35, Europe/Paris
- **Motif** : préparer le cours.
- **Conflit vérifié** : oui — aucun événement.
"""


def test_register_calendar_approval_persists_typed_pending_record(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    record = register_calendar_approval(
        BRIEF, "REV-20261011-1700", job_id="eefcdf90b2c1",
        execution_id="exec-1", account="axel@example.com")

    assert record["status"] == "pending"
    assert record["event"] == {
        "summary": "Révision — Innovation — cadrage",
        "start_time": "2026-10-11T17:00:00+02:00",
        "end_time": "2026-10-11T17:35:00+02:00",
        "timezone": "Europe/Paris",
        "description": "préparer le cours.",
        "calendar_id": "primary",
    }
    saved = json.loads((tmp_path / "cron/pending_approvals/REV-20261011-1700.json").read_text())
    assert saved["job_id"] == "eefcdf90b2c1"


def test_refuse_is_local_and_never_calls_executor(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    register_calendar_approval(BRIEF, "REV-20261011-1700", job_id="job", account="axel@example.com")
    calls = []

    result = resolve_calendar_approval(
        "REV-20261011-1700", "refuse", executor=lambda *_args, **_kwargs: calls.append(1))

    assert calls == []
    assert result["status"] == "rejected"
    assert "refusée" in result["message"]


def test_authorize_checks_conflicts_creates_and_verifies_event(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    register_calendar_approval(BRIEF, "REV-20261011-1700", job_id="job", account="axel@example.com")
    calls = []

    def executor(tool, payload):
        calls.append((tool, payload))
        if tool == "get_events" and len([c for c in calls if c[0] == "get_events"]) == 1:
            return {"ok": True, "text": "No events found in calendar 'primary'."}
        if tool == "manage_event":
            return {"ok": True, "event_id": "evt-123", "text": "Created event evt-123"}
        return {"ok": True, "event_id": "evt-123", "text": "Event evt-123"}

    result = resolve_calendar_approval("REV-20261011-1700", "authorize", executor=executor)

    assert [tool for tool, _ in calls] == ["get_events", "manage_event", "get_events"]
    assert result["status"] == "approved"
    assert result["event_id"] == "evt-123"
    assert "créé" in result["message"]


def test_authorize_fails_closed_when_conflict_check_is_ambiguous(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    register_calendar_approval(BRIEF, "REV-20261011-1700", job_id="job", account="axel@example.com")

    with pytest.raises(RuntimeError, match="conflit"):
        resolve_calendar_approval(
            "REV-20261011-1700", "authorize",
            executor=lambda *_args, **_kwargs: {"ok": True, "text": "Unexpected response"})

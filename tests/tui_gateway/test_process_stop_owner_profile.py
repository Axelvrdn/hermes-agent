"""``process.stop`` on a backend that serves several profiles stops only the caller's background commands.

One local backend serves every "This device" profile behind a remote-primary Desktop and they share one
process registry. ``/stop`` in one profile used to ``kill_all()`` every profile's commands.
"""

from __future__ import annotations


import tui_gateway.server as server
from tools.process_registry import ProcessRegistry, ProcessSession


def _registry_with(monkeypatch, *homes):
    reg = ProcessRegistry()
    killed = []
    for i, home in enumerate(homes):
        s = ProcessSession(id=f"proc_{i}", command="sleep 600", owner_home=home)
        reg._running[s.id] = s
    monkeypatch.setattr(reg, "kill_process", lambda sid, **kw: killed.append(sid) or {"status": "killed"})
    return reg, killed


def test_owner_homes_limits_the_sweep(monkeypatch):
    reg, killed = _registry_with(monkeypatch, "", "/p/reviewer", "/p/calendar")
    assert reg.kill_all(source="process.stop", owner_homes=frozenset({"/p/reviewer"})) == 1
    assert killed == ["proc_1"]


def test_process_stop_from_one_profile_spares_the_others(monkeypatch, tmp_path):
    launch, reviewer = tmp_path / "launch", tmp_path / "profiles" / "reviewer"
    launch.mkdir()
    reviewer.mkdir(parents=True)
    reg, killed = _registry_with(monkeypatch, "", str(reviewer), str(tmp_path / "profiles" / "calendar"))
    monkeypatch.setattr("tools.process_registry.process_registry", reg)
    monkeypatch.setattr(server, "_hermes_home", launch)
    monkeypatch.setattr(server, "_served_profile_homes", {reviewer})
    monkeypatch.setattr(server, "_profile_home", lambda name: reviewer if name == "reviewer" else None)

    resp = server._methods["process.stop"]("r", {"profile": "reviewer"})
    assert resp["result"]["killed"] == 1 and killed == ["proc_1"]

    killed.clear()
    resp = server._methods["process.stop"]("r", {})   # launch profile: its own (untagged) commands only
    assert killed == ["proc_0"]


def test_single_profile_backend_keeps_stopping_everything(monkeypatch):
    reg, killed = _registry_with(monkeypatch, "", "")
    monkeypatch.setattr("tools.process_registry.process_registry", reg)
    monkeypatch.setattr(server, "_served_profile_homes", set())
    server._methods["process.stop"]("r", {})
    assert sorted(killed) == ["proc_0", "proc_1"]

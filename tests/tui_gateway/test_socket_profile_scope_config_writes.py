"""Off-turn RPCs on a socket that speaks for a profile run inside that profile's home.

``wake.stop {persist: true}`` writes ``wake_word.enabled`` through ``save_config_value`` with no ``profile``
plumbing of its own. On the one local backend that serves every "This device" profile, a named profile's
``/wake off`` used to land in the LAUNCH profile's config.yaml.
"""

from __future__ import annotations

from types import SimpleNamespace

import tui_gateway.server as server
from tui_gateway.transport import bind_transport, reset_transport


def test_wake_stop_persists_into_the_sockets_profile(tmp_path, monkeypatch):
    launch, reviewer = tmp_path / "launch", tmp_path / "launch" / "profiles" / "reviewer"
    reviewer.mkdir(parents=True)
    for home in (launch, reviewer):
        (home / "config.yaml").write_text("wake_word:\n  enabled: true\n", encoding="utf-8")
    monkeypatch.setenv("HERMES_HOME", str(launch))
    monkeypatch.setattr(server, "_hermes_home", launch)
    monkeypatch.setattr(server, "_profile_home", lambda name: reviewer if name == "reviewer" else None)

    token = bind_transport(SimpleNamespace(default_profile="reviewer", write=lambda *_a, **_k: True))
    try:
        resp = server.handle_request(
            {"jsonrpc": "2.0", "id": "w", "method": "wake.stop", "params": {"persist": True}})
    finally:
        reset_transport(token)

    assert resp["result"]["disabled_persisted"] is True
    assert "enabled: false" in (reviewer / "config.yaml").read_text()
    assert "enabled: true" in (launch / "config.yaml").read_text()

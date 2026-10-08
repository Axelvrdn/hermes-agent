"""Server on/off lifecycle route (round-9 feedback: 'we should be able to
completely turn off the local engine'). Contract: stop tears the server
down AND persists enabled=false (durable, unlike eject); start persists
enabled=true and boots."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / ".hermes"))
    from hermes_cli import web_server

    test_client = TestClient(web_server.app)
    token = getattr(web_server, "_SESSION_TOKEN", "")
    if token:
        test_client.headers["Authorization"] = f"Bearer {token}"
    return test_client


def test_stop_disables_and_tears_down(client, monkeypatch):
    stopped = {"called": False}

    def _shutdown():
        stopped["called"] = True

    class _FakeSup:
        pass

    monkeypatch.setattr("hermes_cli.local_runtime.bootstrap.get_supervisor",
                        lambda: _FakeSup())
    monkeypatch.setattr("hermes_cli.local_runtime.bootstrap.shutdown_local_runtime",
                        _shutdown)

    r = client.post("/api/local-models/server", json={"action": "stop"})
    assert r.status_code == 200
    assert stopped["called"] is True

    from hermes_cli.config import load_config

    assert load_config()["local_runtime"]["enabled"] is False


def test_start_enables_and_boots(client, monkeypatch):
    booted = {"called": False}

    class _FakeSup:
        base_url = "http://127.0.0.1:18434/v1"

    def _ensure(config, force=False):
        booted["called"] = True
        assert force is True
        return _FakeSup()

    monkeypatch.setattr("hermes_cli.local_runtime.bootstrap.ensure_local_runtime",
                        _ensure)

    r = client.post("/api/local-models/server", json={"action": "start"})
    assert r.status_code == 200
    assert booted["called"] is True

    from hermes_cli.config import load_config

    assert load_config()["local_runtime"]["enabled"] is True


def test_bogus_action_rejected(client):
    r = client.post("/api/local-models/server", json={"action": "reboot"})
    assert r.status_code == 400


def test_status_reports_loaded_models_from_live_router(client, monkeypatch):
    """Round-11 regression: the loaded-models read inside the status route
    raised NameError (missing json import), the blanket except swallowed it,
    and {} shipped as truth — 'Not in memory' on a machine with 30 GB of
    VRAM in use. This test exercises the REAL route against a stub router
    and demands the loaded set comes through."""
    import http.server
    import json as _json
    import threading

    class _Router(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = _json.dumps({"data": [
                {"id": "m-loaded", "status": {"value": "loaded"}},
                {"id": "m-loading", "status": {"value": "loading"}},
                {"id": "m-cold", "status": {"value": "unloaded"}},
            ]}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), _Router)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        port = server.server_address[1]
        # Patch the ROUTE's binding: local_models binds _state_endpoint via
        # from-import at module load, so patching the endpoint module's
        # attribute never reaches the name the route actually calls.
        monkeypatch.setattr(
            "hermes_cli.web_routers.local_models._state_endpoint",
            lambda: {"base_url": f"http://127.0.0.1:{port}/v1", "api_key": "k"})
        payload = client.get("/api/local-models/status").json()
        assert payload["server_running"] is True
        assert payload["loaded_models"] == {"m-loaded": "loaded", "m-loading": "loading"}
    finally:
        server.shutdown()


@pytest.mark.parametrize("refuse", [False, True])
def test_stop_forwards_recovery_and_preserves_conflict(client, tmp_path, monkeypatch, refuse):
    from fastapi import HTTPException
    from hermes_cli.web_routers import local_models
    from hermes_cli.local_runtime import supervisor

    monkeypatch.setattr(supervisor, "runtimes_root", lambda: tmp_path)
    supervisor.state_path().write_text("{}")
    monkeypatch.setattr(local_models.bootstrap, "get_supervisor", lambda: None)
    monkeypatch.setattr(local_models, "_state_endpoint", lambda: None)
    called, disabled = [], []
    def recover():
        called.append(True)
        if refuse:
            raise HTTPException(409, "Another Hermes process owns this server, or its ownership could not be verified")
    monkeypatch.setattr(local_models, "_terminate_state_pid", recover)
    monkeypatch.setattr(local_models, "_set_runtime_enabled", lambda value: disabled.append(value))
    response = client.post("/api/local-models/server", json={"action": "stop"})
    assert response.status_code == (409 if refuse else 200), response.text
    assert called == [True]
    assert disabled == ([] if refuse else [False])


def test_stop_for_a_named_profile_writes_that_profiles_config(client, tmp_path, monkeypatch):
    """One backend serves every "This device" profile: a named profile's Stop must flip ITS
    ``local_runtime.enabled``, never the launch profile's."""
    reviewer = tmp_path / ".hermes" / "profiles" / "reviewer"
    reviewer.mkdir(parents=True)
    (reviewer / "config.yaml").write_text("local_runtime:\n  enabled: true\n", encoding="utf-8")
    (tmp_path / ".hermes" / "config.yaml").write_text("local_runtime:\n  enabled: true\n", encoding="utf-8")
    monkeypatch.setattr("hermes_cli.local_runtime.bootstrap.get_supervisor", lambda: object())
    monkeypatch.setattr("hermes_cli.local_runtime.bootstrap.shutdown_local_runtime", lambda: None)

    r = client.post("/api/local-models/server?profile=reviewer", json={"action": "stop"})
    assert r.status_code == 200

    assert "enabled: false" in (reviewer / "config.yaml").read_text()
    assert "enabled: true" in (tmp_path / ".hermes" / "config.yaml").read_text()


def test_server_toggle_enters_the_profile_scope_off_the_event_loop(client, monkeypatch):
    """Scope entry can fetch external secrets; on the event loop one profile's click stalls every
    profile's HTTP and WebSocket traffic."""
    import asyncio
    import contextlib

    from hermes_cli.web_routers import local_models

    entered = []

    @contextlib.contextmanager
    def _scope(profile):
        try:
            asyncio.get_running_loop()
            entered.append("event-loop")
        except RuntimeError:
            entered.append("worker")
        yield

    monkeypatch.setattr("hermes_cli.web_routers._common._config_profile_scope", _scope)
    monkeypatch.setitem(local_models._SERVER_ACTIONS, "stop", lambda: None)
    assert client.post("/api/local-models/server?profile=reviewer", json={"action": "stop"}).status_code == 200
    assert entered == ["worker"]


def test_download_never_binds_the_requesting_profile(client, monkeypatch):
    """The post-download rescan restarts the SHARED server: it must keep the launch settings, not swap in
    the downloading profile's engine choice (and stop a server other profiles are using)."""
    from hermes_cli.web_routers import local_models

    entered = []
    monkeypatch.setattr(local_models, "_config_profile_scope", lambda p: entered.append(p))
    monkeypatch.setattr(local_models, "_download_target",
                        lambda model_id: (type("E", (), {"display_name": "M", "id": "m"})(),
                                          type("V", (), {"model_id": "m-q4", "quant": "Q4"})()))
    monkeypatch.setattr(local_models, "_download_plan", lambda entry, variant: [])
    r = client.post("/api/local-models/download?profile=reviewer", json={"model_id": "m"})
    assert r.status_code == 200 and entered == []

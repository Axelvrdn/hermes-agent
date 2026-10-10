"""Voicebox plugin contract against an entirely local deterministic HTTP fake."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from plugins.voicebox import discover, synthesize, register


@pytest.fixture
def service(monkeypatch, tmp_path):
    class Fake(BaseHTTPRequestHandler):
        requests = []
        oversized = False
        pending = False
        def log_message(self, *_): pass
        def _reply(self, status, body, content_type="application/json"):
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        def do_GET(self):
            self.requests.append(("GET", self.path))
            if self.path == "/health": self._reply(200, {"status": "ok", "model_loaded": False})
            elif self.path == "/profiles": self._reply(200, [{"id": "reviewed", "name": "Approved voice", "default_engine": "kokoro"}, {"id": "other", "name": "Other"}])
            elif self.path == "/models/status": self._reply(200, {"models": []})
            elif self.path == "/history/job": self._reply(200, {"status": "pending" if Fake.pending else "completed"})
            elif self.path == "/audio/job": self._reply(200, b"RIFF" + b"\0" * (2048 if Fake.oversized else 24), "audio/wav")
            elif self.path == "/audio/huge": self._reply(200, b"RIFF" + b"\0" * 100, "audio/wav")
            else: self._reply(404, {})
        def do_POST(self):
            self.requests.append(("POST", self.path, json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
            self._reply(200, {"id": "job", "status": "completed"})
    server = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("VOICEBOX_URL", f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setenv("VOICEBOX_REVIEWED_PROFILES", "reviewed")
    monkeypatch.setenv("VOICEBOX_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    yield Fake, tmp_path
    server.shutdown()
    server.server_close()
    thread.join()


def test_discover_service_and_reviewed_voices(service):
    fake, _ = service
    result = discover({})
    assert result["available"] is True
    assert result["health"]["status"] == "ok"
    assert result["profiles"] == [{"id": "reviewed", "name": "Approved voice", "default_engine": "kokoro"}]
    assert result["models"] == {"models": []}


def test_synthesis_writes_wav_and_returns_explicit_native_media_tag(service):
    fake, root = service
    result = synthesize({"text": "Bonjour", "profile_id": "reviewed", "language": "fr"})
    assert result["success"] is True
    assert result["media"] == f"MEDIA:{result['file_path']}"
    assert Path(result["file_path"]).read_bytes().startswith(b"RIFF")
    assert Path(result["file_path"]).is_relative_to(root)
    assert ("POST", "/generate", {"text": "Bonjour", "profile_id": "reviewed", "language": "fr", "engine": "kokoro", "normalize": True}) in fake.requests


def test_unreviewed_profile_rejected_before_generation(service):
    fake, _ = service
    assert "error" in synthesize({"text": "Bonjour", "profile_id": "other"})
    assert not any(req[0] == "POST" for req in fake.requests)


def test_output_escape_and_text_limit_rejected(service, monkeypatch):
    fake, root = service
    monkeypatch.setenv("VOICEBOX_OUTPUT_ROOT", str(root / "allowed"))
    assert "error" in synthesize({"text": "ok", "profile_id": "reviewed", "output_path": str(root / "outside.wav")})
    assert "error" in synthesize({"text": "x" * 4001, "profile_id": "reviewed"})
    assert not any(req[0] == "POST" for req in fake.requests)


def test_unconfigured_service_is_gated(monkeypatch):
    monkeypatch.delenv("VOICEBOX_URL", raising=False)
    assert discover({})["available"] is False
    assert "error" in synthesize({"text": "hello", "profile_id": "reviewed"})


def test_oversized_audio_does_not_leave_file(service, monkeypatch):
    fake, root = service
    fake.oversized = True
    monkeypatch.setenv("VOICEBOX_MAX_BYTES", "1024")
    destination = root / "large.wav"
    assert "error" in synthesize({"text": "hello", "profile_id": "reviewed", "output_path": str(destination)})
    assert not destination.exists()


def test_pending_generation_respects_deadline(service, monkeypatch):
    fake, _ = service
    fake.pending = True
    monkeypatch.setenv("VOICEBOX_TIMEOUT", "1")
    assert "timed out" in synthesize({"text": "hello", "profile_id": "reviewed"})["error"]


def test_plugin_registers_narrow_tools():
    class Context:
        def __init__(self): self.tools = []
        def register_tool(self, **kwargs): self.tools.append(kwargs)
    ctx = Context()
    register(ctx)
    assert [tool["name"] for tool in ctx.tools] == ["voicebox_discover", "voicebox_synthesize"]

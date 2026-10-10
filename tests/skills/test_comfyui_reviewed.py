"""Issue #6: local ComfyUI reviewed-template boundary, using an in-process fake service."""
import hashlib
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "optional-skills" / "creative" / "comfyui" / "scripts"))
from reviewed_local import ComfyLocal, Rejected


@pytest.fixture
def service():
    class Handler(BaseHTTPRequestHandler):
        requests = []
        history = {}
        queue = {"queue_running": [], "queue_pending": []}

        def log_message(self, *_):
            pass

        def _reply(self, data, content_type="application/json"):
            body = json.dumps(data).encode() if content_type == "application/json" else data
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self.requests.append(("GET", self.path, None))
            path = self.path.split("?")[0]
            if path == "/object_info":
                return self._reply({"KSampler": {"input": {}}, "SaveImage": {"input": {}}})
            if path == "/system_stats":
                return self._reply({"system": {"comfyui_version": "test"}})
            if path == "/queue":
                return self._reply(self.queue)
            if path.startswith("/history/"):
                return self._reply(self.history)
            if path == "/view":
                return self._reply(b"\x89PNG\r\n\x1a\nFAKE", "image/png")
            self.send_error(404)

        def do_POST(self):
            size = int(self.headers["Content-Length"])
            body = json.loads(self.rfile.read(size))
            self.requests.append(("POST", self.path, body))
            if self.path == "/prompt":
                return self._reply({"prompt_id": "job-1", "number": 1})
            if self.path in ("/queue", "/interrupt"):
                return self._reply({})
            self.send_error(404)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, Handler
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


@pytest.fixture
def setup(tmp_path, service):
    server, handler = service
    workflow = {"1": {"class_type": "KSampler", "inputs": {"seed": 42, "steps": 20}},
                "2": {"class_type": "SaveImage", "inputs": {"filename_prefix": "test", "images": ["1", 0]}}}
    template = tmp_path / "reviewed.json"
    template.write_text(json.dumps(workflow), encoding="utf-8")
    manifest = tmp_path / "templates.json"
    manifest.write_text(json.dumps({"text-image": {"file": "reviewed.json", "sha256": hashlib.sha256(template.read_bytes()).hexdigest(),
                                                   "parameters": {"seed": {"node": "1", "input": "seed", "type": "integer", "min": 0, "max": 999}}}}))
    client = ComfyLocal(f"http://127.0.0.1:{server.server_port}", manifest, tmp_path / "media", media_roots=[tmp_path / "media"])
    return client, template, handler


def test_submit_only_reviewed_template_with_constrained_parameters(setup):
    client, _, handler = setup
    result = client.submit("text-image", {"seed": 7})
    assert result["prompt_id"] == "job-1"
    assert handler.requests[-1][2]["prompt"]["1"]["inputs"]["seed"] == 7
    assert handler.requests[-1][2]["prompt"]["2"]["inputs"]["filename_prefix"] == "test"
    assert client.status("job-1")["state"] == "pending"


def test_rejects_unknown_template_param_tamper_and_path_escape_without_submission(setup):
    client, template, handler = setup
    for name, args in [("not-reviewed", {}), ("text-image", {"graph": {}}), ("text-image", {"seed": 1000})]:
        with pytest.raises(Rejected):
            client.submit(name, args)
    template.write_text('{}')
    with pytest.raises(Rejected):
        client.submit("text-image", {})
    assert not any(path == "/prompt" for _, path, _ in handler.requests)


def test_inventory_and_job_scoped_cancel(setup):
    client, _, handler = setup
    inventory = client.inventory()
    assert "KSampler" in inventory["custom_nodes"]
    assert inventory["websocket"].endswith("/ws?clientId=") is False
    assert inventory["output_root"] == str(client.output_root.resolve())
    with pytest.raises(Rejected):
        client.cancel("foreign")
    client.submit("text-image", {})
    handler.queue["queue_pending"] = [[1, "job-1", {}]]
    assert client.cancel("job-1")["state"] == "cancel_requested"
    assert handler.requests[-1] == ("POST", "/queue", {"delete": ["job-1"]})
    handler.queue["queue_pending"] = []
    handler.queue["queue_running"] = [[1, "job-1", {}]]
    client.cancel("job-1")
    assert handler.requests[-1] == ("POST", "/interrupt", {})


def test_collect_only_own_completed_output_and_safe_media(setup):
    client, _, handler = setup
    client.submit("text-image", {})
    handler.history["job-1"] = {"status": {"completed": True, "status_str": "success"},
        "outputs": {"2": {"images": [{"filename": "image.png", "subfolder": "sub", "type": "output"}]}}}
    result = client.collect("job-1")
    assert result["state"] == "completed"
    assert Path(result["artifacts"][0]).read_bytes().startswith(b"\x89PNG")
    assert Path(result["artifacts"][0]).is_relative_to(client.output_root)
    assert "MEDIA:" + result["artifacts"][0] in result["discord_message"]
    handler.history["job-1"]["outputs"]["2"]["images"][0]["filename"] = "../../.env"
    with pytest.raises(Rejected):
        client.collect("job-1")
    with pytest.raises(Rejected):
        client.collect("foreign")


def test_rejects_server_supplied_symlink_escape(setup, tmp_path):
    client, _, handler = setup
    client.submit("text-image", {})
    (client.output_root / "job-1").mkdir(parents=True)
    (client.output_root / "job-1" / "escape").symlink_to(tmp_path, target_is_directory=True)
    handler.history["job-1"] = {"status": {"completed": True}, "outputs": {"2": {"images": [
        {"filename": "stolen.png", "subfolder": "escape", "type": "output"}]}}}
    with pytest.raises(Rejected):
        client.collect("job-1")
    assert not (tmp_path / "stolen.png").exists()


def test_rejects_output_root_outside_configured_media_roots(setup, tmp_path):
    client, _, _ = setup
    with pytest.raises(Rejected):
        ComfyLocal(client.host, client.manifest, tmp_path / "elsewhere", media_roots=[tmp_path / "media"])
    allowed = ComfyLocal(client.host, client.manifest, tmp_path / "media" / "runs", media_roots=[tmp_path / "media"])
    assert allowed.output_root.is_relative_to(tmp_path / "media")


def test_rejects_cross_origin_redirect_and_non_http_host(setup):
    client, _, _ = setup
    with pytest.raises(Rejected):
        ComfyLocal("https://example.com", client.manifest, client.output_root)
    with pytest.raises(Rejected):
        ComfyLocal("http://user:pass@localhost:8188", client.manifest, client.output_root)


def test_refuses_global_interrupt_when_another_job_runs(setup):
    client, _, handler = setup
    client.submit("text-image", {})
    handler.queue["queue_running"] = [[1, "job-1", {}], [2, "foreign", {}]]
    with pytest.raises(Rejected):
        client.cancel("job-1")
    assert not any(path == "/interrupt" for _, path, _ in handler.requests)


def test_cli_inventory_and_submit_against_fake_service(setup, capsys, monkeypatch):
    from reviewed_local import main
    client, _, _ = setup
    monkeypatch.setenv("HERMES_MEDIA_ALLOW_DIRS", str(client.output_root))
    assert main(["--host", client.host, "--manifest", str(client.manifest), "--output-root", str(client.output_root),
                 "inventory"]) == 0
    assert "KSampler" in capsys.readouterr().out
    assert main(["--host", client.host, "--manifest", str(client.manifest), "--output-root", str(client.output_root),
                 "submit", "text-image", "--params", '{"seed": 9}']) == 0
    assert json.loads(capsys.readouterr().out)["prompt_id"] == "job-1"


def test_cli_run_polls_and_collects_to_media(setup, capsys, monkeypatch):
    from reviewed_local import main
    client, _, handler = setup
    monkeypatch.setenv("HERMES_MEDIA_ALLOW_DIRS", str(client.output_root))
    handler.history["job-1"] = {"status": {"completed": True, "status_str": "success"},
        "outputs": {"2": {"images": [{"filename": "done.png", "subfolder": "", "type": "output"}]}}}
    assert main(["--host", client.host, "--manifest", str(client.manifest), "--output-root", str(client.output_root),
                 "run", "text-image", "--params", "{}", "--timeout", "1"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert Path(result["artifacts"][0]).exists()


def test_bundled_reviewed_manifest_resolves_pinned_workflow():
    root = Path(__file__).resolve().parents[2] / "optional-skills" / "creative" / "comfyui"
    manifest = root / "reviewed-templates.json"
    client = object.__new__(ComfyLocal)
    client.manifest = manifest
    graph = client._template("sd15-image", {"prompt": "winter mountains", "steps": 6})
    assert graph["6"]["inputs"]["text"] == "winter mountains"
    assert graph["3"]["inputs"]["steps"] == 6


def test_ws_filters_other_jobs_and_reports_progress(setup):
    client, _, _ = setup
    client.submit("text-image", {})
    messages = [json.dumps({"type": "progress", "data": {"prompt_id": "foreign", "value": 9, "max": 10}}),
                json.dumps({"type": "progress", "data": {"prompt_id": "job-1", "value": 2, "max": 10}}),
                json.dumps({"type": "execution_success", "data": {"prompt_id": "job-1"}})]
    assert list(client.progress("job-1", messages)) == [{"type": "progress", "value": 2, "max": 10}, {"type": "execution_success"}]

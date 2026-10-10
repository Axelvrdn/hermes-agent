"""Restricted local ComfyUI API client. Only pinned operator-reviewed graphs can run.

No imports from the general-purpose run_workflow.py: that script deliberately accepts
arbitrary workflows and is not a safe gateway for unattended generation.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path


class Rejected(ValueError):
    """Unreviewed or unsafe request; never submit it to ComfyUI."""


class ComfyLocal:
    def __init__(self, host: str, manifest: Path, output_root: Path, *, media_roots=None):
        parsed = urllib.parse.urlsplit(host)
        if parsed.scheme != "http" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
            raise Rejected("Expected a local HTTP ComfyUI origin")
        self.host = host.rstrip("/")
        self.manifest = Path(manifest)
        self.output_root = Path(output_root).resolve()
        if media_roots is None:
            from hermes_constants import get_hermes_home
            media_roots = [get_hermes_home() / "cache" / "images", get_hermes_home() / "cache" / "videos",
                           get_hermes_home() / "cache" / "audio"]
            from gateway.media_policy import media_delivery_allow_dirs
            import os
            media_roots.extend(Path(p.strip()) for p in media_delivery_allow_dirs().replace(",", os.pathsep).split(os.pathsep) if p.strip())
        if not any(self.output_root.is_relative_to(Path(root).resolve()) for root in media_roots):
            raise Rejected("Output root must be under a configured media-delivery allowlist")
        self.client_id = str(uuid.uuid4())
        self.jobs: set[str] = set()

    def _request(self, path: str, body: dict | None = None, *, binary: bool = False):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.host + path, data=data, headers={"Content-Type": "application/json"} if data else {}, method="POST" if data is not None else "GET")
        # Do not follow redirects (including redirects to unrelated hosts).
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        opener = urllib.request.build_opener(NoRedirect)
        with opener.open(req, timeout=15) as response:
            raw = response.read(25 * 1024 * 1024 if binary else 2 * 1024 * 1024 + 1)
            if len(raw) > (25 * 1024 * 1024 if binary else 2 * 1024 * 1024):
                raise Rejected("Response too large")
            if binary:
                return raw
            return json.loads(raw)

    def _template(self, name: str, params: dict) -> dict:
        if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", name) or not isinstance(params, dict):
            raise Rejected("Invalid template or parameters")
        manifest = json.loads(self.manifest.read_text(encoding="utf-8-sig"))
        spec = manifest.get(name)
        if not isinstance(spec, dict):
            raise Rejected("Template not reviewed")
        filename = spec.get("file")
        if not isinstance(filename, str) or not filename or Path(filename).is_absolute() or any(part in (".", "..") for part in Path(filename).parts):
            raise Rejected("Invalid template path")
        template = (self.manifest.parent / filename).resolve(strict=True)
        if not template.is_relative_to(self.manifest.parent.resolve()) or not template.is_file():
            raise Rejected("Template outside reviewed directory")
        data = template.read_bytes()
        if hashlib.sha256(data).hexdigest() != spec.get("sha256"):
            raise Rejected("Template modified since review")
        graph = json.loads(data.decode("utf-8-sig"))
        if isinstance(graph, dict):
            graph.pop("_comment", None)
        if not isinstance(graph, dict) or not graph or any(not isinstance(n, dict) or not isinstance(n.get("class_type"), str) or not isinstance(n.get("inputs"), dict) for n in graph.values()):
            raise Rejected("Expected API-format graph")
        fields = spec.get("parameters", {})
        if not isinstance(fields, dict) or params.keys() - fields.keys():
            raise Rejected("Unknown parameter")
        graph = copy.deepcopy(graph)
        for key, value in params.items():
            field = fields[key]
            if not isinstance(field, dict) or field.get("type") not in ("integer", "text"):
                raise Rejected("Invalid parameter contract")
            if field["type"] == "integer":
                if type(value) is not int or not isinstance(field.get("min"), int) or not isinstance(field.get("max"), int) or not field["min"] <= value <= field["max"]:
                    raise Rejected("Integer outside reviewed range")
            elif not isinstance(value, str) or not value or len(value) > min(field.get("max_length", 2000), 2000):
                raise Rejected("Invalid text parameter")
            node = graph.get(str(field.get("node")))
            if not isinstance(node, dict) or field.get("input") not in node["inputs"] or isinstance(node["inputs"][field["input"]], (dict, list)):
                raise Rejected("Parameter target not reviewed")
            node["inputs"][field["input"]] = value
        return graph

    def inventory(self) -> dict:
        info = self._request("/object_info")
        return {"system": self._request("/system_stats"), "custom_nodes": sorted(info),
                "templates": sorted(json.loads(self.manifest.read_text(encoding="utf-8-sig"))),
                "websocket": self.host.replace("http://", "ws://", 1) + "/ws?clientId=" + self.client_id,
                "output_root": str(self.output_root)}

    def submit(self, name: str, params: dict) -> dict:
        graph = self._template(name, params)
        response = self._request("/prompt", {"prompt": graph, "client_id": self.client_id})
        job = response.get("prompt_id")
        if not isinstance(job, str) or not job:
            raise Rejected("Server did not return a prompt_id")
        self.jobs.add(job)
        return {"prompt_id": job, "template": name}

    def _owned(self, job: str):
        if not isinstance(job, str) or job not in self.jobs:
            raise Rejected("Job not submitted by this client")

    def status(self, job: str) -> dict:
        self._owned(job)
        history = self._request("/history/" + urllib.parse.quote(job, safe=""))
        entry = history.get(job)
        if entry:
            status = entry.get("status", {})
            return {"state": "error" if status.get("status_str") == "error" else "completed" if status.get("completed") else "pending", "prompt_id": job}
        queue = self._request("/queue")
        if any(item[1] == job for item in queue.get("queue_running", []) if isinstance(item, list) and len(item) > 1):
            return {"state": "running", "prompt_id": job}
        return {"state": "pending", "prompt_id": job}

    def cancel(self, job: str) -> dict:
        self._owned(job)
        queue = self._request("/queue")
        if any(item[1] == job for item in queue.get("queue_pending", []) if isinstance(item, list) and len(item) > 1):
            self._request("/queue", {"delete": [job]})
        elif any(item[1] == job for item in queue.get("queue_running", []) if isinstance(item, list) and len(item) > 1):
            # /interrupt is global; refuse while any unrelated job is running.
            if len(queue["queue_running"]) != 1:
                raise Rejected("Cannot interrupt a shared running queue")
            self._request("/interrupt", {})
        else:
            raise Rejected("Job is not queued or running")
        return {"state": "cancel_requested", "prompt_id": job}

    def progress(self, job: str, messages):
        """Filter decoded /ws text frames by prompt_id; caller owns WS transport."""
        self._owned(job)
        for raw in messages:
            if isinstance(raw, bytes):
                continue
            event = json.loads(raw)
            data = event.get("data", {})
            if data.get("prompt_id") != job:
                continue
            kind = event.get("type")
            if kind == "progress":
                yield {"type": kind, "value": data.get("value"), "max": data.get("max")}
            elif kind in ("execution_success", "execution_error", "execution_interrupted"):
                yield {"type": kind}
                return

    def collect(self, job: str) -> dict:
        self._owned(job)
        history = self._request("/history/" + urllib.parse.quote(job, safe=""))
        entry = history.get(job, {})
        status = entry.get("status", {})
        if not status.get("completed") or status.get("status_str") == "error":
            raise Rejected("Job is not successfully completed")
        outputs = entry.get("outputs", {})
        artifacts = []
        for node in outputs.values():
            for kind in ("images", "gifs", "videos", "audio"):
                for item in node.get(kind, []):
                    name, sub = item.get("filename"), item.get("subfolder", "")
                    if not isinstance(name, str) or not isinstance(sub, str) or item.get("type") != "output":
                        raise Rejected("Unsafe output descriptor")
                    target = (self.output_root / job / sub / name).resolve()
                    if target == self.output_root or not target.is_relative_to(self.output_root / job) or not re.fullmatch(r"[\w. -]+", name) or name in (".", ".."):
                        raise Rejected("Output path escapes media root")
                    query = urllib.parse.urlencode({"filename": name, "subfolder": sub, "type": "output"})
                    content = self._request("/view?" + query, binary=True)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(content)
                    artifacts.append(str(target))
        return {"state": "completed", "prompt_id": job, "artifacts": artifacts,
                "discord_message": "\n".join("MEDIA:" + path for path in artifacts)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run operator-reviewed local ComfyUI templates")
    parser.add_argument("--host", required=True, help="HTTP origin of the local server")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("inventory")
    submit = commands.add_parser("submit")
    submit.add_argument("template")
    submit.add_argument("--params", default="{}")
    run = commands.add_parser("run")
    run.add_argument("template")
    run.add_argument("--params", default="{}")
    run.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args(argv)
    client = ComfyLocal(args.host, args.manifest, args.output_root)
    if args.command == "inventory":
        result = client.inventory()
    else:
        result = client.submit(args.template, json.loads(args.params))
        if args.command == "run":
            if not 1 <= args.timeout <= 3600:
                raise Rejected("Timeout must be 1–3600 seconds")
            deadline = time.monotonic() + args.timeout
            while time.monotonic() < deadline:
                state = client.status(result["prompt_id"])["state"]
                if state == "completed":
                    result = client.collect(result["prompt_id"])
                    break
                if state == "error":
                    raise Rejected("ComfyUI job failed")
                time.sleep(min(1, max(0, deadline - time.monotonic())))
            else:
                raise Rejected("ComfyUI job timed out; job may still be running")
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

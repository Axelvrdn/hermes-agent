"""Opt-in Voicebox connector. No network access unless VOICEBOX_URL is configured."""
from __future__ import annotations

import os
import re
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from hermes_constants import get_hermes_home


def _settings():
    url = os.getenv("VOICEBOX_URL", "").rstrip("/")
    parsed = urlsplit(url)
    if not url or parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
        raise ValueError("Configure VOICEBOX_URL as an HTTP(S) origin first")
    reviewed = {item.strip() for item in os.getenv("VOICEBOX_REVIEWED_PROFILES", "").split(",") if item.strip()}
    root = Path(os.getenv("VOICEBOX_OUTPUT_ROOT") or get_hermes_home() / "media" / "voicebox").expanduser().resolve()
    timeout = min(max(float(os.getenv("VOICEBOX_TIMEOUT", "120")), 1), 300)
    max_bytes = min(max(int(os.getenv("VOICEBOX_MAX_BYTES", "8388608")), 1024), 25000000)
    return url, reviewed, root, timeout, max_bytes


def _fetch(client, endpoint):
    response = client.get(endpoint)
    response.raise_for_status()
    return response.json()


def discover(args: dict, **_kwargs):
    """Read service status, installed models and reviewed voice profiles."""
    try:
        url, reviewed, _, timeout, _ = _settings()
        with httpx.Client(base_url=url, timeout=min(timeout, 10), follow_redirects=False) as client:
            health = _fetch(client, "/health")
            profiles = _fetch(client, "/profiles")
            models = _fetch(client, "/models/status")
        if not isinstance(profiles, list):
            raise ValueError("Invalid profiles response")
        return {"available": True, "health": health, "models": models,
                "profiles": [{"id": p["id"], "name": p.get("name"), "default_engine": p.get("default_engine")}
                             for p in profiles if isinstance(p, dict) and p.get("id") in reviewed]}
    except (ValueError, OSError, httpx.HTTPError, KeyError, TypeError) as exc:
        return {"available": False, "error": str(exc)}


def synthesize(args: dict, **_kwargs):
    """Generate with a pre-approved profile; return a native MEDIA: WAV attachment."""
    try:
        url, reviewed, root, timeout, max_bytes = _settings()
        text = args.get("text")
        profile_id = args.get("profile_id")
        if not isinstance(text, str) or not text.strip() or len(text) > 4000:
            raise ValueError("Text must contain 1-4000 characters")
        if not isinstance(profile_id, str) or profile_id not in reviewed:
            raise ValueError("Profile is not reviewed; add it to VOICEBOX_REVIEWED_PROFILES")
        language = args.get("language", "en")
        if not isinstance(language, str) or not re.fullmatch(r"[a-z]{2}", language):
            raise ValueError("Invalid language")
        destination = Path(args.get("output_path") or root / f"voicebox-{uuid.uuid4().hex}.wav").expanduser().resolve()
        if not destination.is_relative_to(root) or destination.suffix.lower() != ".wav" or destination.exists():
            raise ValueError("Output must be a new WAV inside VOICEBOX_OUTPUT_ROOT")
        # Resolve profile from the server, not an untrusted caller-supplied engine.
        with httpx.Client(base_url=url, timeout=min(timeout, 10), follow_redirects=False) as client:
            profiles = _fetch(client, "/profiles")
            profile = next((p for p in profiles if isinstance(p, dict) and p.get("id") == profile_id), None)
            if not profile:
                raise ValueError("Reviewed profile not found on service")
            engine = profile.get("default_engine")
            if not isinstance(engine, str) or not re.fullmatch(r"[a-z_]+", engine):
                raise ValueError("Reviewed profile has no valid default engine")
            response = client.post("/generate", json={"text": text, "profile_id": profile_id,
                            "language": language, "engine": engine, "normalize": True})
            response.raise_for_status()
            job = response.json().get("id")
            if not isinstance(job, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", job):
                raise ValueError("Invalid generation ID")
            deadline = time.monotonic() + timeout
            while True:
                status = _fetch(client, f"/history/{job}")
                if status.get("status") == "completed":
                    break
                if status.get("status") in {"failed", "cancelled"}:
                    raise ValueError("Voicebox generation failed or was cancelled")
                if time.monotonic() >= deadline:
                    raise TimeoutError("Voicebox generation timed out")
                time.sleep(min(0.5, max(0, deadline - time.monotonic())))
            with client.stream("GET", f"/audio/{job}") as audio:
                audio.raise_for_status()
                if audio.headers.get("content-type", "").split(";")[0].lower() not in {"audio/wav", "audio/x-wav", "audio/wave"}:
                    raise ValueError("Voicebox did not return WAV audio")
                if int(audio.headers.get("content-length", "0")) > max_bytes:
                    raise ValueError("Audio exceeds configured byte limit")
                root.mkdir(parents=True, exist_ok=True)
                # Exclusive creation, cleanup on all transfer errors. Never overwrite an existing artifact.
                try:
                    with destination.open("xb") as output:
                        size = 0
                        for chunk in audio.iter_bytes():
                            size += len(chunk)
                            if size > max_bytes:
                                raise ValueError("Audio exceeds configured byte limit")
                            output.write(chunk)
                    if size < 12 or destination.open("rb").read(4) != b"RIFF":
                        raise ValueError("Invalid WAV audio")
                except BaseException:
                    destination.unlink(missing_ok=True)
                    raise
        return {"success": True, "file_path": str(destination), "media": f"MEDIA:{destination}",
                "delivery": "Include the MEDIA: tag in the final response for native Discord audio upload."}
    except (ValueError, TimeoutError, OSError, httpx.HTTPError, KeyError, TypeError) as exc:
        return {"error": str(exc)}


def register(ctx):
    ctx.register_tool(name="voicebox_discover", toolset="voicebox", handler=discover, emoji="🎙️",
        schema={"name": "voicebox_discover", "description": "Check configured Voicebox health, installed models and reviewed voices (no synthesis).",
                "parameters": {"type": "object", "properties": {}}})
    ctx.register_tool(name="voicebox_synthesize", toolset="voicebox", handler=synthesize, emoji="🔊",
        schema={"name": "voicebox_synthesize", "description": "Synthesize WAV using a reviewed Voicebox profile. Include returned MEDIA: tag in reply for native Discord audio.",
                "parameters": {"type": "object", "properties": {
                    "text": {"type": "string", "maxLength": 4000}, "profile_id": {"type": "string"},
                    "language": {"type": "string"}, "output_path": {"type": "string"}},
                    "required": ["text", "profile_id"]}})

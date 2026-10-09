"""Deterministic persistence and resolution of Discord cron calendar approvals."""

from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from hermes_constants import get_hermes_home

_APPROVAL_ID_RE = re.compile(r"^REV-(\d{8})-(\d{4})$")
_FIELD_RE = re.compile(r"^\s*-\s*(?:\*\*)?([^:*]+?)(?:\*\*)?\s*:\s*(.+?)\s*$")
_TIME_RE = re.compile(r"\b(\d{1,2})\s*h\s*(\d{2})\b", re.IGNORECASE)
_EVENT_ID_RE = re.compile(r"(?:event[_ ]?id|id)[\"'`:\s=]+([A-Za-z0-9_-]{4,})", re.IGNORECASE)
Executor = Callable[[str, dict[str, Any]], dict[str, Any]]


def _store_dir() -> Path:
    return get_hermes_home() / "cron" / "pending_approvals"


def _record_path(approval_id: str) -> Path:
    if not _APPROVAL_ID_RE.fullmatch(approval_id):
        raise ValueError(f"Invalid calendar approval ID: {approval_id}")
    return _store_dir() / f"{approval_id}.json"


def _clean_value(value: str) -> str:
    value = value.strip()
    if value.startswith("`") and value.endswith("`") and len(value) >= 2:
        value = value[1:-1]
    return value.strip().replace("**", "")


def _fields(content: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in content.splitlines():
        match = _FIELD_RE.match(line.replace("**", ""))
        if match:
            result[match.group(1).strip().lower()] = _clean_value(match.group(2))
    return result


def _configured_account() -> str:
    try:
        from hermes_cli.config import load_config_readonly
        cfg = load_config_readonly() or {}
        approval = ((cfg.get("cron") or {}).get("calendar_approval") or {})
        return str(approval.get("google_account") or "").strip()
    except Exception:
        return ""


def _event_from_brief(content: str, approval_id: str) -> dict[str, str]:
    match = _APPROVAL_ID_RE.fullmatch(approval_id)
    if not match:
        raise ValueError(f"Invalid calendar approval ID: {approval_id}")
    values = _fields(content)
    title = values.get("titre", "").strip()
    end_text = values.get("fin", "")
    end_match = _TIME_RE.search(end_text)
    if not title or not end_match:
        raise ValueError("Calendar request is missing a deterministic title or end time")
    start_naive = datetime.strptime("".join(match.groups()), "%Y%m%d%H%M")
    zone = ZoneInfo("Europe/Paris")
    start = start_naive.replace(tzinfo=zone)
    end = start.replace(hour=int(end_match.group(1)), minute=int(end_match.group(2)))
    if end <= start:
        end += timedelta(days=1)
    return {
        "summary": title,
        "start_time": start.isoformat(),
        "end_time": end.isoformat(),
        "timezone": "Europe/Paris",
        "description": values.get("motif", "").strip(),
        "calendar_id": "primary",
    }


def _write_record(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)


def register_calendar_approval(
    content: str, approval_id: str, *, job_id: str, execution_id: str = "",
    account: str | None = None,
) -> dict[str, Any]:
    """Parse a typed calendar block and persist it for a later button decision."""
    path = _record_path(approval_id)
    now = datetime.now().astimezone().isoformat()
    record = {
        "version": 1,
        "approval_id": approval_id,
        "job_id": str(job_id),
        "execution_id": str(execution_id or ""),
        "account": str(account or _configured_account()),
        "status": "pending",
        "created_at": now,
        "updated_at": now,
        "event": _event_from_brief(content, approval_id),
    }
    _write_record(path, record)
    return record


def _extract_text(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, dict):
        texts = []
        for key, value in payload.items():
            if key in {"text", "result", "message"} and isinstance(value, str):
                texts.append(value)
            else:
                nested = _extract_text(value)
                if nested:
                    texts.append(nested)
        return "\n".join(texts)
    if isinstance(payload, list):
        return "\n".join(filter(None, (_extract_text(item) for item in payload)))
    return ""


def _find_event_id(payload: Any) -> str:
    if isinstance(payload, dict):
        for key in ("event_id", "eventId", "id"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        for value in payload.values():
            found = _find_event_id(value)
            if found:
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = _find_event_id(value)
            if found:
                return found
    text = _extract_text(payload)
    match = _EVENT_ID_RE.search(text)
    return match.group(1) if match else ""


def _default_executor(tool: str, payload: dict[str, Any]) -> dict[str, Any]:
    proc = subprocess.run(
        ["executor", "call", "google-workspace-ops", "org.default", tool,
         json.dumps(payload, ensure_ascii=False)],
        text=True, capture_output=True, timeout=120, check=False)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "Executor call failed").strip())
    try:
        raw = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Executor returned invalid JSON") from exc
    if not raw.get("ok", False) or (raw.get("data") or {}).get("isError"):
        raise RuntimeError(_extract_text(raw) or "Executor calendar operation failed")
    return {"ok": True, "text": _extract_text(raw), "event_id": _find_event_id(raw), "raw": raw}


def _load_record(approval_id: str) -> tuple[Path, dict[str, Any]]:
    path = _record_path(approval_id)
    if not path.exists():
        raise FileNotFoundError(f"Unknown or expired calendar approval: {approval_id}")
    return path, json.loads(path.read_text(encoding="utf-8"))


def resolve_calendar_approval(
    approval_id: str, decision: str, *, executor: Executor = _default_executor,
) -> dict[str, Any]:
    """Reject locally, or conflict-check/create/read-back through Executor without an LLM."""
    if decision not in {"authorize", "refuse"}:
        raise ValueError(f"Unsupported calendar decision: {decision}")
    path, record = _load_record(approval_id)
    if record.get("status") != "pending":
        return record
    now = datetime.now().astimezone().isoformat()
    if decision == "refuse":
        record.update(status="rejected", updated_at=now,
                      message=f"❌ Demande **{approval_id}** refusée. Aucun événement créé.")
        _write_record(path, record)
        return record

    account = str(record.get("account") or "").strip()
    if not account:
        raise RuntimeError("Aucun compte Google Calendar n'est configuré pour les approbations cron")
    event = dict(record["event"])
    check = executor("get_events", {
        "user_google_email": account,
        "calendar_id": event["calendar_id"],
        "time_min": event["start_time"],
        "time_max": event["end_time"],
        "max_results": 10,
        "single_events": True,
    })
    check_text = str(check.get("text") or "")
    if "no events found" not in check_text.lower():
        raise RuntimeError("La vérification de conflit est ambiguë ou un événement existe déjà")

    created = executor("manage_event", {
        "user_google_email": account,
        "action": "create",
        "calendar_id": event["calendar_id"],
        "summary": event["summary"],
        "start_time": event["start_time"],
        "end_time": event["end_time"],
        "timezone": event["timezone"],
        "description": event["description"],
        "send_updates": "none",
    })
    event_id = str(created.get("event_id") or "")
    if not event_id:
        raise RuntimeError("Google Calendar n'a pas retourné d'identifiant d'événement")
    verified = executor("get_events", {
        "user_google_email": account,
        "calendar_id": event["calendar_id"],
        "event_id": event_id,
        "detailed": True,
    })
    if not verified.get("ok"):
        raise RuntimeError("L'événement a été créé mais sa relecture a échoué")
    record.update(
        status="approved", updated_at=now, event_id=event_id,
        message=(f"✅ Événement **{event['summary']}** créé et vérifié "
                 f"(`{event_id}`), de {event['start_time']} à {event['end_time']}.")
    )
    _write_record(path, record)
    return record

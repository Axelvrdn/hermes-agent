#!/usr/bin/env python3
"""Resolve one persisted cron calendar approval without invoking an LLM."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cron.calendar_approvals import resolve_calendar_approval


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("approval_id")
    parser.add_argument("decision", choices=("authorize", "refuse"))
    args = parser.parse_args()
    try:
        result = resolve_calendar_approval(args.approval_id, args.decision)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps({"ok": True, "result": result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

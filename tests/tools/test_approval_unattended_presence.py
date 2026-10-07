"""Unattended-platform runs resolve flagged commands from ``approvals.unattended_mode``, never by
posting an approval card: the gateway exports ``HERMES_EXEC_ASK=1`` to every session it runs, and a
webhook run that honoured it sent the card to the route's delivery chat, where ``/approve`` resolves
a different session, so the run hung for the full approval timeout."""

import pytest

import tools.approval as approval_mod
from tools import approval_context


@pytest.fixture
def webhook_session(monkeypatch):
    monkeypatch.setattr(approval_mod, "_YOLO_MODE_FROZEN", False)
    monkeypatch.setattr(approval_context, "_get_approval_mode", lambda: "manual")
    for var in ("HERMES_CRON_SESSION", "HERMES_GATEWAY_SESSION", "HERMES_INTERACTIVE"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("HERMES_EXEC_ASK", "1")
    monkeypatch.setenv("HERMES_SESSION_PLATFORM", "webhook")
    monkeypatch.setenv("HERMES_SESSION_KEY", "test-webhook-session")
    monkeypatch.setattr(approval_mod, "_human_decision",
                        lambda *a, **k: pytest.fail("webhook run reached the human approval gate"))


def test_webhook_denies_instantly_even_with_gateway_exec_ask(webhook_session):
    result = approval_mod.check_all_command_guards("sudo systemctl restart nginx", "local")
    assert result["approved"] is False
    assert "approvals.unattended_mode" in result["message"]

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from gateway.config import PlatformConfig
from plugins.platforms.discord.adapter import CronActionsView, CronCalendarApprovalView, DiscordAdapter


def _adapter(allowed_users=None):
    adapter = DiscordAdapter(PlatformConfig(enabled=True, token="test", extra={}))
    adapter._client = MagicMock()
    adapter._allowed_user_ids = set(allowed_users or [])
    adapter._allowed_role_ids = set()
    return adapter


def _interaction(user_id="42"):
    return SimpleNamespace(
        user=SimpleNamespace(id=user_id, display_name="Axel", roles=[]),
        response=SimpleNamespace(defer=AsyncMock(), send_message=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()),
        message=SimpleNamespace(edit=AsyncMock()),
    )


@pytest.mark.asyncio
async def test_send_attaches_controls_only_to_last_fragment():
    adapter = _adapter({"42"})
    channel = MagicMock()
    channel.send = AsyncMock(side_effect=[SimpleNamespace(id=1), SimpleNamespace(id=2)])
    adapter._resolve_channel = AsyncMock(return_value=channel)
    adapter.truncate_message = MagicMock(return_value=["first", "last"])

    result = await adapter.send(
        "9001",
        "long brief",
        metadata={
            "discord_cron_actions": {
                "version": 1,
                "job_id": "eefcdf90b2c1",
                "approval_id": "REV-20261006-1915",
                "expected_user_id": "42",
                "actions": ["rerun", "calendar_authorize", "calendar_refuse"],
            }
        },
    )

    assert result.success
    assert channel.send.await_count == 2
    assert channel.send.await_args_list[0].kwargs["view"] is None
    view = channel.send.await_args_list[1].kwargs["view"]
    assert isinstance(view, CronActionsView)
    assert [child.label for child in view.children] == ["Relancer", "Autoriser", "Refuser"]


@pytest.mark.asyncio
async def test_send_attaches_rerun_to_cron_without_calendar_request():
    adapter = _adapter({"42"})
    channel = MagicMock()
    channel.send = AsyncMock(return_value=SimpleNamespace(id=1))
    adapter._resolve_channel = AsyncMock(return_value=channel)

    result = await adapter.send(
        "9001",
        "ordinary cron brief",
        metadata={
            "discord_cron_actions": {
                "version": 1,
                "job_id": "eefcdf90b2c1",
                "expected_user_id": "42",
                "actions": ["rerun"],
            }
        },
    )

    assert result.success
    view = channel.send.await_args.kwargs["view"]
    assert isinstance(view, CronActionsView)
    assert [child.label for child in view.children] == ["Relancer"]


@pytest.mark.asyncio
async def test_authorized_click_injects_normal_decision_message_once():
    adapter = _adapter({"42"})
    adapter._dispatch_cron_calendar_authorization = AsyncMock()
    view = CronCalendarApprovalView(
        adapter=adapter,
        approval_id="REV-20261006-1915",
        expected_user_id="42",
        allowed_user_ids={"42"},
    )
    interaction = _interaction("42")

    await view._resolve(interaction, "authorize")
    await view._resolve(interaction, "authorize")

    adapter._dispatch_cron_calendar_authorization.assert_awaited_once_with(
        interaction, "REV-20261006-1915", "authorize")
    interaction.response.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_calendar_dispatch_uses_local_resolver_without_llm(monkeypatch):
    adapter = _adapter({"42"})
    adapter.handle_message = AsyncMock()
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(
            returncode=0,
            stdout='{"ok": true, "result": {"message": "✅ Événement créé."}}',
            stderr="",
        )

    monkeypatch.setattr("plugins.platforms.discord.adapter.subprocess.run", fake_run)

    result = await adapter._dispatch_cron_calendar_authorization(
        _interaction("42"), "REV-20261006-1915", "authorize")

    assert calls[0][0][-2:] == ["REV-20261006-1915", "authorize"]
    assert result == "✅ Événement créé."
    adapter.handle_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_wrong_user_cannot_resolve():
    adapter = _adapter({"42", "99"})
    adapter._dispatch_cron_calendar_authorization = AsyncMock()
    view = CronCalendarApprovalView(
        adapter=adapter,
        approval_id="REV-20261006-1915",
        expected_user_id="42",
        allowed_user_ids={"42", "99"},
    )
    interaction = _interaction("99")

    await view._resolve(interaction, "refuse")

    adapter._dispatch_cron_calendar_authorization.assert_not_awaited()
    interaction.response.send_message.assert_awaited_once()


def test_view_children_include_explicit_action_buttons():
    adapter = _adapter({"42"})
    view = CronCalendarApprovalView(
        adapter=adapter,
        approval_id="REV-20261006-1915",
        expected_user_id="42",
        allowed_user_ids={"42"},
    )
    assert len(view.children) == 2
    labels = [getattr(child, "label", None) for child in view.children]
    custom_ids = [getattr(child, "custom_id", None) for child in view.children]
    assert labels == ["Autoriser", "Refuser"]
    assert custom_ids == ["hermes:cron-calendar:authorize", "hermes:cron-calendar:refuse"]


@pytest.mark.asyncio
async def test_rerun_click_triggers_job_without_dispatching_a_message():
    adapter = _adapter({"42"})
    adapter.handle_message = AsyncMock()
    adapter._dispatch_cron_action = AsyncMock(return_value="Relance programmée.")
    view = CronActionsView(
        adapter=adapter,
        job_id="eefcdf90b2c1",
        expected_user_id="42",
        actions=["rerun"],
        allowed_user_ids={"42"},
    )
    interaction = _interaction("42")

    await view._resolve_rerun(interaction)

    adapter._dispatch_cron_action.assert_awaited_once_with(
        interaction, "eefcdf90b2c1", "rerun")
    adapter.handle_message.assert_not_awaited()
    interaction.followup.send.assert_awaited_once_with("Relance programmée.", ephemeral=True)


@pytest.mark.asyncio
async def test_dispatch_rerun_calls_deterministic_trigger(monkeypatch):
    adapter = _adapter({"42"})
    triggered = []

    def fake_trigger(job_id):
        triggered.append(job_id)
        return {"id": job_id, "name": "Brief"}

    monkeypatch.setattr("cron.jobs.trigger_job", fake_trigger)

    result = await adapter._dispatch_cron_action(
        _interaction("42"), "eefcdf90b2c1", "rerun")

    assert triggered == ["eefcdf90b2c1"]
    assert result == "🔄 Relance programmée pour **Brief**."


from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from gateway.config import PlatformConfig
from plugins.platforms.discord.adapter import CronCalendarApprovalView, DiscordAdapter


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
            "discord_cron_authorization": {
                "approval_id": "REV-20261006-1915",
                "expected_user_id": "42",
            }
        },
    )

    assert result.success
    assert channel.send.await_count == 2
    assert channel.send.await_args_list[0].kwargs["view"] is None
    view = channel.send.await_args_list[1].kwargs["view"]
    assert isinstance(view, CronCalendarApprovalView)
    assert len(view.children) == 2


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


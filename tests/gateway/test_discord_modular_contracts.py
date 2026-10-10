"""Behavior contracts for the incremental Discord adapter split (#2)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


def test_event_normalizer_preserves_message_identity_and_truncation():
    from plugins.platforms.discord import adapter_events

    message = SimpleNamespace(
        id=123, channel=SimpleNamespace(id=456), guild=SimpleNamespace(id=789),
        author=SimpleNamespace(id=42, display_name="Alice", bot=False),
        content="x" * 8200, edited_at=None,
    )
    payload, source = adapter_events.message_event_parts(
        message, lambda msg, author: {"text": msg.content[:8192]},
        thread_type=type("Thread", (), {}),
    )
    assert payload == {"chat_id": "456", "message_id": "123", "thread_id": None, "text": "x" * 8192}
    assert source == dict(chat_id="456", user_id="42", user_name="Alice", thread_id=None,
                          guild_id="789", message_id="123")
    message.author.bot = True
    assert adapter_events.message_event_parts(message, lambda *_: {}, thread_type=object) is None


def test_event_normalizer_does_not_attribute_missing_thread_owner():
    from plugins.platforms.discord import adapter_events

    thread = SimpleNamespace(id=321, owner_id=None, parent_id=123, guild=None)
    payload, source = adapter_events.thread_event_parts(thread, lambda *_: {})
    assert payload == {"thread_id": "321", "parent_chat_id": "123"}
    assert source["user_id"] is None


@pytest.mark.asyncio
async def test_shared_view_rechecks_live_auth_on_each_click():
    from plugins.platforms.discord.adapter import ExecApprovalView

    view = ExecApprovalView(session_key="s", allowed_user_ids={"42"})
    verdict = True
    view.live_auth = lambda _interaction: verdict
    interaction = SimpleNamespace(
        user=SimpleNamespace(id=42, roles=[]), guild=None, channel_id=5,
        response=SimpleNamespace(send_message=AsyncMock()),
    )
    assert view._check_auth(interaction) is True
    verdict = False
    assert view._check_auth(interaction) is False
    assert not await view._gate(interaction, resolved_msg=None, unauth_msg="denied")
    interaction.response.send_message.assert_awaited_once_with("denied", ephemeral=True)


def test_view_factory_accepts_optional_discord_only_when_requested():
    from plugins.platforms.discord import adapter_views

    assert callable(adapter_views.define_view_classes)
    from plugins.platforms.discord.adapter import discord
    views = adapter_views.define_view_classes(discord)
    assert views["CronActionsView"].__name__ == "CronActionsView"
    assert views["CronCalendarApprovalView"].__name__ == "CronCalendarApprovalView"


def test_file_uri_path_does_not_decode_regular_paths():
    from plugins.platforms.discord.adapter_media import _local_image_path

    assert _local_image_path("https://example.org/a%20b.png") is None
    assert _local_image_path("file:///tmp/a%20b.png") == "/tmp/a b.png"
    assert _local_image_path("file://C:/Users/Alice/a%20b.png", is_windows=True) == "C:/Users/Alice/a b.png"
    assert _local_image_path("file:///C:/Users/Alice/a%20b.png", is_windows=True) == "C:/Users/Alice/a b.png"
    assert _local_image_path("file://server/share/a%20b.png", is_windows=True) == "//server/share/a b.png"

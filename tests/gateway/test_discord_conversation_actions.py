from types import SimpleNamespace
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from gateway.config import PlatformConfig
from plugins.platforms.discord.adapter import DiscordAdapter, DiscordConversationActionsView


def _adapter():
    adapter = DiscordAdapter(PlatformConfig(enabled=True, token="test", extra={}))
    adapter._client = MagicMock()
    adapter._allowed_user_ids = {"42"}
    adapter._allowed_role_ids = set()
    return adapter


@pytest.mark.asyncio
async def test_normal_final_response_attaches_conversation_controls_to_last_fragment():
    adapter = _adapter()
    channel = MagicMock()
    channel.send = AsyncMock(side_effect=[SimpleNamespace(id=1), SimpleNamespace(id=2)])
    adapter._resolve_channel = AsyncMock(return_value=channel)
    adapter.truncate_message = MagicMock(return_value=["first", "last"])

    result = await adapter.send(
        "9001",
        "long response",
        metadata={
            "notify": True,
            "discord_conversation": {
                "version": 1,
                "session_key": "discord:9001",
                "response_message_id": "2",
                "expected_user_id": "42",
                "inbound_message_id": "11",
                "actions": ["regenerate", "edit", "tts", "obsidian", "continue"],
            },
        },
    )

    assert result.success
    assert channel.send.await_count == 2
    assert channel.send.await_args_list[0].kwargs["view"] is None
    view = channel.send.await_args_list[1].kwargs["view"]
    assert isinstance(view, DiscordConversationActionsView)
    assert [child.label for child in view.children] == [
        "Régénérer", "Modifier", "Lire / TTS", "Sauvegarder dans Obsidian", "Continuer",
    ]
    assert [child.style for child in view.children] == [
        2, 2, 1, 1, 2,
    ]


@pytest.mark.asyncio
async def test_tts_action_sends_the_clicked_response_without_an_agent_turn(monkeypatch):
    adapter = _adapter()
    adapter.send_voice = AsyncMock(return_value=SimpleNamespace(success=True))
    interaction = SimpleNamespace(
        channel=SimpleNamespace(id="9001"),
        message=SimpleNamespace(content="Réponse à lire"),
    )

    Path("/tmp/response.ogg").touch()
    monkeypatch.setattr(
        "tools.tts_tool.text_to_speech_tool",
        lambda **kwargs: '{"success": true, "file_path": "/tmp/response.ogg"}',
    )

    result = await adapter._dispatch_conversation_action(
        interaction, "tts", "discord:9001", "2", "11")

    assert "envoyée" in result.lower()
    adapter.send_voice.assert_awaited_once()
    assert adapter.send_voice.await_args.kwargs["audio_path"] == "/tmp/response.ogg"


@pytest.mark.asyncio
async def test_obsidian_action_saves_clicked_response_under_configured_vault(tmp_path, monkeypatch):
    adapter = _adapter()
    interaction = SimpleNamespace(message=SimpleNamespace(content="Une réponse importante"))
    monkeypatch.setenv("HERMES_OBSIDIAN_VAULT", str(tmp_path))

    result = await adapter._dispatch_conversation_action(
        interaction, "obsidian", "discord:9001", "2", "11")

    saved = next((tmp_path / "01 - Life OS" / "Captures").glob("*.md"))
    assert "Une réponse importante" in saved.read_text(encoding="utf-8")
    assert "file=" in result


@pytest.mark.asyncio
async def test_continue_action_uses_the_normal_authenticated_gateway_path():
    adapter = _adapter()
    adapter.gateway_runner = object()
    adapter.handle_message = AsyncMock()
    interaction = SimpleNamespace(
        channel=SimpleNamespace(id="9001", name="discussion"),
        user=SimpleNamespace(id="42", display_name="Axel"),
        message=SimpleNamespace(id="2"),
    )

    result = await adapter._dispatch_conversation_action(
        interaction, "continue", "discord:9001", "2", "11")

    assert "demandée" in result
    adapter.handle_message.assert_awaited_once()
    assert adapter.handle_message.await_args.args[0].text.startswith("Continue")

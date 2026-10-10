"""Opt-in V2 static delivery: no ambiguous transport retries."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gateway.config import PlatformConfig
from plugins.platforms.discord.adapter import DiscordAdapter
import plugins.platforms.discord.adapter as adapter_module


class LayoutView:
    def __init__(self, *, timeout=None):
        self.children = []

    def add_item(self, item):
        self.children.append(item)


class TextDisplay:
    def __init__(self, content):
        self.content = content


class Rejection(Exception):
    status = 400
    code = 50035


class AmbiguousFailure(Exception):
    status = 503
    code = 0


class RateLimited(Exception):
    status = 429
    code = 0


@pytest.fixture
def harness(monkeypatch):
    monkeypatch.setattr(adapter_module.discord.ui, "LayoutView", LayoutView, raising=False)
    monkeypatch.setattr(adapter_module.discord.ui, "TextDisplay", TextDisplay, raising=False)

    def make(*, enabled=True, error=None):
        adapter = DiscordAdapter(PlatformConfig(enabled=True, token="***", extra={"components_v2_static": enabled}))
        sent = []

        async def send(**kwargs):
            sent.append(kwargs)
            if len(sent) == 1 and error is not None:
                raise error
            return SimpleNamespace(id=len(sent) + 100)

        channel = SimpleNamespace(send=AsyncMock(side_effect=send))
        adapter._client = SimpleNamespace(get_channel=lambda _: channel, fetch_channel=AsyncMock())
        return adapter, sent

    return make


@pytest.mark.asyncio
async def test_opt_in_final_static_reply_uses_v2_text_without_legacy_content(harness):
    adapter, sent = harness()
    result = await adapter.send("555", "Hello", metadata={"notify": True})
    assert result.success
    assert len(sent) == 1
    assert "content" not in sent[0]
    assert isinstance(sent[0]["view"], LayoutView)
    assert [item.content for item in sent[0]["view"].children] == ["Hello"]


@pytest.mark.asyncio
async def test_disabled_or_nonfinal_or_action_reply_stays_legacy(harness):
    for enabled, metadata in ((False, {"notify": True}), (True, {}),
                              (True, {"notify": True, "streaming": True}),
                              (True, {"notify": True, "expect_edits": True}),
                              (True, {"notify": True, "discord_cron_actions": {"actions": ["rerun"], "job_id": "job", "expected_user_id": "42"}})):
        adapter, sent = harness(enabled=enabled)
        result = await adapter.send("555", "Hello", metadata=metadata)
        assert result.success
        assert len(sent) == 1
        assert sent[0]["content"] == "Hello"


@pytest.mark.asyncio
async def test_definite_v2_rejection_retries_legacy_once(harness):
    adapter, sent = harness(error=Rejection("invalid components"))
    result = await adapter.send("555", "Hello", metadata={"notify": True})
    assert result.success
    assert len(sent) == 2
    assert "view" in sent[0] and "content" not in sent[0]
    assert sent[1]["content"] == "Hello"


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [AmbiguousFailure("server failed"), RateLimited("slow down"), TimeoutError("unknown delivery")])
async def test_ambiguous_failure_never_retries_legacy(harness, error):
    adapter, sent = harness(error=error)
    result = await adapter.send("555", "Hello", metadata={"notify": True})
    assert not result.success
    assert len(sent) == 1


@pytest.mark.asyncio
async def test_multichunk_remains_legacy_to_avoid_mixed_partial_delivery(harness):
    adapter, sent = harness()
    result = await adapter.send("555", "A" * (adapter.MAX_MESSAGE_LENGTH + 3), metadata={"notify": True})
    assert result.success
    assert len(sent) >= 2
    assert all("content" in payload for payload in sent)

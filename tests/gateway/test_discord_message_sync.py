"""Generic gateway-to-adapter mutation seam."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from gateway.config import Platform
from gateway.run_adapters import GatewayAdapterLifecycleMixin


def test_gateway_mutation_seam_delegates_to_adapter():
    class Runner(GatewayAdapterLifecycleMixin):
        pass

    adapter = SimpleNamespace(handle_platform_event_mutation=AsyncMock(return_value=True))
    runner = Runner()
    runner._delivery_adapter_for = lambda _source: adapter
    source = SimpleNamespace(platform=Platform.DISCORD, user_id="7")
    event = {"platform": "discord", "event_type": "message_edited", "payload": {"message_id": "11"}}

    assert asyncio.run(runner._sync_discord_mutation(event, source)) is True
    adapter.handle_platform_event_mutation.assert_awaited_once_with(event, source)


def test_gateway_mutation_seam_fails_closed_without_adapter_policy():
    class Runner(GatewayAdapterLifecycleMixin):
        pass

    runner = Runner()
    runner._delivery_adapter_for = lambda _source: SimpleNamespace()
    source = SimpleNamespace(platform=Platform.DISCORD, user_id="7")
    event = {"platform": "discord", "event_type": "message_edited", "payload": {"message_id": "11"}}

    assert asyncio.run(runner._sync_discord_mutation(event, source)) is False

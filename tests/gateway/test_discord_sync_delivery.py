"""Discord mutation egress records only confirmed output IDs (#4)."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from gateway.config import Platform
from gateway.platforms.base import BasePlatformAdapter, SendResult
from hermes_state import AsyncSessionDB, SessionDB


def test_final_send_records_all_acknowledged_ids_but_not_uncertain_results(tmp_path):
    db = SessionDB(db_path=tmp_path / "state.db")
    db.create_session("s", source="discord")
    db.append_message("s", "user", "ask", platform_message_id="11")
    db.record_discord_turn("s", "11", 3, "7")
    class Adapter(BasePlatformAdapter):
        async def connect(self, **kwargs): pass
        async def disconnect(self): pass
        async def get_chat_info(self, chat_id): pass
        async def send(self, chat_id, content, reply_to=None, metadata=None): pass
        @property
        def name(self): return "discord"
    adapter = object.__new__(Adapter)
    adapter.platform = Platform.DISCORD
    adapter.config = SimpleNamespace(extra={"sync_message_mutations": True})
    adapter.gateway_runner = SimpleNamespace(_session_db=AsyncSessionDB(db))
    adapter._final_delivery_adapter = lambda _: adapter
    adapter._record_delivery_obligation = AsyncMock(return_value=None)
    adapter._send_with_retry = AsyncMock(return_value=SendResult(success=True, message_id="90", raw_response={"message_ids": ["90", "91"]}))
    adapter._release_turn_marker = AsyncMock()
    source = SimpleNamespace(chat_id="5", user_id="7", platform=Platform.DISCORD)
    event = SimpleNamespace(source=source, message_id="11", _discord_sync_session_id="s", _discord_sync_generation=3)
    asyncio.run(adapter.send_final_ledgered(event, "key", "answer", {}, reply_to=None))
    assert db.claim_discord_mutation("s", "11", "7", "delete")["output_ids"] == ["90", "91"]
    db.close()

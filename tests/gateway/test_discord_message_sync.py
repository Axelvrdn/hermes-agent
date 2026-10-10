"""Gateway contract for opt-in Discord mutations (#4), with real SQLite state."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from gateway.run_adapters import GatewayAdapterLifecycleMixin
from gateway.config import Platform
from hermes_state import AsyncSessionDB, SessionDB


def test_disabled_or_missing_target_never_interrupts(tmp_path):
    db = SessionDB(db_path=tmp_path / "state.db")
    db.create_session("s", source="discord")
    adapter = SimpleNamespace(config=SimpleNamespace(extra={}), delete_message=AsyncMock(return_value=True))
    class Runner(GatewayAdapterLifecycleMixin):
        pass
    runner = Runner()
    runner.session_store = SimpleNamespace(lookup_by_session_key=lambda _: SimpleNamespace(session_id="s"))
    runner._session_key_for_source = lambda _: "key"
    runner._session_db = AsyncSessionDB(db)
    runner._delivery_adapter_for = lambda _: adapter
    runner._interrupt_and_clear_session = AsyncMock()
    runner._is_session_running = lambda _: False
    runner._invalidate_session_run_generation = lambda *a, **k: None
    runner._is_user_authorized_for_source = lambda _: True
    source = SimpleNamespace(platform=Platform.DISCORD, chat_id="5", thread_id=None, user_id="7")
    event = {"platform": "discord", "event_type": "message_deleted", "payload": {"message_id": "11", "author_id": "7"}}
    asyncio.run(runner._sync_discord_mutation(event, source))
    adapter.config.extra["sync_message_mutations"] = True
    asyncio.run(runner._sync_discord_mutation(event, source))
    runner._interrupt_and_clear_session.assert_not_awaited()
    adapter.delete_message.assert_not_awaited()
    db.close()


def test_claim_deletes_only_correlated_outputs_even_on_partial_failure(tmp_path):
    db = SessionDB(db_path=tmp_path / "state.db")
    db.create_session("s", source="discord")
    db.append_message("s", "user", "ask", platform_message_id="11")
    db.record_discord_turn("s", "11", 1, "7")
    db.record_discord_output("s", "11", 1, "7", "90")
    db.record_discord_output("s", "11", 1, "7", "91")
    adapter = SimpleNamespace(config=SimpleNamespace(extra={"sync_message_mutations": True}),
                              delete_message=AsyncMock(side_effect=[RuntimeError("offline"), True]))
    class Runner(GatewayAdapterLifecycleMixin):
        pass
    runner = Runner()
    runner.session_store = SimpleNamespace(lookup_by_session_key=lambda _: SimpleNamespace(session_id="s"))
    runner._session_key_for_source = lambda _: "key"
    runner._session_db = AsyncSessionDB(db)
    runner._delivery_adapter_for = lambda _: adapter
    runner._interrupt_and_clear_session = AsyncMock()
    runner._is_session_running = lambda _: False
    runner._invalidate_session_run_generation = lambda *a, **k: None
    runner._is_user_authorized_for_source = lambda _: True
    runner._readmit_discord_edit = AsyncMock()
    source = SimpleNamespace(platform=Platform.DISCORD, chat_id="5", thread_id=None, user_id="7")
    event = {"platform": "discord", "event_type": "message_edited", "payload": {"message_id": "11", "text": "new ask"}}
    asyncio.run(runner._sync_discord_mutation(event, source))
    asyncio.run(runner._sync_discord_mutation(event, source))
    assert adapter.delete_message.await_count == 2
    assert [c.args for c in adapter.delete_message.await_args_list] == [("5", "90"), ("5", "91")]
    runner._interrupt_and_clear_session.assert_not_awaited()
    db.close()


def test_edit_readmits_once_with_new_text(tmp_path):
    db = SessionDB(db_path=tmp_path / "state.db")
    db.create_session("s", source="discord")
    db.append_message("s", "user", "ask", platform_message_id="11")
    db.record_discord_turn("s", "11", 1, "7")
    class Runner(GatewayAdapterLifecycleMixin):
        pass
    runner = Runner()
    adapter = SimpleNamespace(config=SimpleNamespace(extra={"sync_message_mutations": True}),
                              delete_message=AsyncMock(return_value=True))
    runner.session_store = SimpleNamespace(lookup_by_session_key=lambda _: SimpleNamespace(session_id="s"))
    runner._session_key_for_source = lambda _: "key"
    runner._session_db = AsyncSessionDB(db)
    runner._delivery_adapter_for = lambda _: adapter
    runner._interrupt_and_clear_session = AsyncMock()
    runner._is_session_running = lambda _: False
    runner._invalidate_session_run_generation = lambda *a, **k: None
    runner._is_user_authorized_for_source = lambda _: True
    runner._readmit_discord_edit = AsyncMock()
    source = SimpleNamespace(platform=Platform.DISCORD, chat_id="5", thread_id=None, user_id="7")
    event = {"platform": "discord", "event_type": "message_edited", "payload": {"message_id": "11", "text": "new ask"}}
    asyncio.run(runner._sync_discord_mutation(event, source))
    asyncio.run(runner._sync_discord_mutation(event, source))
    runner._readmit_discord_edit.assert_awaited_once_with("new ask", source, "11")
    db.close()


def test_revoked_author_does_not_claim_or_delete(tmp_path):
    db = SessionDB(db_path=tmp_path / "state.db")
    db.create_session("s", source="discord")
    db.append_message("s", "user", "ask", platform_message_id="11")
    db.record_discord_turn("s", "11", 1, "7")
    class Runner(GatewayAdapterLifecycleMixin):
        pass
    runner = Runner()
    adapter = SimpleNamespace(config=SimpleNamespace(extra={"sync_message_mutations": True}),
                              delete_message=AsyncMock(return_value=True))
    runner.session_store = SimpleNamespace(lookup_by_session_key=lambda _: SimpleNamespace(session_id="s"))
    runner._session_key_for_source = lambda _: "key"
    runner._session_db = AsyncSessionDB(db)
    runner._delivery_adapter_for = lambda _: adapter
    runner._is_user_authorized_for_source = lambda _: False
    source = SimpleNamespace(platform=Platform.DISCORD, chat_id="5", thread_id=None, user_id="7")
    event = {"platform": "discord", "event_type": "message_deleted", "payload": {"message_id": "11", "author_id": "7"}}
    assert asyncio.run(runner._sync_discord_mutation(event, source)) is False
    assert db.probe_discord_mutation("s", "11", "7") is True
    adapter.delete_message.assert_not_awaited()
    db.close()

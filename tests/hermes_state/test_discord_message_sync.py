"""Opt-in Discord mutation contract (#4): durable ownership and atomic rewind."""

import pytest

from hermes_state import SessionDB


@pytest.fixture
def db(tmp_path):
    state = SessionDB(db_path=tmp_path / "state.db")
    yield state
    state.close()


def test_claim_only_an_active_owned_input_and_archive_once(db):
    db.create_session("s", source="discord")
    target = db.append_message("s", "user", "original", platform_message_id="11")
    db.append_message("s", "assistant", "answer")
    assert db.claim_discord_mutation("s", "11", "7", "edit") is None  # no ownership
    db.record_discord_turn("s", "11", 1, "7")
    db.record_discord_output("s", "11", 1, "7", "90")
    claim = db.claim_discord_mutation("s", "11", "7", "edit")
    assert claim == {"target_id": target, "generation": 1, "output_ids": ["90"]}
    assert db.claim_discord_mutation("s", "11", "7", "edit") is None
    assert db._read_one("SELECT active FROM messages WHERE id = ?", (target,))[0] == 0


def test_correlation_is_scoped_and_compaction_or_ambiguity_refuses(db):
    for sid in ("a", "b"):
        db.create_session(sid, source="discord")
        db.append_message(sid, "user", "ask", platform_message_id="11")
    db.record_discord_turn("a", "11", 1, "7")
    db.record_discord_output("a", "11", 1, "7", "90")
    assert db.claim_discord_mutation("b", "11", "7", "delete") is None
    # A compacted/inactive target must not archive another turn or delete remote outputs.
    db._execute_write(lambda conn: conn.execute("UPDATE messages SET active=0, compacted=1 WHERE session_id='a'"))
    assert db.claim_discord_mutation("a", "11", "7", "delete") is None


def test_stale_generation_cannot_add_outputs_after_claim(db):
    db.create_session("s", source="discord")
    db.append_message("s", "user", "ask", platform_message_id="11")
    db.record_discord_turn("s", "11", 2, "7")
    db.record_discord_output("s", "11", 2, "7", "90")
    assert db.claim_discord_mutation("s", "11", "7", "delete") is not None
    assert db.record_discord_output("s", "11", 2, "7", "91") is False


def test_mutation_readiness_rejects_active_turn_lease(db):
    db.create_session("s", source="discord")
    db.append_message("s", "user", "ask", platform_message_id="11")
    assert db.try_acquire_session_turn_lease("s", "other", ttl_seconds=30)
    assert db.transcript_mutation_ready("s") is False
    db.release_session_turn_lease("s", "other")
    assert db.transcript_mutation_ready("s") is True


def test_mutation_ownership_survives_compression_child_publication(db):
    db.create_session("parent", source="discord")
    db.append_message("parent", "user", "ask", platform_message_id="11")
    db.record_discord_turn("parent", "11", 1, "7")
    db.record_discord_output("parent", "11", 1, "7", "90")
    db.try_acquire_compression_lock("parent", "holder")
    db.publish_compression_child(
        parent_session_id="parent", child_session_id="child", source="discord",
        messages=[{"role": "user", "content": "ask", "platform_message_id": "11"}],
        compression_lock_holder="holder", watermark=None,
    )
    assert db.probe_discord_mutation("child", "11", "7") is True


def test_discord_turn_generation_can_be_allocated_after_restart(db):
    db.create_session("s", source="discord")
    db.append_message("s", "user", "ask", platform_message_id="11")
    db.record_discord_turn("s", "11", 2, "7")
    assert db.record_discord_turn("s", "11", 0, "7") is True
    assert db._read_one(
        "SELECT MAX(generation) FROM discord_mutation_turns WHERE session_id='s' AND inbound_id='11'"
    )[0] == 3


def test_discord_turn_allocator_returns_durable_generation(db):
    db.create_session("s", source="discord")
    assert db.allocate_discord_turn_generation("s", "11", "7", 1) == 1
    db.claim_discord_mutation("s", "11", "7", "edit")
    assert db.allocate_discord_turn_generation("s", "11", "7", 1) == 2

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

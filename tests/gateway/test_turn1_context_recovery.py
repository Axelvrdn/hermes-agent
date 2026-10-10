"""Regression contracts for opt-in Turn-1 context recovery (#7)."""
import asyncio
from types import SimpleNamespace

from gateway.config import Platform
from gateway.session import SessionSource
from gateway.turn1_context import recover_turn1_context, resolve_forum_tags


def source(**kwargs):
    return SessionSource(platform=Platform.DISCORD, chat_id="123", chat_type="thread",
                         chat_name="guild / planning / Launch API", **kwargs)


def test_disabled_and_followup_never_touch_retrievers():
    calls = []
    def search(*args, **kwargs):
        calls.append(args)
        return []
    cfg = {"enabled": True}
    assert asyncio.run(recover_turn1_context(source(), "Launch API", config={"enabled": False}, search_notes=search)) == ""
    assert asyncio.run(recover_turn1_context(source(), "Launch API", config=cfg, history=[{"role": "user"}], search_notes=search)) == ""
    assert asyncio.run(recover_turn1_context(source(), "Launch API", config=cfg, internal=True, search_notes=search)) == ""
    assert not calls


def test_tag_ids_resolve_to_names_without_unknown_ids():
    forum = SimpleNamespace(available_tags=[SimpleNamespace(id=5, name="Operations"), SimpleNamespace(id=6, name="Launch")])
    thread = SimpleNamespace(parent=forum, applied_tags=[6, 99, 5, 6])
    assert resolve_forum_tags(thread) == ("Launch", "Operations")


def test_forum_tags_survive_source_copy_without_entering_persisted_origin():
    from gateway.session_identity import replace_source
    original = source(forum_tag_names=("Launch",))
    copied = replace_source(original, chat_name="new title")
    assert copied.forum_tag_names == ("Launch",)
    assert "forum_tag_names" not in copied.to_dict()


def test_discord_source_receives_resolved_tags_from_thread():
    from plugins.platforms.discord.adapter_thread_titles import DiscordThreadTitlesMixin
    forum = SimpleNamespace(available_tags=[SimpleNamespace(id=5, name="Operations")])
    thread = SimpleNamespace(parent=forum, applied_tags=[5])
    assert DiscordThreadTitlesMixin._forum_tag_names(thread) == ("Operations",)


def test_rank_dedupe_cap_and_exclude_current_session():
    note_queries, history_queries = [], []
    def notes(query, limit):
        note_queries.append((query, limit))
        return [{"title": "Launch API design", "path": "notes/launch.md", "content": "release sequence" * 20},
                {"title": "Launch API design", "path": "notes/launch.md", "content": "duplicate"}]
    def sessions(query, limit, current_session_id):
        history_queries.append((query, limit, current_session_id))
        return [{"session_id": "old", "snippet": "Launch API deployment notes", "source": "discord"},
                {"session_id": "now", "snippet": "Launch API current", "source": "discord"}]
    result = asyncio.run(recover_turn1_context(
        source(forum_tag_names=("Launch",)), "Launch API", config={"enabled": True, "max_chars": 360,
        "max_results": 2, "timeout_seconds": 2}, session_id="now", search_notes=notes, search_sessions=sessions))
    assert "notes/launch.md" in result and "old" in result
    assert "duplicate" not in result and "now" not in result
    assert len(result) <= 360
    assert note_queries and history_queries[0][-1] == "now"
    assert "untrusted" in result.lower()


def test_timeout_and_failure_fail_open():
    async def slow(query, limit):
        await asyncio.sleep(0.3)
        return []
    def broken(query, limit, current_session_id):
        raise RuntimeError("private error")
    assert asyncio.run(recover_turn1_context(source(), "Topic", config={"enabled": True, "timeout_seconds": .01},
                                            search_notes=slow, search_sessions=broken)) == ""


def test_blank_or_private_dm_is_not_retrieved():
    called = []
    def search(*args):
        called.append(args)
        return []
    assert asyncio.run(recover_turn1_context(source(), "", config={"enabled": True}, search_notes=search)) == ""
    dm = SessionSource(platform=Platform.DISCORD, chat_id="1", chat_type="dm", chat_name="Alice")
    assert asyncio.run(recover_turn1_context(dm, "Topic", config={"enabled": True}, search_notes=search)) == ""
    assert not called


def test_gateway_preparation_stages_recall_in_first_user_sidecar_only(monkeypatch):
    """The prologue is a one-shot user sidecar, never appended to the pinned system prompt."""
    from gateway.turn1_context import stage_turn1_recall
    async def fake_recall(*args, **kwargs):
        return "## Prior context (untrusted)\n- Note foo"
    monkeypatch.setattr("gateway.turn1_context.recover_turn1_context", fake_recall)
    notes = []
    original_prompt = "## Current Session Context"
    asyncio.run(stage_turn1_recall({"context_recovery": {"enabled": True}}, source(), "Topic", [],
                                   "old", notes, internal=False))
    assert notes == ["## Prior context (untrusted)\n- Note foo"]
    assert original_prompt == "## Current Session Context"


def test_obsidian_search_reads_only_bounded_matches(monkeypatch):
    import json
    from gateway.turn1_context import search_obsidian_notes
    from tools.registry import registry
    monkeypatch.setattr(registry, "get_entry", lambda name: object())
    calls = []
    def handler(server, tool, timeout):
        def invoke(args):
            calls.append((tool, args))
            if tool == "search_files":
                return json.dumps({"result": json.dumps(["vault/Launch.md", "vault/Other.md"])})
            return json.dumps({"result": "# Launch\nship it"})
        return invoke
    monkeypatch.setattr("tools.mcp_tool_handlers._make_tool_handler", handler)
    rows = search_obsidian_notes("Launch API", 1, "obsidian-vault")
    assert len(rows) == 1 and rows[0]["path"] == "vault/Launch.md"
    assert calls == [("search_files", {"path": ".", "pattern": "**/*Launch*.md"}),
                     ("read_text_file", {"path": "vault/Launch.md", "head": 30})]

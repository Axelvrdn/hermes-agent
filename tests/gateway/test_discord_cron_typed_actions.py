"""Behaviour contracts for typed Discord cron interactions (#8)."""
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from gateway.config import PlatformConfig
from plugins.platforms.discord.adapter import CronActionsView, DiscordAdapter


def adapter():
    a = DiscordAdapter(PlatformConfig(enabled=True, token="test", extra={}))
    a._allowed_user_ids = {"42", "99"}
    a._allowed_role_ids = set()
    a.handle_message = AsyncMock()
    return a


def interaction(user="42"):
    return SimpleNamespace(user=SimpleNamespace(id=user, roles=[]),
                           response=SimpleNamespace(send_message=AsyncMock(), send_modal=AsyncMock(), defer=AsyncMock()),
                           followup=SimpleNamespace(send=AsyncMock()), message=SimpleNamespace(edit=AsyncMock()))


@pytest.mark.asyncio
async def test_workout_button_opens_native_modal_without_agent(tmp_path):
    a = adapter()
    view = CronActionsView(adapter=a, job_id="job", expected_user_id="42", actions=["workout_checkin"],
                           allowed_user_ids={"42"}, profile_home=str(tmp_path))
    assert [c.custom_id for c in view.children] == ["hermes:cron:workout_checkin"]
    i = interaction()
    await view.children[0].callback(i)
    modal = i.response.send_modal.await_args.args[0]
    import discord
    assert isinstance(modal, discord.ui.Modal)
    assert len(modal.children) == 5
    assert all(isinstance(c, discord.ui.TextInput) for c in modal.children)
    a.handle_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_unauthorized_modal_click_and_submit_have_no_effect(tmp_path):
    a = adapter()
    view = CronActionsView(adapter=a, job_id="job", expected_user_id="42", actions=["school_note"],
                           allowed_user_ids={"42", "99"}, profile_home=str(tmp_path))
    await view.children[0].callback(interaction("99"))
    i = interaction()
    await view.children[0].callback(i)
    modal = i.response.send_modal.await_args.args[0]
    await modal.on_submit(interaction("99"))
    assert not list(tmp_path.rglob("*.json"))
    a.handle_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_workout_submission_persists_once_and_rejects_invalid_pain(tmp_path):
    from plugins.platforms.discord.cron_actions import read_context
    a = adapter()
    view = CronActionsView(adapter=a, job_id="job", expected_user_id="42", actions=["workout_checkin"],
                           allowed_user_ids={"42"}, profile_home=str(tmp_path))
    i = interaction()
    await view.children[0].callback(i)
    modal = i.response.send_modal.await_args.args[0]
    for child, value in zip(modal.children, ["0", "10", "3", "5", "OK"]):
        child._value = value
    await modal.on_submit(interaction())
    await modal.on_submit(interaction())
    records = read_context("job", home=tmp_path)
    assert len(records) == 1
    assert records[0]["author_id"] == "42"
    assert records[0]["values"]["shoulder"] == 0
    assert records[0]["values"]["knee"] == 10
    assert records[0]["created_at"] and records[0]["expires_at"]
    assert records[0]["plan"]
    assert a.handle_message.await_count == 0

    i = interaction()
    await view.children[0].callback(i)
    bad = i.response.send_modal.await_args.args[0]
    for child, value in zip(bad.children, ["11", "0", "0", "0", "OK"]):
        child._value = value
    await bad.on_submit(interaction())
    assert len(read_context("job", home=tmp_path)) == 1


def test_context_ttl_and_job_isolation(tmp_path):
    from plugins.platforms.discord.cron_actions import save_context, read_context
    save_context("a", "42", "school_note", {"note": "réviser"}, home=tmp_path, now=100, ttl=50,
                 submission_id="one")
    assert read_context("a", home=tmp_path, now=120)[0]["values"]["note"] == "réviser"
    assert read_context("a", home=tmp_path, now=151) == []
    assert read_context("b", home=tmp_path, now=120) == []
    assert save_context("a", "42", "school_note", {"note": "réviser"}, home=tmp_path,
                        now=100, ttl=50, submission_id="one") is False


def test_obsidian_path_confinement_dedup_and_link(tmp_path):
    from plugins.platforms.discord.cron_actions import save_obsidian
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "School").mkdir()
    result = save_obsidian("job", "42", "Le brief", vault=vault, folder="School",
                           allowed_folders=["School"], bridge_url="https://example.test/open?file={file}",
                           submission_id="abc")
    assert "School%2F" in result
    notes = list((vault / "School").glob("*.md"))
    assert len(notes) == 1
    assert 'job_id: "job"' in notes[0].read_text()
    assert save_obsidian("job", "42", "Le brief", vault=vault, folder="School",
                         allowed_folders=["School"], bridge_url="https://example.test/open?file={file}",
                         submission_id="abc") == result
    for folder in ["../escape", "/tmp", "School/../../escape"]:
        with pytest.raises(ValueError):
            save_obsidian("job", "42", "Le brief", vault=vault, folder=folder,
                          allowed_folders=[folder], bridge_url="https://example.test/?file={file}", submission_id="abc")
    (vault / "linked").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError):
        save_obsidian("job", "42", "Le brief", vault=vault, folder="linked",
                      allowed_folders=["linked"], bridge_url="https://example.test/?file={file}", submission_id="abc")


@pytest.mark.asyncio
async def test_school_modal_stores_note_without_agent(tmp_path):
    from plugins.platforms.discord.cron_actions import read_context
    a = adapter()
    view = CronActionsView(adapter=a, job_id="school", expected_user_id="42", actions=["school_note"],
                           allowed_user_ids={"42"}, profile_home=str(tmp_path))
    opened = interaction()
    await view.children[0].callback(opened)
    modal = opened.response.send_modal.await_args.args[0]
    assert len(modal.children) == 1
    modal.children[0]._value = "Question sur les intégrales"
    await modal.on_submit(interaction())
    assert read_context("school", home=tmp_path)[0]["values"]["note"] == "Question sur les intégrales"
    a.handle_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_obsidian_button_writes_only_configured_folder_without_agent(tmp_path):
    vault = tmp_path / "vault"
    (vault / "School").mkdir(parents=True)
    a = adapter()
    view = CronActionsView(adapter=a, job_id="school", expected_user_id="42", actions=["obsidian_capture"],
                           allowed_user_ids={"42"}, brief="Le brief", action_config={"obsidian": {
                               "vault": str(vault), "folder": "School", "allowed_folders": ["School"],
                               "bridge_url": "https://example.test/?file={file}"}})
    i = interaction()
    i.message.id = "msg-1"
    await view.children[0].callback(i)
    assert len(list((vault / "School").glob("*.md"))) == 1
    i.response.send_message.assert_awaited_once()
    a.handle_message.assert_not_awaited()


def test_obsidian_existing_symlink_file_cannot_escape_vault(tmp_path):
    from plugins.platforms.discord.cron_actions import save_obsidian
    import hashlib
    vault = tmp_path / "vault"
    (vault / "School").mkdir(parents=True)
    outside = tmp_path / "outside.md"
    outside.write_text("safe")
    token = hashlib.sha256(b"job:abc").hexdigest()[:24]
    (vault / "School" / f"cron-{token}.md").symlink_to(outside)
    with pytest.raises(ValueError):
        save_obsidian("job", "42", "overwrite", vault=vault, folder="School",
                      allowed_folders=["School"], bridge_url="https://example.test/?file={file}",
                      submission_id="abc")
    assert outside.read_text() == "safe"


def test_optional_workout_database_adapter(tmp_path):
    import sqlite3
    from plugins.platforms.discord.cron_actions import save_context
    target = tmp_path / "workout.db"
    save_context("run", "42", "workout_checkin",
                 {"shoulder": "2", "knee": "0", "calves": "0", "fatigue": "5", "comment": "ok"},
                 home=tmp_path / "profile", submission_id="adapter-1", workout_db=target)
    with sqlite3.connect(target) as db:
        row = db.execute("SELECT job_id, author_id, shoulder, knee, calves, fatigue FROM checkins").fetchone()
    assert row == ("run", "42", 2, 0, 0, 5)

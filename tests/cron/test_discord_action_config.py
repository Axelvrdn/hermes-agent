"""Validate configured typed cron actions before job storage (#8)."""
import pytest
from cron.jobs import create_job, update_job, get_job


def test_job_actions_persist_on_create_and_update(tmp_path):
    job = create_job("brief", "30m", discord_actions={"actions": ["workout_checkin"]})
    assert get_job(job["id"])["discord_actions"] == {"actions": ["workout_checkin"]}
    update_job(job["id"], {"discord_actions": {"actions": ["school_note"]}})
    assert get_job(job["id"])["discord_actions"] == {"actions": ["school_note"]}


def test_unknown_or_unconfigured_export_action_rejected():
    with pytest.raises(ValueError):
        create_job("brief", "30m", discord_actions={"actions": ["arbitrary"]})
    with pytest.raises(ValueError):
        create_job("brief", "30m", discord_actions={"actions": ["obsidian_capture"]})

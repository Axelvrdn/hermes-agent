"""Next cron run consumes only its own nonexpired typed context (#8)."""
from plugins.platforms.discord.cron_actions import save_context


def test_context_text_includes_prior_checkin_and_school_note(tmp_path):
    from plugins.platforms.discord.cron_actions import context_for_job
    save_context("workout", "42", "workout_checkin",
                 {"shoulder": "7", "knee": "0", "calves": "1", "fatigue": "8", "comment": "fatigué"},
                 home=tmp_path, now=100, ttl=200, submission_id="one")
    text = context_for_job("workout", home=tmp_path, now=150)
    assert "fatigué" in text and "Repos" in text
    assert context_for_job("other", home=tmp_path, now=150) == ""
    assert context_for_job("workout", home=tmp_path, now=301) == ""


def test_next_prompt_contains_checkin_from_own_profile(tmp_path, monkeypatch):
    from cron.scheduler_prompt import _build_job_prompt
    from hermes_constants import get_hermes_home
    home = get_hermes_home()
    save_context("workout", "42", "school_note", {"note": "réviser les intégrales"},
                 home=home, submission_id="note")
    job = {"id": "workout", "prompt": "Préparer le brief", "discord_actions": {"actions": ["school_note"]}}
    assert "réviser les intégrales" in _build_job_prompt(job)
    assert "réviser les intégrales" not in _build_job_prompt({**job, "id": "other"})

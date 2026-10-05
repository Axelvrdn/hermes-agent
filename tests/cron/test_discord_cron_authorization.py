from cron.scheduler_delivery import _extract_discord_calendar_confirmation


def test_extracts_exact_final_line_marker():
    content = "Brief\n\n[HERMES_DISCORD_CALENDAR_CONFIRM_V1:REV-20261006-1915]\n"
    clean, approval_id = _extract_discord_calendar_confirmation(content)
    assert clean == "Brief"
    assert approval_id == "REV-20261006-1915"


def test_rejects_marker_that_is_not_the_final_line():
    content = (
        "[HERMES_DISCORD_CALENDAR_CONFIRM_V1:REV-20261006-1915]\n"
        "ordinary trailing text"
    )
    assert _extract_discord_calendar_confirmation(content) == (content, None)


def test_rejects_marker_with_event_arguments():
    content = "[HERMES_DISCORD_CALENDAR_CONFIRM_V1:REV-1 start=19:15]"
    assert _extract_discord_calendar_confirmation(content) == (content, None)

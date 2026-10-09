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


def test_prepare_target_delivery_attaches_controls_for_explicit_discord_channel_target():
    from unittest.mock import MagicMock
    from gateway.config import GatewayConfig, Platform, PlatformConfig
    from cron import scheduler_delivery as sd

    job = {
        "id": "eefcdf90b2c1",
        "attach_to_session": True,
        "deliver": "discord:1556638655685066772",
        "origin": {
            "platform": "discord",
            "chat_id": "1554533724605911071",
            "user_id": "471786748620308480",
        },
    }
    target = {
        "platform": "discord",
        "chat_id": "1556638655685066772",
        "thread_id": None,
        "_resolved_from": "explicit",
    }
    adapter = MagicMock()
    adapter.name = "discord"
    loop = MagicMock()
    loop.is_running.return_value = True
    config = GatewayConfig(platforms={Platform.DISCORD: PlatformConfig(enabled=True)})

    t = sd._prepare_target_delivery(
        job,
        target,
        adapters={Platform.DISCORD: adapter},
        loop=loop,
        config=config,
        notify_delivery=True,
        mirror_enabled=False,
        mirror_text="",
        delivery_errors=[],
        discord_calendar_approval_id="REV-20261011-1700",
    )

    assert t is not None
    assert t.discord_calendar_approval_id == "REV-20261011-1700"
    assert t.origin_user_id == "471786748620308480"


def test_prepare_target_delivery_honors_discord_inchannel_surface():
    from unittest.mock import MagicMock
    from gateway.config import GatewayConfig, Platform, PlatformConfig
    from plugins.platforms.discord.adapter import DiscordAdapter
    from cron import scheduler_delivery as sd

    job = {
        "id": "eefcdf90b2c1",
        "attach_to_session": True,
        "deliver": "discord:1556638655685066772",
        "origin": {
            "platform": "discord",
            "chat_id": "1554533724605911071",
            "user_id": "471786748620308480",
        },
    }
    target = {
        "platform": "discord",
        "chat_id": "1556638655685066772",
        "thread_id": None,
        "_resolved_from": "explicit",
    }
    adapter = DiscordAdapter(PlatformConfig(enabled=True, token="test", extra={"cron_continuable_surface": "in_channel"}))
    loop = MagicMock()
    loop.is_running.return_value = True
    config = GatewayConfig(platforms={Platform.DISCORD: PlatformConfig(enabled=True, token="test", extra={"cron_continuable_surface": "in_channel"})})

    t = sd._prepare_target_delivery(
        job,
        target,
        adapters={Platform.DISCORD: adapter},
        loop=loop,
        config=config,
        notify_delivery=True,
        mirror_enabled=True,
        mirror_text="hello",
        delivery_errors=[],
    )

    assert t is not None
    assert t.in_channel_surface is True
    assert t.opened_thread_id is None
    assert t.thread_id is None



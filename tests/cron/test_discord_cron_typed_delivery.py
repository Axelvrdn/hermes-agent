"""Per-job typed Discord delivery contract (#8)."""
from unittest.mock import MagicMock

from gateway.config import GatewayConfig, Platform, PlatformConfig
from cron import scheduler_delivery as sd


def test_job_config_adds_typed_actions_to_delivery(tmp_path):
    job = {"id": "a", "attach_to_session": True,
           "origin": {"platform": "discord", "chat_id": "1", "user_id": "42"},
           "discord_actions": {"actions": ["workout_checkin", "obsidian_capture"],
                               "obsidian": {"vault": str(tmp_path), "folder": "Notes",
                                            "allowed_folders": ["Notes"],
                                            "bridge_url": "https://example.test/?file={file}"}}}
    target = {"platform": "discord", "chat_id": "2", "thread_id": None, "_resolved_from": "explicit"}
    adapter = MagicMock()
    adapter.name = "discord"
    loop = MagicMock()
    loop.is_running.return_value = True
    t = sd._prepare_target_delivery(job, target, adapters={Platform.DISCORD: adapter}, loop=loop,
                                    config=GatewayConfig(platforms={Platform.DISCORD: PlatformConfig(enabled=True)}),
                                    notify_delivery=True, mirror_enabled=False, mirror_text="", delivery_errors=[])
    assert t is not None
    actions = sd._live_route_metadata(t)[1]["discord_cron_actions"]
    assert actions["actions"] == ["rerun", "workout_checkin", "obsidian_capture"]
    assert actions["action_config"] == job["discord_actions"]

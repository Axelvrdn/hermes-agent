"""``complete.path`` is an off-turn RPC: it must bind the profile the request (or its socket) names.

One local backend serves every "This device" profile behind a remote-primary Desktop. With a local-terminal
launch profile, a profile whose terminal runs over ssh used to get the HOST's files (or nothing) in the
composer's ``@`` suggestions, because the handler read the launch process's terminal backend outside any
profile scope.
"""

import json
from pathlib import Path

import pytest

from tui_gateway import server


def _profile(root: Path, name: str, config: str) -> Path:
    home = root / "profiles" / name
    home.mkdir(parents=True)
    (home / "config.yaml").write_text(config, encoding="utf-8")
    return home


@pytest.fixture
def hosted(tmp_path, monkeypatch):
    launch = tmp_path / "hermes-home"
    launch.mkdir()
    (launch / "config.yaml").write_text("terminal:\n  backend: local\n", encoding="utf-8")
    monkeypatch.setenv("HERMES_HOME", str(launch))
    monkeypatch.setattr(server, "_hermes_home", launch)
    monkeypatch.delenv("TERMINAL_ENV", raising=False)
    monkeypatch.delenv("TERMINAL_CWD", raising=False)
    remote = _profile(launch, "remote-box", "terminal:\n  backend: ssh\n  cwd: /srv/app\n")
    monkeypatch.setattr(server, "_profile_home", lambda name: remote if name == "remote-box" else None)
    listed = []

    def _terminal_tool(command, **kwargs):
        listed.append(command)
        return json.dumps({"output": "deploy.sh\nsrc/\n", "exit_code": 0})

    monkeypatch.setattr("tools.terminal_tool.terminal_tool", _terminal_tool)
    return listed


def _complete(params):
    return server.handle_request({"jsonrpc": "2.0", "id": "c", "method": "complete.path", "params": params})


def test_a_named_ssh_profile_lists_its_own_workspace(hosted):
    resp = _complete({"word": "@file:", "profile": "remote-box"})

    assert hosted, "listing ran on the host instead of the profile's ssh backend"
    assert "/srv/app" in hosted[0]
    assert [item["display"] for item in resp["result"]["items"]] == ["deploy.sh"]  # `@file:` lists files only


def test_the_launch_profile_keeps_its_host_listing(hosted, tmp_path, monkeypatch):
    (tmp_path / "workspace").mkdir()
    (tmp_path / "workspace" / "notes.md").write_text("x", encoding="utf-8")

    resp = _complete({"word": "@file:", "cwd": str(tmp_path / "workspace")})

    assert hosted == []
    assert [item["display"] for item in resp["result"]["items"]] == ["notes.md"]

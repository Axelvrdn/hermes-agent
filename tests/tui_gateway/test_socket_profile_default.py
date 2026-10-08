"""A socket opened as ``/api/ws?profile=<p>`` speaks for ``p`` on a backend that hosts several profiles.

Desktop runs ONE local host backend for every "This device" profile while its primary is remote, so
the socket is the only thing that names the profile for RPCs whose callers omit ``profile``. Before
this, those RPCs silently ran against the launch profile's home.
"""

from __future__ import annotations

import contextlib
from types import SimpleNamespace

import pytest

import tui_gateway.server as server
from tui_gateway.transport import bind_transport, reset_transport


@pytest.fixture
def bound_homes(monkeypatch):
    """Record the profile home each RPC runs under (the socket's scope), without building real scopes."""
    bound = []
    homes = {"reviewer": "/profiles/reviewer", "calendar-demo": "/profiles/calendar-demo"}
    monkeypatch.setattr(server, "_profile_home", lambda name: homes.get(name or ""))

    @contextlib.contextmanager
    def _scope(session, *, hydrate_secrets=True):
        # Never fetch external secret sources per RPC: Stop would wait behind a slow `op run`.
        bound.append(session.get("profile_home") if hydrate_secrets is False else ("HYDRATED", session))
        yield

    monkeypatch.setattr(server, "_session_profile_runtime_scope", _scope)
    return bound


@pytest.fixture
def echo_profile(monkeypatch, bound_homes):
    seen = []
    contract = SimpleNamespace(params=SimpleNamespace(model_fields={"profile": None, "session_id": None}))
    monkeypatch.setitem(server._methods, "probe.profile", lambda rid, params: seen.append(params) or {"id": rid})
    monkeypatch.setitem(server._contracts.METHODS, "probe.profile", contract)
    monkeypatch.setattr(server._contracts, "validate_params", lambda _c, params: (params, None))
    return seen


def _call(transport, params):
    token = bind_transport(transport)
    try:
        server._handle_admitted_request({"jsonrpc": "2.0", "id": 1, "method": "probe.profile", "params": params})
    finally:
        reset_transport(token)


def test_socket_profile_defaults_profile_but_never_overrides_explicit_or_live_session(echo_profile, monkeypatch):
    sock = SimpleNamespace(default_profile="reviewer")
    monkeypatch.setitem(server._sessions, "live-1", {"profile_home": "/elsewhere"})

    _call(sock, {})
    _call(sock, {"profile": "calendar-demo"})
    _call(sock, {"session_id": "live-1"})
    _call(SimpleNamespace(default_profile=None), {})

    assert [p.get("profile") for p in echo_profile] == ["reviewer", "calendar-demo", None, None]


def test_socket_profile_binds_its_home_for_the_whole_rpc(echo_profile, bound_homes, monkeypatch):
    """Handlers with no ``profile`` plumbing (wake, path completion, process.stop) read config and the
    terminal policy from the bound scope: it must be the socket's profile, or a live session's own."""
    sock = SimpleNamespace(default_profile="reviewer")
    monkeypatch.setitem(server._sessions, "live-1", {"profile_home": "/profiles/calendar-demo"})

    _call(sock, {})                              # socket default
    _call(sock, {"session_id": "live-1"})        # a live session keeps its own profile
    _call(sock, {"profile": "calendar-demo"})    # explicit cross-profile target: the handler's call
    _call(SimpleNamespace(default_profile=None), {})  # unscoped socket: unchanged

    assert bound_homes == ["/profiles/reviewer", "/profiles/calendar-demo"]

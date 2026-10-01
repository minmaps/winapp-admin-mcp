import asyncio
from contextlib import contextmanager
import io
import json
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace

import pytest
import pywintypes

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server
import manage


class Stub:
    identity = {"elevated": True, "integrity": "high"}
    winapp = Path("winapp.exe")
    allowed = {"notepad.exe"}

    def __init__(self):
        self.calls = []

    def list_windows(self):
        return {"windows": []}

    def run(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return {"ok": True, "exit_code": 0, "data": {}}

    def type_literal(self, window_id, selector, text):
        return self.run("send-keys", window_id, [text], ["--target=" + selector, "--via", "send-input", "--verbatim"])


def tool(mcp, name, args):
    return asyncio.run(mcp.call_tool(name, args))


def test_catalog_and_bounds():
    stub = Stub()
    mcp = server.create_mcp(stub, 39781)
    tools = asyncio.run(mcp.list_tools())
    assert len(tools) == 13
    assert {t.name for t in tools} >= {"inspect", "invoke", "screenshot", "wait_for"}
    with pytest.raises(Exception):
        tool(mcp, "inspect", {"window_id": "test", "depth": 999})
    assert not stub.calls


@pytest.mark.parametrize("keys", ["win+r", "alt+f4", "ctrl+alt+del", "vk=0x5B", "ctrl+a win+r"])
def test_system_keys_never_reach_cli(keys):
    stub = Stub()
    with pytest.raises(Exception):
        tool(server.create_mcp(stub, 39781), "press_keys", {"window_id": "test", "selector": "editor", "keys": keys})
    assert not stub.calls


def test_option_looking_text_is_literal():
    stub = Stub()
    mcp = server.create_mcp(stub, 39781)
    tool(mcp, "type_text", {"window_id": "test", "selector": "--app=other", "text": "--window=0 $(hello)"})
    assert stub.calls[-1][0][2] == ["--window=0 $(hello)"]
    assert stub.calls[-1][0][3][0] == "--target=--app=other"
    tool(mcp, "wait_for", {"window_id": "test", "selector": "editor", "value": "--window=0"})
    assert "--value=--window=0" in stub.calls[-1][0][3]


def test_invoke_has_exact_action():
    stub = Stub()
    tool(server.create_mcp(stub, 39781), "invoke", {"window_id": "test", "selector": "button"})
    assert stub.calls[-1][0][3] == ["--action", "invoke"]


@pytest.mark.parametrize("peer,host,auth,origin,expected", [
    ("127.0.0.1", "127.0.0.1:39781", "Bearer token", None, 200),
    ("127.0.0.1", "127.0.0.1:39781", None, None, 401),
    ("127.0.0.1", "127.0.0.1:39781", "Bearer wrong", None, 401),
    ("192.168.1.20", "127.0.0.1:39781", "Bearer token", None, 403),
    ("127.0.0.1", "evil.example", "Bearer token", None, 403),
    ("127.0.0.1", "127.0.0.1:39781", "Bearer token", "http://evil.example", 403),
])
def test_gate(peer, host, auth, origin, expected):
    async def check():
        messages = []
        async def app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"{}"})
        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}
        async def send(message):
            messages.append(message)
        headers = [(b"host", host.encode())]
        if auth:
            headers.append((b"authorization", auth.encode()))
        if origin:
            headers.append((b"origin", origin.encode()))
        await server.LocalGate(app, "token", 39781)({"type": "http", "method": "GET", "path": "/health",
            "headers": headers, "client": (peer, 1234)}, receive, send)
        assert next(m["status"] for m in messages if m["type"] == "http.response.start") == expected
    asyncio.run(check())


def bridge_for_run(monkeypatch, tmp_path):
    b = server.Bridge.__new__(server.Bridge)
    b.winapp, b.env, b.lock, b.state = Path(sys.executable), {}, threading.Lock(), tmp_path
    @contextmanager
    def target(_):
        yield {"hwnd": 1234, "pid": 4567}
    b.target = target
    return b


def test_argv_and_audit_do_not_contain_document_text(monkeypatch, tmp_path):
    b = bridge_for_run(monkeypatch, tmp_path)
    calls = []
    def run(*args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(stdout="{}", stderr="", returncode=0)
    monkeypatch.setattr(server.subprocess, "run", run)
    text = "--window=0 $(hello) confidential document"
    assert b.run("set-value", "ref", ["editor", text])["ok"]
    assert calls[0][0][0][-3:] == ["--", "editor", text]
    assert calls[0][1]["shell"] is False
    assert text not in (tmp_path / "audit.jsonl").read_text("utf-8")


def test_timeout_is_explicit(monkeypatch, tmp_path):
    b = bridge_for_run(monkeypatch, tmp_path)
    def timeout(*args, **kwargs):
        raise server.subprocess.TimeoutExpired("winapp", 30)
    monkeypatch.setattr(server.subprocess, "run", timeout)
    assert b.run("inspect", "ref")["error"] == "cli_timeout"


def test_literal_input_chunks_are_serialized_and_exact(monkeypatch, tmp_path):
    b = bridge_for_run(monkeypatch, tmp_path)
    b.lock = threading.RLock()
    calls = []
    def run(*args, **kwargs):
        calls.append(args[0])
        return SimpleNamespace(stdout="{}", stderr="", returncode=0)
    monkeypatch.setattr(server.subprocess, "run", run)
    literal = "--texte littéral : éèà Ω  deux espaces."
    result = b.type_literal("ref", "--app=other", literal)
    assert result["ok"]
    assert result["data"]["characters_submitted"] == len(literal)
    assert "".join(argv[-1] for argv in calls) == literal
    assert all(len(argv[-1]) <= 8 and "--verbatim" in argv and "--target=--app=other" in argv for argv in calls)


def test_literal_input_stops_after_first_failed_chunk(monkeypatch, tmp_path):
    b = bridge_for_run(monkeypatch, tmp_path)
    b.lock = threading.RLock()
    calls = []
    def run(*args, **kwargs):
        calls.append(args[0])
        return SimpleNamespace(stdout="{}", stderr="", returncode=0 if len(calls) == 1 else 1)
    monkeypatch.setattr(server.subprocess, "run", run)
    result = b.type_literal("ref", "editor", "a"*30)
    assert not result["ok"]
    assert len(calls) == 2
    assert result["characters_submitted"] == 8


@pytest.mark.parametrize("targets,key", [({}, "missing"), ({"expired": {"expires": 0, "identity": (1, 1, "old")}}, "expired")])
def test_unknown_and_expired_targets(targets, key):
    b = server.Bridge.__new__(server.Bridge)
    b.targets = targets
    with pytest.raises(ValueError):
        with b.target(key):
            pass


def test_reused_window_handle_is_refused(monkeypatch):
    b = server.Bridge.__new__(server.Bridge)
    b.targets = {"ref": {"expires": time.monotonic()+30, "identity": (123, 42, "old")}}
    @contextmanager
    def changed(_):
        yield {"hwnd": 123, "pid": 43, "created": "new"}
    monkeypatch.setattr(server, "window_info", changed)
    with pytest.raises(ValueError):
        with b.target("ref"):
            pass


def test_process_scope():
    b = server.Bridge.__new__(server.Bridge)
    b.identity = {"user_sid": "user", "session_id": 1, "integrity_rid": 12288}
    b.allowed = {server.canonical(sys.executable)}
    info = {"executable": sys.executable, "user_sid": "user", "session_id": 1, "integrity_rid": 12288}
    assert b.authorized(info)
    for change in [{"user_sid": "other"}, {"session_id": 2}, {"integrity_rid": 16384}]:
        assert not b.authorized(dict(info, **change))


def test_inaccessible_window_does_not_break_listing(monkeypatch):
    b = server.Bridge.__new__(server.Bridge)
    b.targets, b.lock = {}, threading.Lock()
    monkeypatch.setattr(server, "enumerate_windows", lambda: [123])
    @contextmanager
    def inaccessible(_):
        raise pywintypes.error(5, "OpenProcess", "Access denied")
        yield
    monkeypatch.setattr(server, "window_info", inaccessible)
    assert b.list_windows() == {"windows": []}


def test_register_validates_codex_types_before_live_write(monkeypatch, tmp_path):
    project, codex_home = tmp_path/"project", tmp_path/"codex"
    project.mkdir()
    (project/"state").mkdir()
    codex_home.mkdir()
    (project/"config.json").write_text('{"port":39781}', "utf-8")
    original = '[mcp_servers.existing]\ncommand = "existing.exe"\n\n[unrelated]\nkeep = true\n'
    path = codex_home/"config.toml"
    path.write_text(original, "utf-8")
    monkeypatch.setattr(manage, "ROOT", project)
    monkeypatch.setattr(manage, "CONFIG", project/"config.json")
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    validated = []
    def validate(*args, **kwargs):
        assert path.read_text("utf-8") == original
        staged = Path(kwargs["env"]["CODEX_HOME"])/"config.toml"
        import tomllib
        parsed = tomllib.loads(staged.read_text("utf-8"))
        assert isinstance(parsed["mcp_servers"]["winapp_admin"]["http_headers_helper"], str)
        assert parsed["unrelated"]["keep"]
        assert parsed["mcp_servers"]["existing"]["command"] == "existing.exe"
        validated.append(True)
        return SimpleNamespace(returncode=0, stderr="")
    monkeypatch.setattr(manage.subprocess, "run", validate)
    manage.register()
    assert validated
    assert "http_headers_helper" in path.read_text("utf-8")


def test_rejected_config_never_changes_live_file(monkeypatch, tmp_path):
    project, codex_home = tmp_path/"project", tmp_path/"codex"
    project.mkdir()
    (project/"state").mkdir()
    codex_home.mkdir()
    (project/"config.json").write_text('{"port":39781}', "utf-8")
    path = codex_home/"config.toml"
    path.write_text('model = "existing"\n', "utf-8")
    monkeypatch.setattr(manage, "ROOT", project)
    monkeypatch.setattr(manage, "CONFIG", project/"config.json")
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setattr(manage.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=1, stderr="invalid type"))
    with pytest.raises(RuntimeError, match="aucun changement"):
        manage.register()
    assert path.read_text("utf-8") == 'model = "existing"\n'

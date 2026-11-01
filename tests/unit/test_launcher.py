"""Launch readiness follows service health rather than a historical milestone label."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend import launcher


@pytest.mark.parametrize(
    "health,ready",
    [
        ({"status": "ok", "milestone": "M12", "screening_available": True}, True),
        ({"status": "ok", "milestone": "M10", "screening_available": True}, True),
        ({"status": "error", "screening_available": True}, False),
        ({"status": "ok", "screening_available": False}, False),
        ({"milestone": "M12"}, False),
    ],
)
def test_launcher_readiness_uses_current_health_contract(monkeypatch, health, ready):
    monkeypatch.setattr(launcher.sys, "argv", ["run.sh", "--port", "18510"])
    monkeypatch.setattr(launcher.signal, "signal", lambda *args: None)
    monkeypatch.setattr(launcher, "validate_setup", lambda root: SimpleNamespace(ai=None))
    monkeypatch.setattr(launcher, "start_ai", lambda settings: None)
    monkeypatch.setattr(launcher.socket, "socket", MagicMock())
    monkeypatch.setattr(launcher.time, "sleep", lambda seconds: None)
    monkeypatch.setenv("SPR_NO_BROWSER", "1")
    process = MagicMock()
    process.poll.return_value = None
    process.wait.return_value = 0
    spawn = MagicMock(return_value=process)
    monkeypatch.setattr(launcher.subprocess, "Popen", spawn)
    client = MagicMock()
    response = client.__enter__.return_value.get.return_value
    response.is_success = True
    response.json.return_value = health
    monkeypatch.setattr(launcher.httpx, "Client", MagicMock(return_value=client))
    with pytest.raises(SystemExit) as stopped:
        launcher.main()
    if ready:
        assert stopped.value.code == 0
        assert client.__enter__.return_value.get.call_count == 1
    else:
        assert "did not become ready" in str(stopped.value.code)
    command = spawn.call_args.args[0]
    assert command[command.index("--host") + 1] == "127.0.0.1"

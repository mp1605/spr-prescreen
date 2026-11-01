"""Loopback launcher. Start optional cached Ollama; clean up only owned child processes."""

from __future__ import annotations

import argparse
import asyncio
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from types import FrameType

import httpx

from backend.boot import validate_setup
from backend.core.engines.ollama import Ollama
from backend.core.offline_status import listeners
from backend.core.settings import AISettings
from backend.local_ai import serve_environment, verify_runtime

ROOT = Path(__file__).resolve().parent.parent


async def eligible(settings: AISettings) -> bool:
    try:
        async with asyncio.timeout(3):
            provider = Ollama()
            model = next((m for m in await provider.models() if m.name == settings.model), None)
            return bool(
                model
                and model.digest == settings.model_digest
                and await provider.context_limit(model.name) >= settings.context_tokens
            )
    except Exception:
        return False


def stop(process: subprocess.Popen[bytes] | None) -> None:
    if process is not None and process.poll() is None:
        # SIGINT lets Python parser/semaphore finalizers run during graceful exit.
        process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def start_ai(settings: AISettings) -> subprocess.Popen[bytes] | None:
    if not settings.enabled:
        return None
    # Never replace a listener that belongs to another app or user session.
    with socket.socket() as probe:
        occupied = probe.connect_ex(("127.0.0.1", 11434)) == 0
    if occupied:
        observed, inspected = listeners({11434})
        if (
            inspected == "unavailable"
            or not observed
            or any(not item.loopback for item in observed)
        ):
            raise ValueError("Existing Ollama listener could not be verified as loopback-only.")
        if not asyncio.run(eligible(settings)):
            raise ValueError(
                "Existing local Ollama does not match the pinned model/context. "
                "AI can be disabled in settings."
            )
        print(
            "Using the existing loopback Ollama service; it will not be stopped on exit.",
            flush=True,
        )
        return None
    verify_runtime(ROOT)
    log_path = ROOT / "runs/ollama-runtime.log"
    log_path.parent.mkdir(exist_ok=True, mode=0o700)
    descriptor = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    os.chmod(log_path, 0o600)
    with os.fdopen(descriptor, "ab") as log:
        process = subprocess.Popen(
            [str(ROOT / "runtime/ollama/ollama"), "serve"],
            cwd=ROOT,
            stdout=log,
            stderr=log,
            env=serve_environment(ROOT, cpu=os.environ.get("SPR_OLLAMA_CPU") == "1"),
        )
    for _ in range(40):
        if process.poll() is not None:
            break
        if asyncio.run(eligible(settings)):
            return process
        time.sleep(0.2)
    stop(process)
    raise ValueError(
        "Local Ollama did not become ready with the cached pinned model. No download was attempted."
    )


def interrupted(signum: int, frame: FrameType | None) -> None:
    raise KeyboardInterrupt


def main() -> None:
    signal.signal(signal.SIGTERM, interrupted)
    if hasattr(signal, "SIGHUP"):
        signal.signal(signal.SIGHUP, interrupted)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8501, help="Loopback port; default 8501")
    arguments = parser.parse_args()
    if not 1024 <= arguments.port <= 65535:
        parser.error("Use an unprivileged local port (1024–65535)")
    ai = backend = None
    try:
        settings = validate_setup(ROOT)
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", arguments.port))
        ai = start_ai(settings.ai)
        backend = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "backend.app:create_app",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                str(arguments.port),
                "--no-access-log",
            ],
            cwd=ROOT,
        )
        url = f"http://127.0.0.1:{arguments.port}"
        with httpx.Client(trust_env=False, timeout=1) as client:
            for _ in range(80):
                if backend.poll() is not None:
                    raise ValueError("Backend exited during startup; inspect the terminal message.")
                try:
                    response = client.get(url + "/api/health")
                    if response.is_success:
                        health = response.json()
                        if (
                            health.get("status") == "ok"
                            and health.get("screening_available") is True
                        ):
                            break
                except httpx.HTTPError:
                    pass
                time.sleep(0.2)
            else:
                raise ValueError("Backend did not become ready on its loopback address.")
        print("SPR local workspace: " + url, flush=True)
        if os.environ.get("SPR_NO_BROWSER") != "1":
            import webbrowser

            webbrowser.open(url)
        raise SystemExit(backend.wait())
    except KeyboardInterrupt:
        pass
    except (OSError, ValueError) as exc:
        raise SystemExit("Startup stopped: " + str(exc)) from exc
    finally:
        stop(backend)
        stop(ai)


if __name__ == "__main__":
    main()

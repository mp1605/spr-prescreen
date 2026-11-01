"""Observe this app's listener ports; never label unavailable OS evidence as verified."""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Literal

from backend.core.assets import AssetStatus, model_status
from backend.core.engines.ollama import Ollama
from backend.core.rules_loader import StrictModel
from backend.security.airlock import airlock_status, loopback


class Listener(StrictModel):
    port: int
    address: str
    loopback: bool
    process: str
    evidence: Literal["os_listener", "request_socket"]


class OfflineStatus(StrictModel):
    airlock_installed: bool
    blocked_attempts: int
    listeners: tuple[Listener, ...]
    listener_inspection: Literal["available", "partial", "unavailable"]
    models_on_disk: AssetStatus
    ai_reachable: bool
    bundled_ai_present: bool = False
    bundled_ai_bytes: int = 0
    guard_scope: str = "Python sockets and DNS in this backend and its parser workers"
    native_scope: str = (
        "Native Word/Ollama processes use local-only settings; Python socket wrappers "
        "are not an operating-system firewall. Physical offline checks remain separate."
    )


def listeners(
    ports: set[int],
) -> tuple[tuple[Listener, ...], Literal["available", "partial", "unavailable"]]:
    executable = Path("/usr/sbin/lsof")
    if not executable.is_file():
        return (), "unavailable"
    found: list[Listener] = []
    pids = {os.getpid()}

    def parse(output: str, *, collect_only: bool = False) -> None:
        process = "unknown"
        for line in output.splitlines():
            if line.startswith("p") and line[1:].isdigit():
                pids.add(int(line[1:]))
            elif line.startswith("c"):
                process = line[1:80]
            elif line.startswith("n") and ":" in line and not collect_only:
                address, _, number = line[1:].rpartition(":")
                address = address.strip("[]")
                if number.isdigit():
                    found.append(
                        Listener(
                            port=int(number),
                            address=address,
                            loopback=loopback(address),
                            process=process,
                            evidence="os_listener",
                        )
                    )

    try:
        for port in sorted(ports):
            result = subprocess.run(
                [str(executable), "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-Fpcn"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode not in (0, 1):
                return (), "unavailable"
            parse(result.stdout)
        baseline = tuple(found)
        try:
            tree = subprocess.run(
                ["/bin/ps", "-axo", "pid=,ppid="],
                capture_output=True,
                text=True,
                timeout=2,
                check=True,
            )
        except (OSError, subprocess.SubprocessError):
            return baseline, "partial"
        pairs = [
            tuple(map(int, line.split()))
            for line in tree.stdout.splitlines()
            if len(line.split()) == 2
        ]
        while True:
            children = {pid for pid, parent in pairs if parent in pids}
            if children <= pids:
                break
            pids.update(children)
        result = subprocess.run(
            [
                str(executable),
                "-nP",
                "-a",
                "-p",
                ",".join(map(str, sorted(pids))),
                "-iTCP",
                "-sTCP:LISTEN",
                "-Fpcn",
            ],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode not in (0, 1):
            return (), "unavailable"
        found.clear()
        parse(result.stdout)
        return tuple(found), "available"
    except (OSError, ValueError, subprocess.SubprocessError):
        return (), "unavailable"


def bundled_ai(root: Path) -> tuple[bool, int]:
    try:
        manifest = root / "models/ollama/manifests/registry.ollama.ai/library/qwen2.5/3b"
        data = json.loads(manifest.read_bytes())
        layers = [data["config"], *data["layers"]]
        total = 0
        for layer in layers:
            digest, size = layer["digest"], layer["size"]
            if not re.fullmatch(r"sha256:[a-f0-9]{64}", digest) or not isinstance(size, int):
                return False, 0
            path = root / "models/ollama/blobs" / digest.replace(":", "-")
            if (
                not path.resolve().is_relative_to((root / "models").resolve())
                or path.stat().st_size != size
            ):
                return False, 0
            total += size
        return bool(layers), total
    except (OSError, ValueError, KeyError, TypeError):
        return False, 0


async def offline_status(root: Path, server: tuple[str, int] | None) -> OfflineStatus:
    installed, blocked = airlock_status()
    port = server[1] if server else 8501
    observed, inspection = await asyncio.to_thread(listeners, {port, 11434})
    if inspection == "unavailable" and server:
        observed = (
            Listener(
                port=port,
                address=server[0],
                loopback=loopback(server[0]),
                process="backend",
                evidence="request_socket",
            ),
        )
    try:
        async with asyncio.timeout(2):
            response = await Ollama().request("GET", "/api/version")
            reachable = isinstance(response.get("version"), str)
    except Exception:
        reachable = False
    ai_present, ai_bytes = bundled_ai(root)
    return OfflineStatus(
        airlock_installed=installed,
        blocked_attempts=blocked,
        listeners=observed,
        listener_inspection=inspection,
        models_on_disk=model_status(root),
        ai_reachable=reachable,
        bundled_ai_present=ai_present,
        bundled_ai_bytes=ai_bytes,
    )

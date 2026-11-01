"""Offline, bounded Word rendering using the project-owned LibreOffice runtime."""

from __future__ import annotations

import json
import os
import signal
import subprocess
from pathlib import Path
from xml.sax.saxutils import escape


class PreviewError(ValueError):
    pass


def convert_word(root: Path, source: Path, output: Path) -> Path:
    executable = root / "runtime/LibreOfficeDev.app/Contents/MacOS/soffice"
    if not executable.is_file():
        raise PreviewError("Word page renderer is unavailable. Download the highlighted DOCX.")
    profile = output / "profile"
    user = profile / "user"
    user.mkdir(parents=True, mode=0o700)
    (user / "registrymodifications.xcu").write_text(
        '<?xml version="1.0"?><oor:items xmlns:oor="http://openoffice.org/2001/registry">'
        '<item oor:path="/org.openoffice.Office.Common/Security/Scripting">'
        '<prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop>'
        '<prop oor:name="DisableMacrosExecution" oor:op="fuse"><value>true</value></prop>'
        '</item><item oor:path="/org.openoffice.Office.Writer/Content/Update">'
        '<prop oor:name="Link" oor:op="fuse"><value>2</value></prop>'
        '<prop oor:name="Field" oor:op="fuse"><value>false</value></prop>'
        '<prop oor:name="Chart" oor:op="fuse"><value>false</value></prop>'
        "</item></oor:items>"
    )
    cache = output / "font-cache"
    cache.mkdir(mode=0o700)
    fonts = output / "fonts.conf"
    fonts.write_text(
        '<?xml version="1.0"?><fontconfig><dir>/System/Library/Fonts</dir>'
        "<dir>/Library/Fonts</dir><dir>"
        + escape(str(Path.home() / "Library/Fonts"))
        + "</dir><cachedir>"
        + escape(str(cache))
        + "</cachedir></fontconfig>"
    )
    options = {
        "ExportBookmarksToPDFDestination": {"type": "boolean", "value": "true"},
        "ExportNotes": {"type": "boolean", "value": "false"},
        "UseLosslessCompression": {"type": "boolean", "value": "true"},
        "ReduceImageResolution": {"type": "boolean", "value": "false"},
    }
    command = [
        str(executable),
        "-env:UserInstallation=" + profile.as_uri(),
        "--headless",
        "--nologo",
        "--nodefault",
        "--norestore",
        "--nolockcheck",
        "--convert-to",
        "pdf:writer_pdf_Export:" + json.dumps(options),
        "--outdir",
        str(output),
        str(source),
    ]
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(output),
        "TMPDIR": str(output),
        "FONTCONFIG_FILE": str(fonts),
        "XDG_CACHE_HOME": str(cache),
        "SAL_USE_VCLPLUGIN": "svp",
        "LANG": "en_US.UTF-8",
    }
    # A private process group is killed on timeout, including any child renderer.
    with (output / "renderer.log").open("wb") as log:
        process = subprocess.Popen(command, env=env, stdout=log, stderr=log, start_new_session=True)
        try:
            code = process.wait(timeout=60)
        except subprocess.TimeoutExpired as exc:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            raise PreviewError(
                "Word preview exceeded 60 seconds. Download the highlighted DOCX."
            ) from exc
    result = output / (source.stem + ".pdf")
    if code or not result.is_file() or result.stat().st_size > 100 * 1024**2:
        raise PreviewError("Word pages could not be rendered. Download the highlighted DOCX.")
    return result

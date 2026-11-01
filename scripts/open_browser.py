"""Open only the fixed loopback address once the service responds."""

import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.core.runtime import configure_offline_environment  # noqa: E402

configure_offline_environment(ROOT)
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

for _ in range(50):
    try:
        with opener.open("http://127.0.0.1:8501/api/health", timeout=1):
            webbrowser.open("http://127.0.0.1:8501")
            break
    except (urllib.error.URLError, TimeoutError):
        time.sleep(0.2)

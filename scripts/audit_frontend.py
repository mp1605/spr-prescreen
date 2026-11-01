"""Audit actual browser asset references; inert URLs in library text are not requests."""

import re
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def remote(value):
    return value.strip().casefold().startswith(("http:", "https:", "//"))


class References(HTMLParser):
    def handle_starttag(self, tag, attributes):
        for name, value in attributes:
            if name in {"src", "href"} and value and remote(value):
                raise ValueError("Remote HTML asset reference")


def audit(root):
    References().feed((root / "backend/static/index.html").read_text())
    styles = list((root / "backend/static/assets").glob("*.css"))
    if not styles:
        raise ValueError("Built stylesheet is missing")
    for path in styles:
        content = path.read_text()
        for value in re.findall(r"url\(\s*['\"]?([^)'\"]+)", content):
            if remote(value):
                raise ValueError("Remote CSS asset reference")
        if re.search(r"@import\s", content):
            raise ValueError("Unresolved CSS import")
    for path in (root / "frontend/src").rglob("*"):
        if path.suffix in {".ts", ".tsx"}:
            for value in re.findall(r"(?:from\s*|import\s*\()\s*['\"]([^'\"]+)", path.read_text()):
                if remote(value):
                    raise ValueError("Remote JavaScript import")
    return {
        "html": "local references",
        "css_files": len(styles),
        "remote_asset_references": 0,
        "source_imports": "local/bundled",
    }


if __name__ == "__main__":
    print(audit(ROOT))

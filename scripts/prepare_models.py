"""Explicit online setup command. It uses official policy text only, never sponsor papers."""

import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["HF_HUB_DISABLE_XET"] = "1"
os.environ["DO_NOT_TRACK"] = "1"
os.environ["ORT_DISABLE_TELEMETRY"] = "1"
os.environ["HF_HOME"] = str(ROOT / "models/huggingface")
os.environ.pop("HF_HUB_OFFLINE", None)

import spacy  # noqa: E402
from fastembed import TextEmbedding  # noqa: E402

model = TextEmbedding(
    model_name="BAAI/bge-small-en-v1.5",
    cache_dir=str(ROOT / "models/fastembed"),
    threads=2,
)
vector = next(
    model.embed(
        ["Information related to current operations, readiness or posture for future operations"]
    )
)
if len(vector) != 384:
    raise SystemExit("Unexpected embedding dimensions")
nlp = spacy.load("en_core_web_sm")
(ROOT / "models/spacy").mkdir(parents=True, exist_ok=True)
nlp.to_disk(ROOT / "models/spacy/en_core_web_sm")
files = []
for directory in (ROOT / "models/fastembed", ROOT / "models/spacy"):
    for path in sorted(directory.rglob("*")):
        if (
            path.is_file()
            and path.stat().st_size > 0
            and ".cache" not in path.parts
            and ".locks" not in path.parts
        ):
            files.append(
                {
                    "path": str(path.relative_to(ROOT)),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "bytes": path.stat().st_size,
                }
            )
manifest = {
    "embedding_model": "BAAI/bge-small-en-v1.5",
    "embedding_dimensions": 384,
    "language_model": "en_core_web_sm-3.8.0",
    "assets": files,
}
(ROOT / "models/manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
print(f"Prepared {len(files)} local model assets; 384-dimensional inference passed.")

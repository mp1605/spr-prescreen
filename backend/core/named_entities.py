"""Optional cached spaCy NER. No download, corpus search, or rule additions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Literal, Protocol

from backend.core.assets import ModelManifest, model_status
from backend.core.runtime import configure_offline_environment


@dataclass(frozen=True)
class NamedEntity:
    start: int
    end: int
    kind: Literal["location", "actor"]


class EntityProvider(Protocol):
    identity: str

    def entities(self, text: str) -> tuple[NamedEntity, ...]: ...


class LocalEntities:
    def __init__(self, root: Path) -> None:
        configure_offline_environment(root)
        if not model_status(root, verify_hashes=True).ready:
            raise ValueError("Optional local entity model unavailable")
        manifest = ModelManifest.model_validate_json((root / "models/manifest.json").read_bytes())
        self.identity = hashlib.sha256(
            json.dumps(
                [(a.path, a.sha256) for a in manifest.assets if "models/spacy/" in a.path]
            ).encode()
        ).hexdigest()
        import spacy

        self.nlp = spacy.load(
            root / "models/spacy/en_core_web_sm",
            disable=["tagger", "parser", "lemmatizer", "attribute_ruler"],
        )
        self.nlp.max_length = 2_000_001
        self.lock = RLock()

    def entities(self, text: str) -> tuple[NamedEntity, ...]:
        with self.lock:
            doc = self.nlp(text)
        return tuple(
            NamedEntity(
                e.start_char, e.end_char, "location" if e.label_ in {"GPE", "LOC"} else "actor"
            )
            for e in doc.ents
            if e.label_ in {"GPE", "LOC", "ORG"}
        )

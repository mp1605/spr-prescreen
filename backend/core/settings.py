from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, ValidationError, model_validator

from backend.core.rules_loader import PolicyError, StrictModel, load_yaml


class SemanticSettings(StrictModel):
    model: Literal["BAAI/bge-small-en-v1.5"]
    cache_dir: Literal["models/fastembed"]
    high_threshold: Annotated[float, Field(ge=0, le=1)]
    mid_threshold: Annotated[float, Field(ge=0, le=1)]
    calibrated: Literal[False]

    @model_validator(mode="after")
    def validate_thresholds(self) -> SemanticSettings:
        if self.mid_threshold >= self.high_threshold:
            raise ValueError("Semantic mid threshold must be lower than high threshold")
        return self


class AISettings(StrictModel):
    enabled: bool
    scope: Literal["full", "selective"] = "full"
    model: Annotated[str, Field(pattern=r"^[A-Za-z0-9_.:/-]{1,160}$")]
    model_digest: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")] | None = None
    context_tokens: Annotated[int, Field(ge=2048, le=32768)] = 32768
    max_output_tokens: Annotated[int, Field(ge=256, le=4096)] = 2048
    endpoint: Literal["http://127.0.0.1:11434"]
    timeout_seconds: Annotated[int, Field(ge=1, le=120)]

    @model_validator(mode="after")
    def local(self) -> AISettings:
        if (
            "cloud" in self.model.casefold()
            or "://" in self.model
            or self.max_output_tokens + 1024 >= self.context_tokens
        ):
            raise ValueError("Use a local model tag and sufficient context budget")
        if self.enabled and self.model_digest is None:
            raise ValueError("Enable through admin settings after verifying the local model digest")
        return self


class EvaluationSettings(StrictModel):
    mode: Literal["blind"]
    sponsor_material_access: Literal[False]
    exemplar_source: Literal["official_rules_only"]


class Settings(StrictModel):
    schema_version: Literal[1]
    host: Literal["127.0.0.1"]
    port: Literal[8501]
    max_file_mb: Literal[25]
    max_batch_files: Literal[100]
    semantic: SemanticSettings
    ai: AISettings
    evaluation: EvaluationSettings


def load_settings(root: Path) -> Settings:
    try:
        return Settings.model_validate(load_yaml(root / "config/settings.yaml"))
    except ValidationError as exc:
        raise PolicyError(f"Invalid settings configuration: {exc}") from exc

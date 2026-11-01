"""One local generation at a time, with a total per-paper deadline and add-only output."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any, Literal

import httpx

from backend.core.ai_merge import merge_ai
from backend.core.ai_models import AIInfo, AIProposal
from backend.core.ai_prompt import AIBudgetError, build_prompt
from backend.core.ai_quotes import VerifiedAI, verify_quote
from backend.core.ai_scope import source_for_ai
from backend.core.engines.context import SourceContext
from backend.core.engines.ollama import AIProvider, AIUnavailable, Ollama
from backend.core.ingest_models import ParseResult
from backend.core.models import FlagCount, PaperResult
from backend.core.rules_loader import RuleRegistry
from backend.core.settings import AISettings
from backend.core.specificity import SpecificityEngine


def settings_digest(settings: AISettings) -> str:
    return hashlib.sha256(settings.model_dump_json().encode()).hexdigest()


def pipeline_digest() -> str:
    root = Path(__file__).resolve().parents[1]
    files = (
        "ai_models.py",
        "ai_merge.py",
        "ai_prompt.py",
        "ai_quotes.py",
        "ai_scope.py",
        "engines/ai.py",
        "engines/ollama.py",
        "color_models.py",
        "models.py",
        "specificity_policy.py",
        "specificity_patterns.py",
        "specificity.py",
    )
    return hashlib.sha256(b"".join((root / name).read_bytes() for name in files)).hexdigest()


def _reject_constant(value: str) -> None:
    raise ValueError("Non-finite JSON")


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def parse_proposals(text: str) -> tuple[list[AIProposal], int]:
    value = json.loads(
        text,
        object_pairs_hook=_unique,
        parse_constant=_reject_constant,
    )
    if not isinstance(value, list) or len(value) > 32:
        raise ValueError("Strict JSON array required")
    valid = []
    rejected = 0
    for item in value:
        try:
            valid.append(AIProposal.model_validate(item, strict=True))
        except ValueError:
            rejected += 1
    return valid, rejected


class AIEngine:
    def __init__(self, settings: AISettings, provider: AIProvider | None = None) -> None:
        self.settings = settings
        self.provider = provider or Ollama()
        self.gate = Lock()

    def session(self, settings: AISettings | None = None) -> AISession | None:
        snapshot = settings or self.settings
        return AISession(self, snapshot) if snapshot.enabled else None


class AISession:
    def __init__(self, host: AIEngine, settings: AISettings) -> None:
        self.host, self.settings = host, settings
        self.verified_digest: str | None = None
        self.generation_attempted = False

    async def generate(self, payload: dict[str, Any], seconds: float) -> dict[str, Any]:
        async with asyncio.timeout(seconds):
            models = await self.host.provider.models()
            selected = next(
                (
                    m
                    for m in models
                    if m.name == self.settings.model and m.digest == self.settings.model_digest
                ),
                None,
            )
            if selected is None:
                raise AIUnavailable("Pinned local model unavailable or changed")
            if await self.host.provider.context_limit(selected.name) < self.settings.context_tokens:
                raise AIUnavailable("Configured context exceeds model capability")
            self.verified_digest = selected.digest
            self.generation_attempted = True
            response = await self.host.provider.complete(payload)
            if (
                response.get("model") != selected.name
                or response.get("done") is not True
                or response.get("done_reason") != "stop"
                or response.get("remote_host")
                or response.get("remote_model")
            ):
                raise AIUnavailable("Incomplete or nonlocal generation")
            tokens = response.get("prompt_eval_count")
            if (
                not isinstance(tokens, int)
                or isinstance(tokens, bool)
                or tokens < 1
                or tokens > self.settings.context_tokens - self.settings.max_output_tokens
            ):
                raise AIUnavailable("Invalid model context accounting")
            return response

    def run(
        self,
        document: ParseResult,
        baseline: PaperResult,
        registry: RuleRegistry,
        assessor: SpecificityEngine | None = None,
    ) -> PaperResult:
        self.generation_attempted = False
        self.verified_digest = None
        started = time.monotonic()
        deadline = started + self.settings.timeout_seconds
        state: Literal["ran", "timeout", "error"] = "ran"
        codes = []
        accepted = []
        rejected = 0
        prompt_digest = None
        size = 0
        locked = False
        scoped = source_for_ai(document, baseline, self.settings.scope)
        if self.settings.scope == "selective" and not scoped.segments:
            info = AIInfo(
                model=self.settings.model,
                configured_model_digest=self.settings.model_digest,
                configuration_digest=settings_digest(self.settings),
                pipeline_digest=pipeline_digest(),
                state="skipped",
                scope="selective",
                generation_attempted=False,
                total_source_segments=len(document.segments),
                seconds=time.monotonic() - started,
                issue_codes=("no_candidates",),
                context_tokens=self.settings.context_tokens,
                timeout_seconds=self.settings.timeout_seconds,
                max_output_tokens=self.settings.max_output_tokens,
            )
            return baseline.model_copy(
                update={
                    "ai_state": "skipped",
                    "ai": info,
                    "seconds": baseline.seconds + time.monotonic() - started,
                }
            )
        try:
            payload, prompt_digest, size = build_prompt(scoped, baseline, registry, self.settings)
            locked = self.host.gate.acquire(timeout=max(0, deadline - time.monotonic()))
            if not locked:
                raise TimeoutError
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError
            response = asyncio.run(self.generate(payload, remaining))
            message = response.get("message", {})
            if (
                not isinstance(message, dict)
                or message.get("tool_calls")
                or not isinstance(message.get("content"), str)
            ):
                raise ValueError("Strict content required")
            proposals, rejected = parse_proposals(message["content"])
            if rejected:
                codes.append("invalid_proposal")
            unique: dict[tuple[str, str, int, int], VerifiedAI] = {}
            units = {unit.unit_id: unit for unit in document.units}
            context = SourceContext(document)
            as_of = baseline.fusion.as_of_utc_date if baseline.fusion else datetime.now(UTC).date()
            for proposal in proposals:
                match = verify_quote(proposal, scoped, deadline)
                if match is None:
                    rejected += 1
                    codes.append("unbound_or_ambiguous_quote")
                    continue
                if (
                    assessor is not None
                    and proposal.item_id.startswith("L2-")
                    and proposal.clear_or_possible == "clear"
                ):
                    facts = assessor.features(
                        units[match.segment.unit_id],
                        match.evidence.char_start,
                        match.evidence.char_end,
                        as_of=as_of,
                        context=context,
                    )
                    match = replace(match, features=facts)
                key = (
                    match.segment.segment_id,
                    proposal.item_id,
                    match.evidence.char_start,
                    match.evidence.char_end,
                )
                previous = unique.get(key)
                if previous and previous.evidence.clear_or_possible != proposal.clear_or_possible:
                    rejected += 1
                    codes.append("conflicting_suggestions")
                    if proposal.clear_or_possible == "possible":
                        unique[key] = match
                else:
                    unique[key] = match
            accepted = list(unique.values())
            if time.monotonic() > deadline:
                raise TimeoutError
        except (TimeoutError, httpx.TimeoutException):
            state = "timeout"
            codes.append("deadline_exceeded")
            accepted = []
        except AIBudgetError as exc:
            state = "error"
            codes.append(str(exc))
            accepted = []
        except Exception:
            state = "error"
            codes.append("provider_or_response_error")
            accepted = []
        finally:
            if locked:
                self.host.gate.release()
        info = AIInfo(
            model=self.settings.model,
            model_digest=self.verified_digest,
            configured_model_digest=self.settings.model_digest,
            configuration_digest=settings_digest(self.settings),
            pipeline_digest=pipeline_digest(),
            prompt_digest=prompt_digest,
            state=state,
            scope=self.settings.scope,
            total_source_segments=len(document.segments),
            source_segment_ids=tuple(s.segment_id for s in scoped.segments),
            generation_attempted=self.generation_attempted,
            seconds=time.monotonic() - started,
            accepted=len(accepted),
            rejected=rejected,
            issue_codes=tuple(dict.fromkeys(codes)),
            context_tokens=self.settings.context_tokens,
            timeout_seconds=self.settings.timeout_seconds,
            max_output_tokens=self.settings.max_output_tokens,
            source_segments=len(scoped.segments),
            prompt_bytes=size,
        )
        try:
            findings = (
                merge_ai(
                    baseline, tuple(accepted), info.configuration_digest + info.pipeline_digest
                )
                if accepted
                else baseline.findings
            )
        except Exception:
            findings = baseline.findings
            info = info.model_copy(
                update={
                    "state": "error",
                    "accepted": 0,
                    "issue_codes": (*info.issue_codes, "merge_refused"),
                }
            )
            state = "error"
        incomplete = list(baseline.incomplete_reasons)
        if state in ("timeout", "error") or rejected:
            incomplete.append(
                "Optional local AI did not complete reliably or rejected "
                "source-unverified suggestions; "
                "E1/E2 findings are retained and human source inspection is required."
            )
        red = sum(f.color == "red" for f in findings)
        yellow = len(findings) - red
        color = "red" if red else "yellow" if yellow or incomplete else "green"
        label = (
            "Flag identified"
            if red
            else "Incomplete"
            if incomplete
            else "Potential flag"
            if yellow
            else "No flags found"
        )
        return PaperResult.model_validate(
            baseline.model_dump()
            | {
                "findings": findings,
                "color": color,
                "label": label,
                "flag_count": FlagCount(total=len(findings), red=red, yellow=yellow),
                "incomplete_reasons": tuple(dict.fromkeys(incomplete)),
                "ai_state": state,
                "ai": info,
                "seconds": baseline.seconds + time.monotonic() - started,
            }
        )

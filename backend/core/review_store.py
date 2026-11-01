"""Append-only decisions, revision preconditions, and audited undo. No finding mutation."""

from __future__ import annotations

import os
from collections import defaultdict
from datetime import UTC, datetime
from uuid import uuid4

from backend.core.batch_folders import BatchFolders
from backend.core.batch_models import BatchEntry, ReviewCommand, ReviewEvent, ReviewState
from backend.core.run_store import RunStore
from backend.core.semantic_models import FeedbackExample, FeedbackReference


class ReviewConflict(ValueError):
    pass


class ReviewStore:
    def __init__(self, runs: RunStore, folders: BatchFolders | None = None) -> None:
        self.runs = runs
        self.folders = folders

    def _events(self, run_id: str) -> tuple[ReviewEvent, ...]:
        path = self.runs.path(run_id) / "decisions.jsonl"
        if not path.exists():
            return ()
        return tuple(
            ReviewEvent.model_validate_json(line) for line in path.read_bytes().splitlines()
        )

    @staticmethod
    def _active(events: tuple[ReviewEvent, ...]) -> dict[str | None, list[ReviewEvent]]:
        stacks: dict[str | None, list[ReviewEvent]] = {}
        for event in events:
            stack = stacks.setdefault(event.finding_id, [])
            if event.action == "undo":
                if not stack or stack[-1].event_id != event.target_event:
                    raise ValueError("Review audit history is inconsistent")
                stack.pop()
            else:
                stack.append(event)
        return stacks

    def state(self, run_id: str, entry_id: str) -> ReviewState:
        with self.runs.lock:
            batch = self.runs.read(run_id)
            entry = next((e for e in batch.entries if e.entry_id == entry_id), None)
            if entry is None:
                raise KeyError(entry_id)
            events = tuple(e for e in self._events(run_id) if e.entry_id == entry_id)
            state = self._state(entry, events)
            return self.folders.decorate(batch, entry, state) if self.folders else state

    def states(self, run_id: str) -> dict[str, ReviewState]:
        """Read a run's audit log once, rather than once for every paper."""
        with self.runs.lock:
            batch = self.runs.read(run_id)
            grouped: dict[str, list[ReviewEvent]] = defaultdict(list)
            for event in self._events(run_id):
                grouped[event.entry_id].append(event)
            states = {
                entry.entry_id: self._state(entry, tuple(grouped[entry.entry_id]))
                for entry in batch.entries
            }
            return {
                entry.entry_id: self.folders.decorate(batch, entry, states[entry.entry_id])
                if self.folders
                else states[entry.entry_id]
                for entry in batch.entries
            }

    @classmethod
    def _state(cls, entry: BatchEntry, events: tuple[ReviewEvent, ...]) -> ReviewState:
        active = cls._active(events)
        findings = {f.finding_id: f for f in entry.result.findings} if entry.result else {}
        examples: list[FeedbackExample] = []
        for stack in active.values():
            reference = stack[-1].feedback if stack else None
            if reference is not None and entry.result is not None:
                finding = findings.get(reference.finding_id)
                if finding is None or reference.finding_id != stack[-1].finding_id:
                    raise ValueError("Review feedback source is inconsistent")
                examples.append(
                    FeedbackExample(
                        **reference.model_dump(),
                        paper_id=finding.paper_id,
                        rules_version=entry.result.rules_version,
                        items=finding.items,
                        quote=finding.quote,
                    )
                )
        approval = next(
            (event for event in reversed(active.get(None, [])) if event.action == "approve"), None
        )
        decisions = {key: stack[-1] for key, stack in active.items() if key and stack}
        all_flags_reviewed = findings.keys() <= decisions.keys()
        return ReviewState(
            revision=len(events),
            decisions=decisions,
            inspected=bool(active.get(None)) and all_flags_reviewed,
            approved=approval is not None,
            approval_event=approval,
            events=events,
            feedback_examples=tuple(examples),
        )

    def apply(self, run_id: str, entry_id: str, command: ReviewCommand) -> ReviewState:
        with self.runs.lock:
            entry = self.runs.entry(run_id, entry_id)
            if entry.phase != "done" or entry.result is None:
                raise ReviewConflict("Wait until screening finishes before reviewing")
            state = self.state(run_id, entry_id)
            if state.revision != command.revision:
                raise ReviewConflict("Review changed in another window. Refresh and try again.")
            if command.action in ("accept", "override"):
                if command.finding_id not in {f.finding_id for f in entry.result.findings}:
                    raise ValueError("Finding does not belong to this upload")
                if command.target_event is not None:
                    raise ValueError("Only undo may name a previous event")
            elif command.action in ("inspect", "approve"):
                if command.finding_id is not None or command.target_event is not None:
                    raise ValueError("Paper inspection does not target a finding or event")
                if command.action == "inspect" and any(
                    flag.finding_id not in state.decisions for flag in entry.result.findings
                ):
                    raise ReviewConflict(
                        "Accept or override every flag before recording source inspection"
                    )
                if command.action == "approve" and (
                    entry.result.color != "green"
                    or entry.result.incomplete_reasons
                    or entry.result.flag_count.total
                    or state.approved
                ):
                    raise ReviewConflict("Only an unapproved, complete green paper can be approved")
            else:
                active = self._active(state.events).get(command.finding_id, [])
                if (
                    not active
                    or active[-1].event_id != command.target_event
                    or active[-1].reviewer != command.reviewer
                ):
                    raise ReviewConflict("Only your current decision can be undone")
            batch = self.runs.read(run_id)
            if self.folders and (
                command.action == "approve"
                or (
                    command.action == "undo"
                    and state.approval_event
                    and command.target_event == state.approval_event.event_id
                )
            ):
                self.folders.synchronize(batch, entry, state)
            feedback = None
            if command.action in ("accept", "override"):
                finding = next(
                    f for f in entry.result.findings if f.finding_id == command.finding_id
                )
                feedback = FeedbackReference(
                    finding_id=finding.finding_id,
                    polarity="positive" if command.action == "accept" else "negative",
                )
            event = ReviewEvent(
                event_id=uuid4().hex,
                entry_id=entry_id,
                finding_id=command.finding_id,
                action=command.action,
                reason=command.reason,
                reviewer=command.reviewer.strip(),
                utc=datetime.now(UTC),
                target_event=command.target_event,
                feedback=feedback,
            )
            path = self.runs.path(run_id) / "decisions.jsonl"
            with path.open("ab") as handle:
                os.chmod(path, 0o600)
                handle.write(event.model_dump_json().encode() + b"\n")
                handle.flush()
                os.fsync(handle.fileno())
            if self.folders:
                updated = self._state(entry, (*state.events, event))
                self.folders.attempt(batch, entry, updated)
            return self.state(run_id, entry_id)

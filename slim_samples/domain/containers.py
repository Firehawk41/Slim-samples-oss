"""Containers and their custody (S-02, S-05).

A sample arrives in one or more containers (bottles). What was received is one immutable record; what
happens afterwards (moved, condition noted, corrected, held, disposed, returned) is an append-only list
of events. Where a container is, what state it is in and whether it is due for disposal are all
*derived* by folding the events, so history is never overwritten.
"""

from collections.abc import Sequence
from datetime import date, datetime
from enum import IntEnum
from typing import Protocol

from pydantic import Field

from slim_samples.domain.base import Frozen
from slim_samples.domain.problems import Problem, Refused
from slim_samples.domain.rules import Effect, SamplesRules


class SampleInfo(Frozen):
    """What the host tells us about a lab sample (the TR is the host's; slim-samples never reads it)."""

    sample: str  # the lab sample ID, e.g. TR00042-01
    analyses: frozenset[str] = frozenset()  # analysis codes ordered for it
    customer: str = ""  # the host's key for the customer (retention overrides use it)


class SampleLookup(Protocol):
    def sample(self, sample_id: str) -> SampleInfo | None: ...


class ContainerIn(Frozen):
    """One row of the check-in section: how many bottles of one kind, in what state, where, for what."""

    container_type: str
    count: int = Field(default=1, ge=1, le=999)
    conditions: frozenset[str] = frozenset()
    location: str
    analyses: frozenset[str] = frozenset()  # empty: every analysis ordered for the sample
    note: str = Field(default="", max_length=500)


class ConditionRecord(Frozen):
    """A condition as it was when noted: label and effect are copied, so a later change to the lab's
    rules never rewrites what a past container meant."""

    code: str
    label: str
    effect: Effect


class EventKind(IntEnum):
    MOVED = 1
    CONDITION = 2  # the set of conditions noted now (replaces the earlier set; the earlier stays in history)
    CORRECTED = 3  # a wrong type, count or analyses entered at check-in
    HOLD = 4  # keep it: an open complaint or nonconformity
    RELEASE = 5  # the hold is lifted
    DISPOSED = 6
    RETURNED = 7


FINAL = {EventKind.DISPOSED, EventKind.RETURNED}


class Event(Frozen):
    kind: EventKind
    at: datetime
    by_id: str
    by: str
    location: str | None = None
    conditions: tuple[ConditionRecord, ...] | None = None
    container_type: str | None = None
    type_label: str | None = None
    count: int | None = None
    analyses: frozenset[str] | None = None
    method: str | None = None
    reason: str | None = None


class Container(Frozen):
    id: int
    sample: str
    position: int  # 1, 2, ... within the sample
    container_type: str
    type_label: str
    count: int
    analyses: frozenset[str]
    received_on: date
    retention_due: date
    customer: str
    rules_id: int
    note: str = ""
    conditions: tuple[ConditionRecord, ...] = ()
    location: str  # where it was put on receipt
    received_at: datetime
    received_by_id: str
    received_by: str
    events: tuple[Event, ...] = ()

    # ---- derived: fold the events -------------------------------------------------------------

    def _last(self, *kinds: EventKind) -> Event | None:
        return next((e for e in reversed(self.events) if e.kind in kinds), None)

    @property
    def outcome(self) -> EventKind | None:
        final = self._last(*FINAL)
        return None if final is None else final.kind

    @property
    def active(self) -> bool:
        return self.outcome is None

    @property
    def current_location(self) -> str | None:
        if not self.active:
            return None
        moved = self._last(EventKind.MOVED)
        return moved.location if moved else self.location

    @property
    def current_conditions(self) -> tuple[ConditionRecord, ...]:
        noted = self._last(EventKind.CONDITION)
        return noted.conditions or () if noted else self.conditions

    @property
    def current_type(self) -> tuple[str, str]:
        fix = next(
            (e for e in reversed(self.events) if e.kind == EventKind.CORRECTED and e.container_type), None
        )
        return (
            (fix.container_type, fix.type_label or fix.container_type)
            if fix
            else (
                self.container_type,
                self.type_label,
            )
        )

    @property
    def current_count(self) -> int:
        fix = next((e for e in reversed(self.events) if e.kind == EventKind.CORRECTED and e.count), None)
        return fix.count if fix else self.count

    @property
    def current_analyses(self) -> frozenset[str]:
        fix = next(
            (e for e in reversed(self.events) if e.kind == EventKind.CORRECTED and e.analyses is not None),
            None,
        )
        return fix.analyses if fix else self.analyses

    @property
    def held(self) -> bool:
        last = self._last(EventKind.HOLD, EventKind.RELEASE)
        return last is not None and last.kind == EventKind.HOLD

    @property
    def hold_reason(self) -> str:
        last = self._last(EventKind.HOLD, EventKind.RELEASE)
        return (last.reason or "") if last is not None and last.kind == EventKind.HOLD else ""

    @property
    def finished_on(self) -> datetime | None:
        final = self._last(*FINAL)
        return None if final is None else final.at

    @property
    def worst_effect(self) -> Effect:
        return max((c.effect for c in self.current_conditions), default=Effect.NONE)

    def due(self, today: date, within_days: int = 0) -> bool:
        """Active, not held, and its retention ends on or before today (+ `within_days` ahead)."""
        return self.active and not self.held and (self.retention_due - today).days <= within_days

    def overdue(self, today: date) -> bool:
        return self.active and not self.held and self.retention_due < today

    @property
    def title(self) -> str:
        return f"bottle {self.position}: {self.current_count} × {self.current_type[1]}"


class Flag(Frozen):
    """A condition that touches an analysis: the report and the review screen say so (S-04)."""

    analysis: str
    container: int  # the bottle's position within the sample
    effect: Effect
    text: str


def flags(
    containers: Sequence[Container], analyses: Sequence[str] | None = None
) -> dict[str, tuple[Flag, ...]]:
    """Per analysis, every condition (that is not recorded-only) of the bottles that serve it.
    A finished (disposed or returned) bottle still counts: what happened to the result stays true."""
    found: dict[str, list[Flag]] = {}
    for c in containers:
        for cond in c.current_conditions:
            if cond.effect == Effect.NONE:
                continue
            for analysis in sorted(c.current_analyses):
                if analyses is not None and analysis not in analyses:
                    continue
                text = f"{cond.label}: {c.title}"
                found.setdefault(analysis, []).append(
                    Flag(analysis=analysis, container=c.position, effect=cond.effect, text=text)
                )
    return {a: tuple(v) for a, v in found.items()}


def blocked(containers: Sequence[Container]) -> dict[str, tuple[Flag, ...]]:
    """The analyses no prep batch may use until the lab acts (Effect.BLOCK on a bottle that serves it
    and is still in the lab)."""
    live = [c for c in containers if c.active]
    return {
        a: tuple(f for f in fl if f.effect == Effect.BLOCK)
        for a, fl in flags(live).items()
        if any(f.effect == Effect.BLOCK for f in fl)
    }


class Planned(Frozen):
    """A checked row, ready to be recorded: codes resolved to their labels and the analyses spelt out."""

    position: int
    container_type: str
    type_label: str
    count: int
    conditions: tuple[ConditionRecord, ...]
    location: str
    analyses: frozenset[str]
    note: str


def condition_records(codes: frozenset[str], rules: SamplesRules, where: str, problems: list[Problem]):
    records = []
    for code in sorted(codes):
        cond = rules.condition(code)
        if cond is None:
            problems.append(Problem(where=where, message=f"unknown condition {code!r}"))
        else:
            records.append(ConditionRecord(code=cond.code, label=cond.label, effect=cond.effect))
    return tuple(records)


def plan_receipt(
    info: SampleInfo, items: Sequence[ContainerIn], rules: SamplesRules, *, first_position: int = 1
) -> list[Planned]:
    """Check what staff logged at check-in against the lab's rules and the sample's analyses.
    Refuses with every problem found, each saying which row and field."""
    problems: list[Problem] = []
    if not items:
        raise Refused(Problem(where="containers", message="log at least one container: how many, what kind"))
    planned: list[Planned] = []
    covered: set[str] = set()
    for i, item in enumerate(items):
        where = f"containers[{i}]"
        ctype = rules.container_type(item.container_type)
        if ctype is None:
            problems.append(
                Problem(where=f"{where}.container_type", message=f"unknown type {item.container_type!r}")
            )
        if rules.location(item.location) is None:
            problems.append(Problem(where=f"{where}.location", message=f"unknown location {item.location!r}"))
        conditions = condition_records(item.conditions, rules, f"{where}.conditions", problems)
        stray = item.analyses - info.analyses if info.analyses else frozenset()
        if stray:
            problems.append(
                Problem(
                    where=f"{where}.analyses",
                    message=f"not ordered for {info.sample}: {', '.join(sorted(stray))}",
                )
            )
        serves = item.analyses or info.analyses
        covered |= serves
        if ctype is not None:
            planned.append(
                Planned(
                    position=first_position + i,
                    container_type=ctype.code,
                    type_label=ctype.label,
                    count=item.count,
                    conditions=conditions,
                    location=item.location,
                    analyses=frozenset(serves),
                    note=item.note.strip(),
                )
            )
    missing = info.analyses - covered
    if missing:
        problems.append(
            Problem(where="containers", message=f"no container is logged for: {', '.join(sorted(missing))}")
        )
    if problems:
        raise Refused(problems)
    return planned


class Label(Frozen):
    """What a bottle's label prints (S-06): readable now, a barcode later (the code is already unique)."""

    code: str  # e.g. TR00042-01/2
    sample: str
    bottle: str  # "2 of 3"
    kind: str
    count: int
    received_on: date
    keep_until: date


def label_for(container: Container, of: int) -> Label:
    return Label(
        code=f"{container.sample}/{container.position}",
        sample=container.sample,
        bottle=f"{container.position} of {of}",
        kind=container.current_type[1],
        count=container.current_count,
        received_on=container.received_on,
        keep_until=container.retention_due,
    )

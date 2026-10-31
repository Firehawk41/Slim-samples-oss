"""What the host calls to receive containers and to keep their custody (S-02, S-05, S-08).

The host owns the transaction: these flush, the caller commits. Every write takes the actor and, where
a person could get it wrong, a reason. A finished container (disposed or returned) takes no more events.
"""

from collections.abc import Sequence
from datetime import date

from sqlalchemy.orm import Session

from slim_samples.domain.actor import Actor
from slim_samples.domain.containers import (
    Container,
    ContainerIn,
    EventKind,
    Flag,
    Label,
    SampleLookup,
    blocked,
    condition_records,
    flags,
    label_for,
    plan_receipt,
)
from slim_samples.domain.problems import Problem, Refused
from slim_samples.persistence import store
from slim_samples.persistence._rows import NotAllowed, NotFound
from slim_samples.persistence.rules import PublishedRules, get_rules
from slim_samples.persistence.tables import containers as containers_table


def _staff(actor: Actor) -> None:
    if not actor.roles:
        raise NotAllowed(f"{actor.display} has no lab role: only lab staff handle samples")


def _reason(reason: str, what: str) -> str:
    reason = (reason or "").strip()
    if not reason:
        raise Refused(Problem(where="reason", message=f"say why: {what}"))
    return reason


# ---------------------------------------------------------------------------- reading


def containers_of(session: Session, sample: str) -> list[Container]:
    return store.load(session, containers_table.c.sample == sample)


def containers_for(session: Session, samples: Sequence[str]) -> dict[str, list[Container]]:
    """Several samples in one go (a request page, the board): two queries, not two per sample."""
    found: dict[str, list[Container]] = {s: [] for s in samples}
    if samples:
        for c in store.load(session, containers_table.c.sample.in_(list(samples))):
            found[c.sample].append(c)
    return found


def get_container(session: Session, container_id: int) -> Container:
    found = store.load(session, ids=[container_id])
    if not found:
        raise NotFound(f"no container {container_id}")
    return found[0]


def active_containers(session: Session) -> list[Container]:
    """Everything still in the lab (not disposed or returned)."""
    return [c for c in store.load(session) if c.active]


def due_for_disposal(session: Session, today: date, within_days: int = 0) -> list[Container]:
    """Retention ends on or before today (+ `within_days` ahead); held ones are left out (S-09)."""
    from datetime import timedelta

    horizon = today + timedelta(days=within_days)
    return [
        c
        for c in store.load(session, containers_table.c.retention_due <= horizon)
        if c.due(today, within_days)
    ]


def flags_for(
    session: Session, sample: str, analyses: Sequence[str] | None = None
) -> dict[str, tuple[Flag, ...]]:
    """Per analysis, the conditions of the bottles that serve it: the review screen and report warnings."""
    return flags(containers_of(session, sample), analyses)


def blocked_for(session: Session, sample: str) -> dict[str, tuple[Flag, ...]]:
    return blocked(containers_of(session, sample))


def labels_for(session: Session, sample: str) -> list[Label]:
    found = containers_of(session, sample)
    return [label_for(c, len(found)) for c in found]


# ---------------------------------------------------------------------------- receiving


def receive(
    session: Session,
    lookup: SampleLookup,
    sample: str,
    items: Sequence[ContainerIn],
    *,
    actor: Actor,
    rules: PublishedRules,
    received_on: date,
) -> list[Container]:
    """Log how many and what kind of bottles arrived for a sample, once (S-02). Refuses nothing logged,
    an unknown type / location / condition, and an ordered analysis no bottle serves."""
    _staff(actor)
    if containers_of(session, sample):
        raise Refused(Problem(where=sample, message="already received; add a bottle if another arrived"))
    return _insert(session, lookup, sample, items, actor=actor, rules=rules, received_on=received_on)


def add_container(
    session: Session,
    lookup: SampleLookup,
    sample: str,
    items: Sequence[ContainerIn],
    *,
    actor: Actor,
    rules: PublishedRules,
    received_on: date,
    reason: str,
) -> list[Container]:
    """Another bottle arrived for a sample that is already received."""
    _staff(actor)
    _reason(reason, "why another bottle was added")
    existing = containers_of(session, sample)
    if not existing:
        raise Refused(Problem(where=sample, message="not received yet; receive it first"))
    return _insert(
        session, lookup, sample, items, actor=actor, rules=rules, received_on=received_on, existing=existing
    )


def _insert(session, lookup, sample, items, *, actor, rules, received_on, existing=()):
    info = lookup.sample(sample)
    if info is None:
        raise Refused(Problem(where=sample, message="no such sample"))
    first = max((c.position for c in existing), default=0) + 1
    # Later bottles are checked against what they serve; coverage is judged on the first receipt only.
    base = info if not existing else info.model_copy(update={"analyses": frozenset()})
    plans = plan_receipt(base, items, rules.rules, first_position=first)
    if existing:
        stray = {a for p in plans for a in p.analyses} - info.analyses
        if stray:
            raise Refused(
                Problem(where="containers", message=f"not ordered for {sample}: {', '.join(sorted(stray))}")
            )
        plans = [p.model_copy(update={"analyses": p.analyses or info.analyses}) for p in plans]
    due = rules.rules.retention_due(received_on, info.customer)
    ids = [
        store.insert_container(
            session,
            p,
            sample=sample,
            customer=info.customer,
            rules_id=rules.id,
            received_on=received_on,
            retention_due=due,
            actor=actor,
        )
        for p in plans
    ]
    session.flush()
    return store.load(session, ids=ids)


# ---------------------------------------------------------------------------- custody


def _open(session: Session, container_id: int) -> Container:
    container = get_container(session, container_id)
    if not container.active:
        verb = "disposed of" if container.outcome == EventKind.DISPOSED else "returned to the customer"
        raise Refused(Problem(where=container.title, message=f"already {verb}"))
    return container


def move(
    session: Session,
    container_id: int,
    location: str,
    *,
    actor: Actor,
    rules: PublishedRules,
    reason: str = "",
):
    _staff(actor)
    container = _open(session, container_id)
    if rules.rules.location(location) is None:
        raise Refused(Problem(where="location", message=f"unknown location {location!r}"))
    if location == container.current_location:
        raise Refused(Problem(where="location", message="it is already there"))
    store.insert_event(
        session,
        container_id,
        EventKind.MOVED,
        actor,
        location=location,
        body={"reason": reason.strip() or None},
    )
    session.flush()
    return get_container(session, container_id)


def note_conditions(
    session: Session,
    container_id: int,
    codes: frozenset[str],
    *,
    actor: Actor,
    rules: PublishedRules,
    reason: str,
):
    """Replace the conditions noted on a bottle (found cracked later, a mistake at the door). The earlier
    set stays in the history; the reason is required."""
    _staff(actor)
    _reason(reason, "what changed")
    _open(session, container_id)
    problems: list[Problem] = []
    records = condition_records(frozenset(codes), rules.rules, "conditions", problems)
    if problems:
        raise Refused(problems)
    store.insert_event(
        session,
        container_id,
        EventKind.CONDITION,
        actor,
        body={"conditions": [r.model_dump(mode="json") for r in records], "reason": reason.strip()},
    )
    session.flush()
    return get_container(session, container_id)


def correct(
    session: Session,
    lookup: SampleLookup,
    container_id: int,
    *,
    actor: Actor,
    rules: PublishedRules,
    reason: str,
    container_type: str | None = None,
    count: int | None = None,
    analyses: frozenset[str] | None = None,
):
    """Fix what was entered at check-in: the kind of bottle, how many, or which analyses it serves."""
    _staff(actor)
    _reason(reason, "what was wrong")
    container = _open(session, container_id)
    if container_type is None and count is None and analyses is None:
        raise Refused(Problem(where="correction", message="nothing to correct"))
    body: dict = {"reason": reason.strip()}
    if container_type is not None:
        ctype = rules.rules.container_type(container_type)
        if ctype is None:
            raise Refused(Problem(where="container_type", message=f"unknown type {container_type!r}"))
        body.update(container_type=ctype.code, type_label=ctype.label)
    if count is not None:
        if not 1 <= count <= 999:
            raise Refused(Problem(where="count", message="between 1 and 999"))
        body["count"] = count
    if analyses is not None:
        info = lookup.sample(container.sample)
        if info is None:
            raise Refused(Problem(where=container.sample, message="no such sample"))
        stray = analyses - info.analyses
        if stray:
            raise Refused(Problem(where="analyses", message=f"not ordered: {', '.join(sorted(stray))}"))
        siblings = [c for c in containers_of(session, container.sample) if c.id != container.id]
        covered = set(analyses or info.analyses)
        for other in siblings:
            covered |= other.current_analyses
        if info.analyses - covered:
            raise Refused(
                Problem(
                    where="analyses",
                    message=f"no container would serve: {', '.join(sorted(info.analyses - covered))}",
                )
            )
        body["analyses"] = sorted(analyses or info.analyses)
    store.insert_event(session, container_id, EventKind.CORRECTED, actor, body=body)
    session.flush()
    return get_container(session, container_id)


def hold(session: Session, container_id: int, *, actor: Actor, reason: str):
    """Keep it past its retention date: an open complaint or nonconformity (S-09)."""
    _staff(actor)
    _reason(reason, "what the hold is for")
    container = _open(session, container_id)
    if container.held:
        raise Refused(Problem(where=container.title, message="already on hold"))
    store.insert_event(session, container_id, EventKind.HOLD, actor, body={"reason": reason.strip()})
    session.flush()
    return get_container(session, container_id)


def release_hold(session: Session, container_id: int, *, actor: Actor, reason: str):
    _staff(actor)
    if not actor.may_release_hold:
        raise NotAllowed(f"{actor.display} may not lift a hold: a supervisor or quality does")
    _reason(reason, "why the hold ends")
    container = _open(session, container_id)
    if not container.held:
        raise Refused(Problem(where=container.title, message="not on hold"))
    store.insert_event(session, container_id, EventKind.RELEASE, actor, body={"reason": reason.strip()})
    session.flush()
    return get_container(session, container_id)


def dispose(
    session: Session,
    container_id: int,
    *,
    actor: Actor,
    rules: PublishedRules,
    method: str,
    today: date,
    reason: str = "",
):
    """Record that a bottle was disposed of. Refused while on hold; before its retention date a reason
    is required."""
    _staff(actor)
    container = _open(session, container_id)
    if container.held:
        raise Refused(Problem(where=container.title, message=f"on hold: {container.hold_reason}"))
    if method not in rules.rules.disposal_methods:
        raise Refused(Problem(where="method", message=f"unknown disposal method {method!r}"))
    if today < container.retention_due:
        _reason(reason, f"it is kept until {container.retention_due.isoformat()}")
    store.insert_event(
        session,
        container_id,
        EventKind.DISPOSED,
        actor,
        body={"method": method, "reason": reason.strip() or None},
    )
    session.flush()
    return get_container(session, container_id)


def return_to_customer(session: Session, container_id: int, *, actor: Actor, note: str = ""):
    _staff(actor)
    container = _open(session, container_id)
    if container.held:
        raise Refused(Problem(where=container.title, message=f"on hold: {container.hold_reason}"))
    store.insert_event(
        session,
        container_id,
        EventKind.RETURNED,
        actor,
        body={"reason": note.strip() or None, "method": "returned"},
    )
    session.flush()
    return get_container(session, container_id)


# ---------------------------------------------------------------------------- checking


def verify(session: Session) -> list[Problem]:
    """Recheck the record: retention dates follow the rules each bottle was received under, positions
    run 1…n per sample, and nothing happens to a bottle after it was disposed of or returned."""
    problems: list[Problem] = []
    everything = store.load(session)
    rules_cache: dict[int, PublishedRules] = {}
    positions: dict[str, list[int]] = {}
    for c in everything:
        positions.setdefault(c.sample, []).append(c.position)
        if c.rules_id not in rules_cache:
            rules_cache[c.rules_id] = get_rules(session, c.rules_id)
        want = rules_cache[c.rules_id].rules.retention_due(c.received_on, c.customer)
        if want != c.retention_due:
            problems.append(
                Problem(
                    where=f"{c.sample}/{c.position}",
                    message=f"retention is {c.retention_due}, rules give {want}",
                )
            )
        final_seen = False
        for e in c.events:
            if final_seen:
                problems.append(
                    Problem(where=f"{c.sample}/{c.position}", message="an event after it was finished")
                )
                break
            final_seen = e.kind in (EventKind.DISPOSED, EventKind.RETURNED)
    for sample, found in positions.items():
        if sorted(found) != list(range(1, len(found) + 1)):
            problems.append(
                Problem(where=sample, message=f"bottle numbers {sorted(found)} aren't 1…{len(found)}")
            )
    return problems

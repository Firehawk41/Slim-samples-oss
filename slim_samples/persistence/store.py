"""The containers and events tables as domain objects. The only writer of both; insert-only."""

from collections.abc import Iterable
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from slim_samples.domain.actor import Actor
from slim_samples.domain.containers import ConditionRecord, Container, Event, EventKind, Planned
from slim_samples.persistence._rows import actor_json
from slim_samples.persistence.audit import set_change_context
from slim_samples.persistence.tables import containers, events


def insert_container(
    session: Session,
    plan: Planned,
    *,
    sample: str,
    customer: str,
    rules_id: int,
    received_on: date,
    retention_due: date,
    actor: Actor,
) -> int:
    set_change_context(session, actor, f"receive {sample} bottle {plan.position}")
    result = session.execute(
        containers.insert().values(
            sample=sample,
            position=plan.position,
            container_type=plan.container_type,
            type_label=plan.type_label,
            count=plan.count,
            rules_id=rules_id,
            customer=customer,
            received_on=received_on,
            retention_due=retention_due,
            location=plan.location,
            conditions=[c.model_dump(mode="json") for c in plan.conditions],
            analyses=sorted(plan.analyses),
            note=plan.note,
            received_by_id=actor.id,
            received_by=actor_json(actor),
        )
    )
    return result.inserted_primary_key[0]


def insert_event(
    session: Session,
    container_id: int,
    kind: EventKind,
    actor: Actor,
    *,
    location: str | None = None,
    body: dict | None = None,
    why: str = "",
) -> None:
    set_change_context(session, actor, why or f"{kind.name.lower()} container {container_id}")
    session.execute(
        events.insert().values(
            container_id=container_id,
            kind=int(kind),
            location=location,
            body=body or {},
            by_id=actor.id,
            by=actor_json(actor),
        )
    )


def next_position(session: Session, sample: str) -> int:
    top = session.scalar(select(func.max(containers.c.position)).where(containers.c.sample == sample))
    return (top or 0) + 1


def load(session: Session, *where, ids: Iterable[int] | None = None) -> list[Container]:
    """Containers matching the conditions, oldest first, each with its events: two queries in all."""
    query = select(containers).order_by(containers.c.sample, containers.c.position)
    if where:
        query = query.where(*where)
    if ids is not None:
        query = query.where(containers.c.id.in_(list(ids)))
    rows = session.execute(query).all()
    if not rows:
        return []
    by_container: dict[int, list[Event]] = {r.id: [] for r in rows}
    for ev in session.execute(
        select(events).where(events.c.container_id.in_(list(by_container))).order_by(events.c.id)
    ):
        by_container[ev.container_id].append(_event(ev))
    return [_container(r, tuple(by_container[r.id])) for r in rows]


def _container(row, evs: tuple[Event, ...]) -> Container:
    return Container(
        id=row.id,
        sample=row.sample,
        position=row.position,
        container_type=row.container_type,
        type_label=row.type_label,
        count=row.count,
        analyses=frozenset(row.analyses),
        received_on=row.received_on,
        retention_due=row.retention_due,
        customer=row.customer,
        rules_id=row.rules_id,
        note=row.note,
        conditions=tuple(ConditionRecord.model_validate(c) for c in row.conditions),
        location=row.location,
        received_at=row.created_at,
        received_by_id=row.received_by_id,
        received_by=row.received_by["display"],
        events=evs,
    )


def _event(row) -> Event:
    body = row.body or {}
    conditions = body.get("conditions")
    analyses = body.get("analyses")
    return Event(
        kind=EventKind(row.kind),
        at=row.created_at,
        by_id=row.by_id,
        by=row.by["display"],
        location=row.location,
        conditions=None
        if conditions is None
        else tuple(ConditionRecord.model_validate(c) for c in conditions),
        container_type=body.get("container_type"),
        type_label=body.get("type_label"),
        count=body.get("count"),
        analyses=None if analyses is None else frozenset(analyses),
        method=body.get("method"),
        reason=body.get("reason"),
    )

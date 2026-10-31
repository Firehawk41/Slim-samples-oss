"""Publishing the lab's sample rules (S-03): numbered, content-hashed, immutable. Publishing the same content
again returns the existing row. Only quality, or a supervisor standing in."""

import hashlib
import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from slim_samples.domain.actor import Actor
from slim_samples.domain.base import Frozen
from slim_samples.domain.rules import SamplesRules
from slim_samples.persistence._rows import NotAllowed, NotFound, actor_json, as_of_filter
from slim_samples.persistence.audit import set_change_context
from slim_samples.persistence.tables import samples_rules


class PublishedRules(Frozen):
    id: int
    rules: SamplesRules
    published_at: datetime


def content_hash(rules: SamplesRules) -> str:
    canonical = json.dumps(rules.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def publish_rules(session: Session, rules: SamplesRules, actor: Actor) -> PublishedRules:
    if not actor.may_publish_rules:
        raise NotAllowed(
            f"{actor.display} may not publish sample rules: the lab's quality side sets them (S-03)"
        )
    digest = content_hash(rules)
    if session.scalar(select(samples_rules.c.id).where(samples_rules.c.content_hash == digest)) is None:
        set_change_context(session, actor, f"publish sample rules {rules.name}")
        session.execute(
            samples_rules.insert().values(
                name=rules.name,
                content_hash=digest,
                body=rules.model_dump(mode="json"),
                published_by_id=actor.id,
                published_by=actor_json(actor),
            )
        )
    return _published(
        session.execute(select(samples_rules).where(samples_rules.c.content_hash == digest)).one()
    )


def get_rules(session: Session, id: int) -> PublishedRules:
    row = session.execute(select(samples_rules).where(samples_rules.c.id == id)).one_or_none()
    if row is None:
        raise NotFound(f"no published the sample rules {id}")
    return _published(row)


def current_rules(session: Session, name: str, as_of: datetime | None = None) -> PublishedRules | None:
    """The latest rules of that name published by `as_of` (default: now)."""
    row = session.execute(
        select(samples_rules)
        .where(samples_rules.c.name == name, as_of_filter(samples_rules.c.created_at, as_of))
        .order_by(samples_rules.c.created_at.desc(), samples_rules.c.id.desc())
        .limit(1)
    ).one_or_none()
    return None if row is None else _published(row)


def _published(row) -> PublishedRules:
    return PublishedRules(id=row.id, rules=SamplesRules.model_validate(row.body), published_at=row.created_at)

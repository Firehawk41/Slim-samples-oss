"""slim-samples' tables (S-07). Every one is append-only: rows are inserted, never updated or deleted,
enforced by the repositories (no update path) and by triggers (`append_only.py`).

* `samples_rules`: the lab's lists and periods, published once per content (hash).
* `samples_containers`: what was received, one row per kind of bottle. Never changed.
* `samples_events`: everything that happens afterwards. Where a bottle is, whether it is held or
  finished is derived from these, so the custody chain can't be quietly rewritten.

Names start `samples_`: the database is shared. Portable: enums as ints, JSON via `JSON`, no ARRAY, no
foreign keys into other modules' tables (the sample is a string, the TR's lab sample ID).
"""

from sqlalchemy import JSON, Column, Date, ForeignKey, Integer, String, Table, Text, UniqueConstraint

from slim_samples.persistence.db import Base
from slim_samples.persistence.types import UtcDateTime, db_now

metadata = Base.metadata

samples_rules = Table(
    "samples_rules",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(100), nullable=False),
    Column("content_hash", String(64), nullable=False, unique=True),
    Column("body", JSON, nullable=False),
    Column("published_by_id", String(100), nullable=False),
    Column("published_by", JSON, nullable=False),
    Column("created_at", UtcDateTime(), nullable=False, server_default=db_now()),
)

containers = Table(
    "samples_containers",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("sample", String(40), nullable=False),
    Column("position", Integer, nullable=False),
    Column("container_type", String(40), nullable=False),
    Column("type_label", String(100), nullable=False),
    Column("count", Integer, nullable=False),
    Column("rules_id", Integer, ForeignKey("samples_rules.id"), nullable=False),
    Column("customer", String(100), nullable=False, server_default=""),
    Column("received_on", Date, nullable=False),
    Column("retention_due", Date, nullable=False, index=True),
    Column("location", String(40), nullable=False),
    Column("conditions", JSON, nullable=False),
    Column("analyses", JSON, nullable=False),
    Column("note", Text, nullable=False, server_default=""),
    Column("received_by_id", String(100), nullable=False),
    Column("received_by", JSON, nullable=False),
    Column("created_at", UtcDateTime(), nullable=False, server_default=db_now()),
    UniqueConstraint("sample", "position"),
)

events = Table(
    "samples_events",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("container_id", Integer, ForeignKey("samples_containers.id"), nullable=False, index=True),
    Column("kind", Integer, nullable=False),
    Column("location", String(40), nullable=True),
    Column("body", JSON, nullable=False),
    Column("by_id", String(100), nullable=False),
    Column("by", JSON, nullable=False),
    Column("created_at", UtcDateTime(), nullable=False, server_default=db_now()),
)

TABLES = ("samples_rules", "samples_containers", "samples_events")

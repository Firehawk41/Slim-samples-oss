"""Migrations: only slim-samples' tables, its own version table, append-only by trigger."""

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError

from slim_samples.persistence import migrate
from slim_samples.persistence.tables import TABLES
from tests.factories import ANALYST, LOOKUP, S1, TODAY, bottle, rules


def test_creates_its_tables_and_its_own_version_table(session):
    names = set(inspect(session.connection()).get_table_names())
    assert set(TABLES) <= names
    assert migrate.VERSION_TABLE in names
    assert {n for n in names if not n.startswith("samples_")} == {migrate.VERSION_TABLE}


def test_upgrade_is_repeatable_and_downgrades(session):
    migrate.upgrade(session.connection())
    migrate.downgrade(session.connection())
    assert not set(TABLES) & set(inspect(session.connection()).get_table_names())


@pytest.mark.parametrize(
    "sql",
    ["UPDATE samples_containers SET count = 9", "DELETE FROM samples_events", "DELETE FROM samples_rules"],
)
def test_every_table_refuses_update_and_delete(session, sql):
    from slim_samples.service import custody

    r = rules(session)
    custody.receive(session, LOOKUP, S1, [bottle()], actor=ANALYST, rules=r, received_on=TODAY)
    custody.hold(session, custody.containers_of(session, S1)[0].id, actor=ANALYST, reason="x")
    with pytest.raises(DBAPIError, match="append-only"):
        session.execute(text(sql))

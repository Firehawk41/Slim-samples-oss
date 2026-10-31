from datetime import timedelta

import pytest

from slim_samples.demo import DEMO_RULES
from slim_samples.domain.containers import EventKind
from slim_samples.domain.problems import Refused
from slim_samples.domain.rules import Effect
from slim_samples.persistence._rows import NotAllowed, NotFound
from slim_samples.service import custody
from slim_samples.service.rules import current_rules, publish_rules
from tests.factories import (
    ANALYST,
    LOOKUP,
    NOBODY,
    QUALITY,
    S1,
    SUPERVISOR,
    TODAY,
    bottle,
    rules,
)


@pytest.fixture
def r(session):
    return rules(session)


def receive(session, r, items=None, sample=S1, actor=ANALYST):
    return custody.receive(
        session, LOOKUP, sample, items or [bottle()], actor=actor, rules=r, received_on=TODAY
    )


def test_receive_records_bottles_with_a_retention_date(session, r):
    (c,) = receive(session, r, [bottle(count=3, conditions=frozenset({"leaking"}))])
    assert (c.sample, c.position, c.current_count, c.current_location) == (S1, 1, 3, "receiving")
    assert c.retention_due == TODAY + timedelta(days=90) and c.received_by == "Ana Analyst" and c.active
    assert [x.code for x in c.current_conditions] == ["leaking"]


def test_a_customer_override_sets_a_longer_retention(session, r):
    (c,) = receive(session, r, sample="TR00001-02")
    assert c.retention_due == TODAY + timedelta(days=365)


def test_receiving_twice_is_refused_but_a_late_bottle_can_be_added_with_a_reason(session, r):
    receive(session, r)
    with pytest.raises(Refused, match="already received"):
        receive(session, r)
    with pytest.raises(Refused, match="say why"):
        custody.add_container(
            session,
            LOOKUP,
            S1,
            [bottle(analyses=frozenset({"IC-ANIONS"}))],
            actor=ANALYST,
            rules=r,
            received_on=TODAY,
            reason=" ",
        )
    (b,) = custody.add_container(
        session,
        LOOKUP,
        S1,
        [bottle(container_type="pfa", analyses=frozenset({"IC-ANIONS"}))],
        actor=ANALYST,
        rules=r,
        received_on=TODAY,
        reason="second bottle came by courier",
    )
    assert b.position == 2 and custody.verify(session) == []


def test_add_container_to_an_unreceived_sample_or_for_an_unordered_analysis_is_refused(session, r):
    with pytest.raises(Refused, match="not received yet"):
        custody.add_container(
            session, LOOKUP, S1, [bottle()], actor=ANALYST, rules=r, received_on=TODAY, reason="x"
        )
    receive(session, r)
    with pytest.raises(Refused, match="not ordered"):
        custody.add_container(
            session,
            LOOKUP,
            S1,
            [bottle(analyses=frozenset({"ZZZ"}))],
            actor=ANALYST,
            rules=r,
            received_on=TODAY,
            reason="x",
        )


def test_unknown_sample_and_people_without_a_lab_role_are_refused(session, r):
    with pytest.raises(Refused, match="no such sample"):
        receive(session, r, sample="TR99999-01")
    with pytest.raises(NotAllowed):
        receive(session, r, actor=NOBODY)


def test_move_changes_location_and_keeps_the_history(session, r):
    (c,) = receive(session, r)
    moved = custody.move(session, c.id, "fridge-1", actor=SUPERVISOR, rules=r, reason="needs cold")
    assert moved.current_location == "fridge-1" and moved.location == "receiving"
    assert [e.kind for e in moved.events] == [EventKind.MOVED] and moved.events[0].by == "Sam Supervisor"
    with pytest.raises(Refused, match="already there"):
        custody.move(session, c.id, "fridge-1", actor=ANALYST, rules=r)
    with pytest.raises(Refused, match="unknown location"):
        custody.move(session, c.id, "moon", actor=ANALYST, rules=r)


def test_conditions_can_be_corrected_later_with_a_reason(session, r):
    (c,) = receive(session, r)
    with pytest.raises(Refused, match="say why"):
        custody.note_conditions(session, c.id, frozenset({"cracked"}), actor=ANALYST, rules=r, reason="")
    with pytest.raises(Refused, match="unknown condition"):
        custody.note_conditions(session, c.id, frozenset({"melted"}), actor=ANALYST, rules=r, reason="x")
    c = custody.note_conditions(
        session, c.id, frozenset({"cracked"}), actor=ANALYST, rules=r, reason="found at prep"
    )
    assert [x.code for x in c.current_conditions] == ["cracked"] and c.conditions == ()
    c = custody.note_conditions(session, c.id, frozenset(), actor=ANALYST, rules=r, reason="it was a stain")
    assert c.current_conditions == ()


def test_corrections_change_what_it_is_not_what_was_received(session, r):
    (c,) = receive(session, r, [bottle(count=3)])
    c = custody.correct(
        session, LOOKUP, c.id, actor=ANALYST, rules=r, reason="miscounted", count=2, container_type="pfa"
    )
    assert (c.current_count, c.current_type, c.count, c.container_type) == (
        2,
        ("pfa", "PFA bottle"),
        3,
        "hdpe",
    )
    with pytest.raises(Refused, match="nothing to correct"):
        custody.correct(session, LOOKUP, c.id, actor=ANALYST, rules=r, reason="x")
    with pytest.raises(Refused, match="between 1 and 999"):
        custody.correct(session, LOOKUP, c.id, actor=ANALYST, rules=r, reason="x", count=0)
    with pytest.raises(Refused, match="unknown type"):
        custody.correct(session, LOOKUP, c.id, actor=ANALYST, rules=r, reason="x", container_type="tin")


def test_a_correction_may_not_leave_an_analysis_without_a_bottle(session, r):
    (c,) = receive(session, r)
    with pytest.raises(Refused, match="no container would serve"):
        custody.correct(
            session, LOOKUP, c.id, actor=ANALYST, rules=r, reason="x", analyses=frozenset({"IC-ANIONS"})
        )
    with pytest.raises(Refused, match="not ordered"):
        custody.correct(
            session, LOOKUP, c.id, actor=ANALYST, rules=r, reason="x", analyses=frozenset({"ZZZ"})
        )
    c = custody.correct(
        session,
        LOOKUP,
        c.id,
        actor=ANALYST,
        rules=r,
        reason="x",
        analyses=frozenset({"IC-ANIONS", "ICPMS-METALS"}),
    )
    assert c.current_analyses == {"IC-ANIONS", "ICPMS-METALS"}


def test_hold_blocks_disposal_and_only_a_supervisor_lifts_it(session, r):
    (c,) = receive(session, r)
    held = custody.hold(session, c.id, actor=ANALYST, reason="complaint C-7")
    assert held.held and held.hold_reason == "complaint C-7" and not held.due(TODAY + timedelta(days=999))
    with pytest.raises(Refused, match="already on hold"):
        custody.hold(session, c.id, actor=ANALYST, reason="again")
    with pytest.raises(Refused, match="on hold: complaint C-7"):
        custody.dispose(
            session,
            c.id,
            actor=ANALYST,
            rules=r,
            method="Lab waste stream",
            today=TODAY + timedelta(days=999),
        )
    with pytest.raises(Refused, match="on hold"):
        custody.return_to_customer(session, c.id, actor=ANALYST)
    with pytest.raises(NotAllowed):
        custody.release_hold(session, c.id, actor=ANALYST, reason="closed")
    assert not custody.release_hold(session, c.id, actor=QUALITY, reason="C-7 closed").held
    with pytest.raises(Refused, match="not on hold"):
        custody.release_hold(session, c.id, actor=QUALITY, reason="x")


def test_dispose_needs_a_listed_method_and_a_reason_before_the_retention_date(session, r):
    (c,) = receive(session, r)
    with pytest.raises(Refused, match="unknown disposal method"):
        custody.dispose(session, c.id, actor=ANALYST, rules=r, method="bin", today=c.retention_due)
    with pytest.raises(Refused, match=f"kept until {c.retention_due.isoformat()}"):
        custody.dispose(session, c.id, actor=ANALYST, rules=r, method="Lab waste stream", today=TODAY)
    done = custody.dispose(
        session, c.id, actor=ANALYST, rules=r, method="Lab waste stream", today=TODAY, reason="customer asked"
    )
    assert done.outcome == EventKind.DISPOSED and not done.active and done.current_location is None
    assert done.events[-1].method == "Lab waste stream" and done.events[-1].reason == "customer asked"


def test_on_the_retention_date_no_reason_is_needed_and_a_finished_bottle_takes_nothing_more(session, r):
    (c,) = receive(session, r)
    done = custody.dispose(
        session, c.id, actor=ANALYST, rules=r, method="Vendor pickup", today=c.retention_due
    )
    for call in (
        lambda: custody.move(session, c.id, "shelf-a", actor=ANALYST, rules=r),
        lambda: custody.hold(session, c.id, actor=ANALYST, reason="x"),
        lambda: custody.return_to_customer(session, c.id, actor=ANALYST),
    ):
        with pytest.raises(Refused, match="already disposed of"):
            call()
    assert done.finished_on is not None and custody.verify(session) == []


def test_return_to_customer(session, r):
    (c,) = receive(session, r)
    back = custody.return_to_customer(session, c.id, actor=ANALYST, note="collected by courier")
    assert back.outcome == EventKind.RETURNED
    with pytest.raises(Refused, match="already returned"):
        custody.move(session, c.id, "shelf-a", actor=ANALYST, rules=r)


def test_due_for_disposal_lists_the_active_unheld_bottles_whose_retention_ended(session, r):
    (a,) = receive(session, r)
    (b,) = receive(session, r, sample="TR00001-02")
    day = a.retention_due
    assert [c.id for c in custody.due_for_disposal(session, day)] == [a.id]
    assert [c.id for c in custody.due_for_disposal(session, day, within_days=300)] == [a.id, b.id]
    assert custody.due_for_disposal(session, day - timedelta(days=1)) == []
    custody.hold(session, a.id, actor=ANALYST, reason="x")
    assert custody.due_for_disposal(session, day) == []
    assert not custody.get_container(session, a.id).overdue(day + timedelta(days=5))


def test_conditions_flag_only_the_analyses_their_bottle_serves(session, r):
    receive(
        session,
        r,
        [
            bottle(conditions=frozenset({"leaking", "unlabelled"}), analyses=frozenset({"ICPMS-METALS"})),
            bottle(container_type="pfa", analyses=frozenset({"IC-ANIONS"})),
        ],
    )
    got = custody.flags_for(session, S1)
    assert set(got) == {"ICPMS-METALS"}  # "unlabelled" is recorded only; the clean PFA bottle serves IC
    (flag,) = got["ICPMS-METALS"]
    assert flag.effect == Effect.WARN and flag.text == "Leaking: bottle 1: 1 × HDPE bottle"
    assert custody.flags_for(session, S1, analyses=["IC-ANIONS"]) == {}
    assert custody.blocked_for(session, S1) == {}


def test_a_blocking_condition_blocks_while_the_bottle_is_in_the_lab_but_still_warns_after(session, r):
    (c,) = receive(session, r, [bottle(conditions=frozenset({"unsafe"}))])
    assert set(custody.blocked_for(session, S1)) == {"ICPMS-METALS", "IC-ANIONS"}
    custody.dispose(session, c.id, actor=ANALYST, rules=r, method="Vendor pickup", today=c.retention_due)
    assert custody.blocked_for(session, S1) == {}
    assert set(custody.flags_for(session, S1)) == {"ICPMS-METALS", "IC-ANIONS"}


def test_flags_use_the_effect_it_had_when_noted_not_the_labs_later_rules(session, r):
    receive(session, r, [bottle(conditions=frozenset({"leaking"}))])
    softer = DEMO_RULES.model_copy(
        update={
            "conditions": tuple(c.model_copy(update={"effect": Effect.NONE}) for c in DEMO_RULES.conditions)
        }
    )
    publish_rules(session, softer, QUALITY)
    assert current_rules(session, "demo").rules == softer
    assert set(custody.flags_for(session, S1)) == {"ICPMS-METALS", "IC-ANIONS"}


def test_only_quality_or_a_supervisor_publishes_the_labs_rules(session):
    with pytest.raises(NotAllowed):
        publish_rules(session, DEMO_RULES, ANALYST)
    first = publish_rules(session, DEMO_RULES, QUALITY)
    assert publish_rules(session, DEMO_RULES, SUPERVISOR).id == first.id  # same content: same version


def test_labels_are_numbered_and_carry_the_keep_until_date(session, r):
    receive(session, r, [bottle(count=2), bottle(container_type="pfa", analyses=frozenset({"IC-ANIONS"}))])
    one, two = custody.labels_for(session, S1)
    assert (one.code, one.bottle, one.kind, one.count) == ("TR00001-01/1", "1 of 2", "HDPE bottle", 2)
    assert two.bottle == "2 of 2" and two.keep_until == TODAY + timedelta(days=90)


def test_many_samples_load_in_one_go_and_missing_ones_are_empty(session, r):
    receive(session, r)
    got = custody.containers_for(session, [S1, "TR00001-02"])
    assert len(got[S1]) == 1 and got["TR00001-02"] == [] and custody.containers_for(session, []) == {}
    with pytest.raises(NotFound):
        custody.get_container(session, 9999)


def test_verify_finds_a_retention_date_the_rules_dont_give(session, r):
    from sqlalchemy import text

    receive(session, r)
    # A hand edit: the append-only trigger would refuse an UPDATE, so make the bad row as a table owner could.
    if session.get_bind().dialect.name == "postgresql":
        session.execute(text("ALTER TABLE samples_containers DISABLE TRIGGER USER"))
    else:
        session.execute(text("DROP TRIGGER slim_samples_no_update_samples_containers"))
    session.execute(text("UPDATE samples_containers SET retention_due = received_on"))
    assert [p.message for p in custody.verify(session)] == [
        f"retention is {TODAY}, rules give {TODAY + timedelta(days=90)}"
    ]

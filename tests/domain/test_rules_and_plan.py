from datetime import date

import pytest
from pydantic import ValidationError

from slim_samples.demo import DEMO_RULES
from slim_samples.domain.containers import ContainerIn, SampleInfo, plan_receipt
from slim_samples.domain.problems import Refused
from slim_samples.domain.rules import Condition, ContainerType, Location, SamplesRules

INFO = SampleInfo(sample="TR00001-01", analyses=frozenset({"A", "B"}), customer="demo-a")


def ci(**kw):
    kw.setdefault("container_type", "hdpe")
    kw.setdefault("location", "receiving")
    return ContainerIn(**kw)


def test_retention_is_days_from_receipt_with_a_per_customer_override():
    assert DEMO_RULES.retention_due(date(2026, 11, 2), "demo-a") == date(2027, 1, 31)
    assert DEMO_RULES.retention_due(date(2026, 11, 2), "demo-long") == date(2027, 11, 2)


@pytest.mark.parametrize(
    "change",
    [
        {"container_types": (ContainerType(code="a", label="A"), ContainerType(code="a", label="A2"))},
        {"locations": ()},
        {"conditions": (Condition(code="x", label="X"), Condition(code="x", label="Y"))},
        {"disposal_methods": ("Drain", "drain")},
        {"retention_days": 0},
    ],
)
def test_rules_refuse_duplicates_empty_lists_and_zero_retention(change):
    with pytest.raises(ValidationError):
        SamplesRules(**{**DEMO_RULES.model_dump(), **change})


def test_codes_are_slugs():
    with pytest.raises(ValidationError):
        Location(code="Fridge 1", label="Fridge")


def test_one_bottle_serves_every_ordered_analysis():
    (p,) = plan_receipt(INFO, [ci(count=3)], DEMO_RULES)
    assert p.analyses == {"A", "B"} and p.count == 3 and p.type_label == "HDPE bottle" and p.position == 1


def test_several_bottles_each_name_what_they_serve_and_together_cover_the_order():
    plans = plan_receipt(
        INFO, [ci(analyses=frozenset({"A"})), ci(container_type="pfa", analyses=frozenset({"B"}))], DEMO_RULES
    )
    assert [(p.position, p.type_label) for p in plans] == [(1, "HDPE bottle"), (2, "PFA bottle")]


def test_nothing_logged_is_refused():
    with pytest.raises(Refused, match="at least one container"):
        plan_receipt(INFO, [], DEMO_RULES)


def test_an_uncovered_analysis_is_refused():
    with pytest.raises(Refused, match="no container is logged for: B"):
        plan_receipt(INFO, [ci(analyses=frozenset({"A"}))], DEMO_RULES)


def test_every_problem_is_reported_with_its_row_and_field():
    with pytest.raises(Refused) as e:
        plan_receipt(
            INFO,
            [
                ci(
                    container_type="nope",
                    location="moon",
                    conditions=frozenset({"melted"}),
                    analyses=frozenset({"Z"}),
                )
            ],
            DEMO_RULES,
        )
    assert {p.where for p in e.value.problems} == {
        "containers[0].container_type",
        "containers[0].location",
        "containers[0].conditions",
        "containers[0].analyses",
        "containers",
    }


def test_conditions_are_copied_with_their_effect():
    (p,) = plan_receipt(INFO, [ci(conditions=frozenset({"leaking", "unlabelled"}))], DEMO_RULES)
    assert {(c.code, c.effect.name) for c in p.conditions} == {("leaking", "WARN"), ("unlabelled", "NONE")}

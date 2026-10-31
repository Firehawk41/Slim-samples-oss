"""Test helpers: actors, a fake TR (the host's port), and the demo rules published."""

from datetime import date

from slim_samples.demo import DEMO_RULES
from slim_samples.domain.actor import Actor, IdentitySource, Role
from slim_samples.domain.containers import ContainerIn, SampleInfo
from slim_samples.service.rules import publish_rules

TODAY = date(2026, 11, 2)

ANALYST = Actor(
    id="u-an",
    display="Ana Analyst",
    roles=frozenset({Role.ANALYST}),
    identity_source=IdentitySource.AUTHENTICATED,
)
SUPERVISOR = Actor(
    id="u-su",
    display="Sam Supervisor",
    roles=frozenset({Role.SUPERVISOR}),
    identity_source=IdentitySource.AUTHENTICATED,
)
QUALITY = Actor(
    id="u-qm",
    display="Quinn Quality",
    roles=frozenset({Role.QUALITY}),
    identity_source=IdentitySource.AUTHENTICATED,
)
NOBODY = Actor(id="u-cu", display="A Customer")


class FakeSamples:
    """The host's port: what each lab sample is and which analyses were ordered for it."""

    def __init__(self, **samples: SampleInfo) -> None:
        self.samples = samples

    def sample(self, sample_id: str) -> SampleInfo | None:
        return self.samples.get(sample_id)


S1 = "TR00001-01"
LOOKUP = FakeSamples(
    **{
        "TR00001-01": SampleInfo(
            sample=S1, analyses=frozenset({"ICPMS-METALS", "IC-ANIONS"}), customer="demo-a"
        ),
        "TR00001-02": SampleInfo(
            sample="TR00001-02", analyses=frozenset({"IC-ANIONS"}), customer="demo-long"
        ),
    }
)


def rules(session, rules_=DEMO_RULES):
    return publish_rules(session, rules_, SUPERVISOR)


def bottle(**kw) -> ContainerIn:
    kw.setdefault("container_type", "hdpe")
    kw.setdefault("location", "receiving")
    return ContainerIn(**kw)

"""The lab's own lists and periods (S-03): container types, conditions with what each one does, storage
locations, disposal methods, retention. Lab data, never code: a lab edits them and publishes a new
version; every container keeps the version it was received under."""

from datetime import date, timedelta
from enum import IntEnum
from typing import Annotated

from pydantic import Field, StringConstraints, model_validator

from slim_samples.domain.base import Frozen

Code = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9_-]{0,39}$")]
Label = Annotated[str, StringConstraints(min_length=1, max_length=100)]


class Effect(IntEnum):
    """What a condition does to the analyses the bottle serves (S-04)."""

    NONE = 1  # recorded only
    WARN = 2  # the review screen and the report say the analysis may be compromised
    BLOCK = 3  # no prep batch may use the sample until the lab decides (e.g. unsafe to handle)


class ContainerType(Frozen):
    code: Code
    label: Label


class Condition(Frozen):
    """Something wrong with a bottle on receipt. No condition noted means it arrived intact."""

    code: Code
    label: Label
    effect: Effect = Effect.WARN


class Location(Frozen):
    code: Code
    label: Label


class RetentionOverride(Frozen):
    customer: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    days: int = Field(ge=1, le=3650)


class SamplesRules(Frozen):
    name: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    container_types: tuple[ContainerType, ...] = Field(min_length=1)
    conditions: tuple[Condition, ...] = ()
    locations: tuple[Location, ...] = Field(min_length=1)
    disposal_methods: tuple[Label, ...] = Field(min_length=1)
    retention_days: int = Field(ge=1, le=3650)
    retention_overrides: tuple[RetentionOverride, ...] = ()

    @model_validator(mode="after")
    def _unique(self):
        for what, codes in (
            ("container type", [t.code for t in self.container_types]),
            ("condition", [c.code for c in self.conditions]),
            ("location", [x.code for x in self.locations]),
            ("customer override", [o.customer for o in self.retention_overrides]),
            ("disposal method", [m.lower() for m in self.disposal_methods]),
        ):
            if len(set(codes)) != len(codes):
                raise ValueError(f"duplicate {what}")
        return self

    def container_type(self, code: str) -> ContainerType | None:
        return next((t for t in self.container_types if t.code == code), None)

    def condition(self, code: str) -> Condition | None:
        return next((c for c in self.conditions if c.code == code), None)

    def location(self, code: str) -> Location | None:
        return next((x for x in self.locations if x.code == code), None)

    def retention_for(self, customer: str) -> int:
        return next((o.days for o in self.retention_overrides if o.customer == customer), self.retention_days)

    def retention_due(self, received_on: date, customer: str) -> date:
        """Kept from the day it was received (§7.4: records of the item's receipt start the clock)."""
        return received_on + timedelta(days=self.retention_for(customer))

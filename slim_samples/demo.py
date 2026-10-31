"""An invented lab's lists (never a real lab's); the host seeds them and the lab edits them."""

from slim_samples.domain.rules import (
    Condition,
    ContainerType,
    Effect,
    Location,
    RetentionOverride,
    SamplesRules,
)

DEMO_RULES = SamplesRules(
    name="demo",
    container_types=(
        ContainerType(code="pfa", label="PFA bottle"),
        ContainerType(code="hdpe", label="HDPE bottle"),
        ContainerType(code="glass", label="Glass vial"),
        ContainerType(code="other", label="Other"),
    ),
    conditions=(
        Condition(code="leaking", label="Leaking", effect=Effect.WARN),
        Condition(code="cracked", label="Cracked or damaged", effect=Effect.WARN),
        Condition(code="no-preservative", label="Not preserved", effect=Effect.WARN),
        Condition(code="over-temperature", label="Arrived warm", effect=Effect.WARN),
        Condition(code="unlabelled", label="Unlabelled", effect=Effect.NONE),
        Condition(code="unsafe", label="Unsafe to handle", effect=Effect.BLOCK),
    ),
    locations=(
        Location(code="receiving", label="Receiving bench"),
        Location(code="fridge-1", label="Fridge 1"),
        Location(code="shelf-a", label="Shelf A"),
        Location(code="cabinet-acid", label="Acid cabinet"),
        Location(code="waste-pickup", label="Waste pickup area"),
    ),
    disposal_methods=("Lab waste stream", "Neutralised and drained", "Vendor pickup"),
    retention_days=90,
    retention_overrides=(RetentionOverride(customer="demo-long", days=365),),
)

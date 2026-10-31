"""Who does something. slim-samples never authenticates; the host passes an Actor in, with the roles
it gave the person."""

from enum import IntEnum

from pydantic import Field

from slim_samples.domain.base import Frozen


class Role(IntEnum):
    ANALYST = 1
    SUPERVISOR = 2
    QUALITY = 3  # the quality manager


class IdentitySource(IntEnum):
    """How the host knows who the actor is (slim-data D-50, same values)."""

    AUTHENTICATED = 1  # a real login
    ASSERTED = 2  # claimed, e.g. a demo persona


class Actor(Frozen):
    id: str = Field(min_length=1, max_length=100)
    display: str = Field(min_length=1, max_length=254)
    roles: frozenset[Role] = frozenset()
    identity_source: IdentitySource | None = None

    @property
    def may_publish_rules(self) -> bool:
        """The lab sets its own lists and periods: quality, or a supervisor standing in."""
        return bool(self.roles & {Role.QUALITY, Role.SUPERVISOR})

    @property
    def may_release_hold(self) -> bool:
        return bool(self.roles & {Role.QUALITY, Role.SUPERVISOR})

"""Why a request was refused: a list of problems, each saying where and what."""

from slim_samples.domain.base import Frozen


class Problem(Frozen):
    where: str
    message: str


class Refused(ValueError):
    """The request breaks a rule. `problems` says which, so the host can show each beside its field."""

    def __init__(self, problems: list[Problem] | Problem) -> None:
        self.problems = [problems] if isinstance(problems, Problem) else list(problems)
        super().__init__("; ".join(f"{p.where}: {p.message}" for p in self.problems))

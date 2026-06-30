from dataclasses import dataclass


@dataclass(slots=True)
class ActionStep:
    action: str
    note: str


@dataclass(slots=True)
class TimingSample:
    name: str
    elapsed_seconds: float


@dataclass
class ApiCall:
    method: str
    path: str
    status_code: int = 0

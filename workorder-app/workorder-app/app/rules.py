"""Pure business rules: no Flask, no database. Easy to unit test.

Rule numbers refer to the assignment brief.
"""
from datetime import date

ASSET_STATUSES = ("ACTIVE", "INACTIVE", "OUT_OF_SERVICE")
TECHNICIAN_STATUSES = ("ACTIVE", "INACTIVE", "ON_LEAVE")
PRIORITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
STATUSES = ("OPEN", "ASSIGNED", "IN_PROGRESS", "COMPLETED", "CANCELLED")

# The state machine. Forward-only; COMPLETED and CANCELLED are terminal.
TRANSITIONS = {
    "OPEN": ("ASSIGNED", "CANCELLED"),
    "ASSIGNED": ("IN_PROGRESS", "CANCELLED"),
    "IN_PROGRESS": ("COMPLETED",),
    "COMPLETED": (),
    "CANCELLED": (),
}
TERMINAL = frozenset({"COMPLETED", "CANCELLED"})
# Statuses in which a technician must be on the work order.
NEEDS_TECHNICIAN = frozenset({"ASSIGNED", "IN_PROGRESS", "COMPLETED"})
# Statuses in which the technician may still be changed.
REASSIGNABLE = frozenset({"OPEN", "ASSIGNED"})


class RuleViolation(Exception):
    """A business rule was broken. `status` is the HTTP status to answer with."""

    def __init__(self, code: str, message: str, status: int = 422, field: str | None = None):
        super().__init__(message)
        self.code, self.message, self.status, self.field = code, message, status, field


def allowed_transitions(status: str) -> tuple[str, ...]:
    return TRANSITIONS[status]


def check_transition(current: str, target: str) -> None:
    """Rules 3 and 4, plus the general state machine."""
    if target == current:
        return
    if target in TRANSITIONS[current]:
        return
    if current == "COMPLETED" and target == "OPEN":
        raise RuleViolation(
            "INVALID_TRANSITION",
            "A completed work order cannot be reopened (COMPLETED -> OPEN).",
            409,
        )
    if current == "CANCELLED" and target == "IN_PROGRESS":
        raise RuleViolation(
            "INVALID_TRANSITION",
            "A cancelled work order cannot be moved to IN_PROGRESS.",
            409,
        )
    allowed = ", ".join(TRANSITIONS[current]) or "none (terminal state)"
    raise RuleViolation(
        "INVALID_TRANSITION",
        f"Cannot move a work order from {current} to {target}. Allowed: {allowed}.",
        409,
    )


def check_critical_has_technician(priority: str, technician_id) -> None:
    """Rule 2."""
    if priority == "CRITICAL" and technician_id is None:
        raise RuleViolation(
            "CRITICAL_REQUIRES_TECHNICIAN",
            "A CRITICAL work order must have an assigned technician.",
            field="technician_id",
        )


def check_schedule_not_in_past(scheduled: date, today: date) -> None:
    """Rule 5."""
    if scheduled < today:
        raise RuleViolation(
            "SCHEDULE_IN_PAST",
            f"Scheduled date {scheduled.isoformat()} is in the past (today is {today.isoformat()}).",
            field="scheduled_date",
        )


def check_asset_accepts_maintenance(asset_status: str, type_is_emergency: bool) -> None:
    """Rule 6."""
    if asset_status == "OUT_OF_SERVICE" and not type_is_emergency:
        raise RuleViolation(
            "ASSET_OUT_OF_SERVICE",
            "This asset is OUT_OF_SERVICE; only emergency maintenance types may be raised against it.",
            field="maintenance_type_id",
        )


def check_status_has_technician(status: str, technician_id) -> None:
    if status in NEEDS_TECHNICIAN and technician_id is None:
        raise RuleViolation(
            "TECHNICIAN_REQUIRED",
            f"A work order in status {status} must have an assigned technician.",
            field="technician_id",
        )

"""KPIs for one day. Plain Python, no Streamlit."""

from __future__ import annotations

from dataclasses import dataclass

from core.models import CLOSE_TIME, OPEN_TIME, Appointment, Dock, Punctuality, Status
from core.rules import arrival_punctuality

# Cancelled and no-show bookings never used their dock time.
USED_STATUSES = {Status.BOOKED, Status.ARRIVED, Status.AT_DOCK, Status.COMPLETED}


@dataclass
class DayKpis:
    bookings: int
    utilisation_pct: float
    arrivals: int
    early: int
    on_time: int
    late: int
    on_time_pct: float | None  # None when no truck has arrived yet
    avg_yard_wait_min: float | None  # None when no truck has reached a dock yet
    no_shows: int
    cancelled: int


def open_minutes_per_dock() -> int:
    return (CLOSE_TIME.hour * 60 + CLOSE_TIME.minute) - (OPEN_TIME.hour * 60 + OPEN_TIME.minute)


def dock_utilisation(appointments: list[Appointment], docks: list[Dock]) -> dict[str, float]:
    """Booked minutes as a % of opening hours, per active dock."""
    capacity = open_minutes_per_dock()
    result = {}
    for dock in docks:
        if not dock.active:
            continue
        used = sum(a.duration_min for a in appointments if a.dock_id == dock.id and a.status in USED_STATUSES)
        result[dock.id] = 100 * used / capacity
    return result


def yard_wait_minutes(appt: Appointment) -> float | None:
    """Minutes between arriving at the gate and reaching the dock."""
    if appt.arrived_at is None or appt.docked_at is None:
        return None
    return (appt.docked_at - appt.arrived_at).total_seconds() / 60


def day_kpis(appointments: list[Appointment], docks: list[Dock]) -> DayKpis:
    """Headline KPIs for the appointments of one day."""
    per_dock = dock_utilisation(appointments, docks)
    utilisation = sum(per_dock.values()) / len(per_dock) if per_dock else 0.0

    arrived = [a for a in appointments if a.arrived_at is not None]
    punctuality = [arrival_punctuality(a.start, a.arrived_at) for a in arrived]
    on_time = punctuality.count(Punctuality.ON_TIME)

    waits = [w for a in appointments if (w := yard_wait_minutes(a)) is not None]

    return DayKpis(
        bookings=sum(a.status != Status.CANCELLED for a in appointments),
        utilisation_pct=utilisation,
        arrivals=len(arrived),
        early=punctuality.count(Punctuality.EARLY),
        on_time=on_time,
        late=punctuality.count(Punctuality.LATE),
        on_time_pct=100 * on_time / len(arrived) if arrived else None,
        avg_yard_wait_min=sum(waits) / len(waits) if waits else None,
        no_shows=sum(a.status == Status.NO_SHOW for a in appointments),
        cancelled=sum(a.status == Status.CANCELLED for a in appointments),
    )

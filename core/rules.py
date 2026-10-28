"""Business rules for booking slots and moving trucks through the yard.

Plain Python, no Streamlit. Anything that depends on the current time takes
`now` as a parameter so tests stay repeatable.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time, timedelta
from typing import Iterable

from core.models import (
    CLOSE_TIME,
    MAX_PALLETS,
    NO_SHOW_AFTER_MIN,
    ON_TIME_TOLERANCE_MIN,
    OPEN_TIME,
    OPEN_WEEKDAYS,
    SLOT_GRID_MIN,
    YARD_SPOTS,
    Appointment,
    Direction,
    Dock,
    DockType,
    Punctuality,
    Status,
)

# Bookings in these states still occupy their dock slot.
BLOCKING_STATUSES = {Status.BOOKED, Status.ARRIVED, Status.AT_DOCK, Status.COMPLETED}

TRANSITIONS: dict[Status, set[Status]] = {
    Status.BOOKED: {Status.ARRIVED, Status.NO_SHOW, Status.CANCELLED},
    Status.ARRIVED: {Status.AT_DOCK},
    Status.AT_DOCK: {Status.COMPLETED},
}


class BookingError(ValueError):
    """Raised when a booking or status change breaks a rule."""


# --- Duration -----------------------------------------------------------------
def duration_for_pallets(pallets: int) -> int:
    """Slot length in minutes for a given pallet count."""
    if pallets < 1:
        raise BookingError("Pallet count must be at least 1.")
    if pallets <= 10:
        return 30
    if pallets <= 26:
        return 60
    if pallets <= MAX_PALLETS:
        return 90
    raise BookingError(
        f"{pallets} pallets is more than one truck (max {MAX_PALLETS}). "
        "Split it into two bookings."
    )


# --- Booking validation -------------------------------------------------------
def is_open_day(day: date) -> bool:
    return day.weekday() in OPEN_WEEKDAYS


def is_on_grid(t: time) -> bool:
    return t.minute % SLOT_GRID_MIN == 0 and t.second == 0 and t.microsecond == 0


def dock_compatibility_errors(dock: Dock, direction: Direction, reefer: bool) -> list[str]:
    """Reasons this dock can't take this kind of load (empty list = fine)."""
    errors = []
    if not dock.active:
        errors.append(f"Dock {dock.id} is not active.")
    if dock.type != DockType.BOTH and dock.type.value != direction.value:
        errors.append(f"Dock {dock.id} is {dock.type.value}-only; this load is {direction.value}.")
    if reefer and not dock.reefer:
        errors.append(f"Dock {dock.id} has no reefer plug; this load needs one.")
    return errors


def overlaps(a: Appointment, b: Appointment) -> bool:
    return a.start < b.end and b.start < a.end


def find_clash(appt: Appointment, existing: Iterable[Appointment]) -> Appointment | None:
    """First booking on the same dock whose time overlaps `appt`."""
    for other in existing:
        if (
            other.dock_id == appt.dock_id
            and other.status in BLOCKING_STATUSES
            and (appt.id is None or other.id != appt.id)
            and overlaps(appt, other)
        ):
            return other
    return None


def validate_booking(
    appt: Appointment,
    dock: Dock,
    existing: Iterable[Appointment],
    now: datetime | None = None,
) -> list[str]:
    """All the reasons this booking can't go ahead (empty list = OK).

    Pass `now` when booking a new slot so slots that have already started are refused.
    """
    errors = []
    for label, value in (("Carrier", appt.carrier), ("Truck plate", appt.truck_plate),
                         ("Reference", appt.reference)):
        if not value.strip():
            errors.append(f"{label} is required.")
    try:
        duration_for_pallets(appt.pallets)
    except BookingError as exc:
        errors.append(str(exc))

    if not is_open_day(appt.date):
        errors.append("The site is closed on Sundays.")
    if not is_on_grid(appt.start_time):
        errors.append(f"Slots start on a {SLOT_GRID_MIN}-minute grid (e.g. 08:00, 08:30).")
    if appt.start_time < OPEN_TIME or appt.end > datetime.combine(appt.date, CLOSE_TIME):
        errors.append(
            f"{appt.start_time:%H:%M}–{appt.end:%H:%M} is outside opening hours "
            f"({OPEN_TIME:%H:%M}–{CLOSE_TIME:%H:%M})."
        )
    if now and appt.start < now:
        errors.append(f"That slot has already started (it is now {now:%a %d %b %H:%M}).")

    errors.extend(dock_compatibility_errors(dock, appt.direction, appt.reefer))

    clash = find_clash(appt, existing)
    if clash:
        errors.append(
            f"Dock {appt.dock_id} is already booked {clash.start_time:%H:%M}–{clash.end:%H:%M} "
            f"({clash.carrier})."
        )
    return errors


# --- Suggestions --------------------------------------------------------------
def _ceil_to_grid(t: time) -> time:
    minutes = t.hour * 60 + t.minute + (1 if t.second or t.microsecond else 0)
    minutes = -(-minutes // SLOT_GRID_MIN) * SLOT_GRID_MIN
    if minutes >= 24 * 60:
        return CLOSE_TIME
    return time(minutes // 60, minutes % 60)


def suggest_slots(
    appt: Appointment,
    docks: Iterable[Dock],
    existing: Iterable[Appointment],
    n: int = 3,
    days_ahead: int = 7,
    now: datetime | None = None,
) -> list[Appointment]:
    """The `n` earliest free slots that would work for this load.

    Walks forward on the slot grid from the requested start, across every
    compatible active dock. When two options share a time, the requested
    dock comes first. Never suggests a slot that has already started.
    """
    try:
        duration_for_pallets(appt.pallets)
    except BookingError:
        return []  # no slot can fix a pallet problem

    existing = list(existing)
    candidates = [d for d in docks if not dock_compatibility_errors(d, appt.direction, appt.reefer)]
    candidates.sort(key=lambda d: (d.id != appt.dock_id, d.id))

    duration = timedelta(minutes=appt.duration_min)
    found: list[Appointment] = []
    for offset in range(days_ahead + 1):
        day = appt.date + timedelta(days=offset)
        if not is_open_day(day) or (now and day < now.date()):
            continue
        t = max(OPEN_TIME, _ceil_to_grid(appt.start_time)) if offset == 0 else OPEN_TIME
        if now and day == now.date():
            t = max(t, _ceil_to_grid(now.time()))
        slot = datetime.combine(day, t)
        while slot + duration <= datetime.combine(day, CLOSE_TIME):
            for dock in candidates:
                option = replace(appt, date=day, start_time=slot.time(), dock_id=dock.id, id=None)
                if not validate_booking(option, dock, existing, now):
                    found.append(option)
                    if len(found) == n:
                        return found
            slot += timedelta(minutes=SLOT_GRID_MIN)
    return found


# --- Yard & gate --------------------------------------------------------------
def format_minutes(minutes: int) -> str:
    """e.g. 25 → '25 min', 60 → '1 h', 220 → '3 h 40 min'."""
    hours, mins = divmod(int(minutes), 60)
    if not hours:
        return f"{mins} min"
    return f"{hours} h" + (f" {mins} min" if mins else "")


def arrival_text(slot_start: datetime, arrived_at: datetime) -> str:
    """Plain words for an arrival, e.g. 'on time', '25 min early', '1 h 10 min late'."""
    punctuality = arrival_punctuality(slot_start, arrived_at)
    if punctuality == Punctuality.ON_TIME:
        return "on time"
    minutes = abs(int((arrived_at - slot_start).total_seconds() // 60))
    return f"{format_minutes(minutes)} {punctuality.value}"


def arrival_punctuality(slot_start: datetime, arrived_at: datetime) -> Punctuality:
    """On time if within ±15 minutes of the slot start."""
    diff_min = (arrived_at - slot_start).total_seconds() / 60
    if diff_min < -ON_TIME_TOLERANCE_MIN:
        return Punctuality.EARLY
    if diff_min > ON_TIME_TOLERANCE_MIN:
        return Punctuality.LATE
    return Punctuality.ON_TIME


def can_mark_no_show(appt: Appointment, now: datetime) -> bool:
    return appt.status == Status.BOOKED and now >= appt.start + timedelta(minutes=NO_SHOW_AFTER_MIN)


def next_statuses(status: Status) -> set[Status]:
    return set(TRANSITIONS.get(status, set()))


def apply_transition(
    appt: Appointment,
    new_status: Status,
    now: datetime,
    existing: Iterable[Appointment] = (),
) -> Appointment:
    """Return a copy of `appt` moved to `new_status`, with the right timestamp set."""
    if new_status not in next_statuses(appt.status):
        raise BookingError(f"Can't move a truck from '{appt.status.value}' to '{new_status.value}'.")

    if new_status == Status.NO_SHOW and not can_mark_no_show(appt, now):
        raise BookingError(
            f"A truck can only be marked no-show {NO_SHOW_AFTER_MIN} minutes after its slot start "
            f"({(appt.start + timedelta(minutes=NO_SHOW_AFTER_MIN)):%H:%M})."
        )
    if new_status == Status.ARRIVED:
        return replace(appt, status=new_status, arrived_at=now)
    if new_status == Status.AT_DOCK:
        for other in existing:
            if other.dock_id == appt.dock_id and other.status == Status.AT_DOCK and other.id != appt.id:
                raise BookingError(f"Dock {appt.dock_id} is still occupied by {other.carrier} ({other.truck_plate}).")
        return replace(appt, status=new_status, docked_at=now)
    if new_status == Status.COMPLETED:
        return replace(appt, status=new_status, completed_at=now)
    return replace(appt, status=new_status)


def waiting_minutes(appt: Appointment, now: datetime) -> int:
    """How long a truck has been waiting in the yard (0 if it isn't waiting)."""
    if appt.status != Status.ARRIVED or appt.arrived_at is None:
        return 0
    return max(0, int((now - appt.arrived_at).total_seconds() // 60))


def yard_overflow(waiting_count: int, spots: int = YARD_SPOTS) -> str | None:
    """Warning text when more trucks are waiting than there are parking spots."""
    if waiting_count > spots:
        return f"Yard over capacity: {waiting_count} trucks waiting for {spots} parking spots."
    return None

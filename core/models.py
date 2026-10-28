"""Data model and site constants. Plain Python, no Streamlit."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import StrEnum

# --- Site constants -----------------------------------------------------------
OPEN_TIME = time(6, 0)
CLOSE_TIME = time(22, 0)
OPEN_WEEKDAYS = {0, 1, 2, 3, 4, 5}  # Monday=0 … Saturday=5; closed Sunday
SLOT_GRID_MIN = 30
YARD_SPOTS = 12
ON_TIME_TOLERANCE_MIN = 15
NO_SHOW_AFTER_MIN = 30
MAX_PALLETS = 33


class Direction(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class DockType(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"
    BOTH = "both"


class Status(StrEnum):
    BOOKED = "booked"
    ARRIVED = "arrived"  # waiting in the yard
    AT_DOCK = "at_dock"
    COMPLETED = "completed"
    NO_SHOW = "no_show"
    CANCELLED = "cancelled"


class Punctuality(StrEnum):
    EARLY = "early"
    ON_TIME = "on_time"
    LATE = "late"


@dataclass
class Dock:
    id: str  # e.g. "D1"
    name: str
    type: DockType
    reefer: bool
    active: bool = True


@dataclass
class Appointment:
    carrier: str
    truck_plate: str
    reference: str  # PO / ASN / delivery note
    direction: Direction
    pallets: int
    reefer: bool
    date: date
    start_time: time
    duration_min: int
    dock_id: str
    status: Status = Status.BOOKED
    arrived_at: datetime | None = None
    docked_at: datetime | None = None
    completed_at: datetime | None = None
    notes: str = ""
    id: int | None = None

    @property
    def start(self) -> datetime:
        return datetime.combine(self.date, self.start_time)

    @property
    def end(self) -> datetime:
        return self.start + timedelta(minutes=self.duration_min)

"""Demo data: 6 docks and ~25 invented appointments for today and the next open day.

Today's bookings tell a story as seen at 11:00 (DEMO_TIME): early trucks are
done, two are at a dock, three are waiting in the yard, one never showed up,
one was cancelled and the afternoon is still booked.

Run `python -m data.seed` to reset the database.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, time, timedelta

from core import db
from core.models import Appointment, Direction, Dock, DockType, Status
from core.rules import duration_for_pallets, is_open_day

DEMO_TIME = time(11, 0)

DOCKS = [
    Dock("D1", "Dock 1", DockType.INBOUND, reefer=False),
    Dock("D2", "Dock 2", DockType.INBOUND, reefer=True),
    Dock("D3", "Dock 3", DockType.INBOUND, reefer=False),
    Dock("D4", "Dock 4", DockType.OUTBOUND, reefer=False),
    Dock("D5", "Dock 5", DockType.OUTBOUND, reefer=False),
    Dock("D6", "Dock 6", DockType.BOTH, reefer=True),
]

IN, OUT = Direction.INBOUND, Direction.OUTBOUND
B, A, AD, C, NS, X = (
    Status.BOOKED, Status.ARRIVED, Status.AT_DOCK, Status.COMPLETED, Status.NO_SHOW, Status.CANCELLED,
)

# (dock, start, pallets, direction, reefer, carrier, plate, reference, status,
#  arrived, docked, completed, notes)
TODAY = [
    ("D1", "06:00", 20, IN, False, "Rhône Freight", "FR-218-KL", "ASN-40112", C, "05:55", "06:00", "06:55", ""),
    ("D4", "06:00", 24, OUT, False, "Atlas Logistics", "AT-904-PB", "DN-70031", C, "06:05", "06:10", "07:05", ""),
    ("D2", "06:30", 30, IN, True, "Nordic Haul", "NH-551-ZT", "ASN-40113", C, "06:20", "06:35", "07:55", "Chilled dairy"),
    ("D5", "07:00", 6, OUT, False, "Iberia Road", "IB-337-MM", "DN-70032", NS, None, None, None, ""),
    ("D1", "07:30", 8, IN, False, "Loire Transports", "LT-120-GH", "ASN-40114", C, "07:50", "07:55", "08:25", "Traffic on A6"),
    ("D3", "08:00", 18, IN, False, "Alpine Cargo", "AC-772-RE", "ASN-40115", C, "07:30", "08:00", "08:50", ""),
    ("D6", "09:00", 32, IN, True, "Baltic Line", "BL-640-WS", "ASN-40116", C, "08:58", "09:05", "10:25", "Frozen goods"),
    ("D3", "09:30", 9, IN, False, "Seine Express", "SE-215-DA", "ASN-40117", X, None, None, None, "Supplier delayed order"),
    ("D4", "10:00", 28, OUT, False, "Meridian Freight", "MF-388-TK", "DN-70033", AD, "10:05", "10:20", None, ""),
    ("D1", "10:30", 22, IN, False, "Celtic Carriers", "CC-903-JN", "ASN-40118", AD, "10:10", "10:35", None, ""),
    ("D3", "11:00", 15, IN, False, "Rhône Freight", "FR-447-BV", "ASN-40119", A, "10:40", None, None, ""),
    ("D2", "11:00", 10, IN, True, "Nordic Haul", "NH-208-QC", "ASN-40120", A, "10:55", None, None, "Chilled produce"),
    ("D5", "11:30", 12, OUT, False, "Atlas Logistics", "AT-615-HF", "DN-70034", A, "10:50", None, None, ""),
    ("D6", "13:00", 20, OUT, False, "Alpine Cargo", "AC-129-LP", "DN-70035", B, None, None, None, ""),
    ("D1", "14:00", 30, IN, False, "Loire Transports", "LT-582-SY", "ASN-40121", B, None, None, None, ""),
    ("D2", "15:30", 14, IN, True, "Baltic Line", "BL-314-NX", "ASN-40122", B, None, None, None, ""),
    ("D4", "16:00", 5, OUT, False, "Seine Express", "SE-860-RU", "DN-70036", B, None, None, None, "Small parcel run"),
    ("D5", "18:30", 25, OUT, False, "Meridian Freight", "MF-701-CE", "DN-70037", B, None, None, None, ""),
]

NEXT_DAY = [
    ("D1", "06:00", 20, IN, False, "Celtic Carriers", "CC-455-MA", "ASN-40123", B, None, None, None, ""),
    ("D4", "06:30", 16, OUT, False, "Iberia Road", "IB-902-TS", "DN-70038", B, None, None, None, ""),
    ("D2", "07:00", 31, IN, True, "Nordic Haul", "NH-733-FD", "ASN-40124", B, None, None, None, "Chilled dairy"),
    ("D3", "08:30", 7, IN, False, "Rhône Freight", "FR-366-PW", "ASN-40125", B, None, None, None, ""),
    ("D5", "09:00", 29, OUT, False, "Atlas Logistics", "AT-248-GK", "DN-70039", B, None, None, None, ""),
    ("D6", "10:00", 19, OUT, True, "Baltic Line", "BL-517-HR", "DN-70040", B, None, None, None, "Frozen export"),
    ("D6", "12:00", 4, IN, False, "Seine Express", "SE-094-LZ", "ASN-40126", B, None, None, None, ""),
    ("D1", "13:30", 26, IN, False, "Alpine Cargo", "AC-861-UV", "ASN-40127", B, None, None, None, ""),
]


def first_open_day(day: date) -> date:
    while not is_open_day(day):
        day += timedelta(days=1)
    return day


def _at(day: date, hhmm: str | None) -> datetime | None:
    return datetime.combine(day, time.fromisoformat(hhmm)) if hhmm else None


def build_appointments(day: date, rows: list[tuple]) -> list[Appointment]:
    appointments = []
    for (dock, start, pallets, direction, reefer, carrier, plate, ref,
         status, arrived, docked, completed, notes) in rows:
        appointments.append(Appointment(
            carrier=carrier,
            truck_plate=plate,
            reference=ref,
            direction=direction,
            pallets=pallets,
            reefer=reefer,
            date=day,
            start_time=time.fromisoformat(start),
            duration_min=duration_for_pallets(pallets),
            dock_id=dock,
            status=status,
            arrived_at=_at(day, arrived),
            docked_at=_at(day, docked),
            completed_at=_at(day, completed),
            notes=notes,
        ))
    return appointments


def demo_days(today: date | None = None) -> tuple[date, date]:
    """The two days the demo data covers: today (or next open day) and the open day after."""
    day1 = first_open_day(today or date.today())
    return day1, first_open_day(day1 + timedelta(days=1))


def seed(conn: sqlite3.Connection, today: date | None = None) -> None:
    """Wipe the database and load the demo docks and appointments."""
    day1, day2 = demo_days(today)
    db.clear(conn)
    for dock in DOCKS:
        db.insert_dock(conn, dock)
    for appt in build_appointments(day1, TODAY) + build_appointments(day2, NEXT_DAY):
        db.insert_appointment(conn, appt)


if __name__ == "__main__":
    connection = db.connect()
    seed(connection)
    day1, day2 = demo_days()
    print(f"Seeded {len(DOCKS)} docks and {len(TODAY) + len(NEXT_DAY)} appointments for {day1} and {day2}.")

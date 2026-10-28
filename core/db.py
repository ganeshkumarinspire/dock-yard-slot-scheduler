"""SQLite storage. Plain sqlite3, no ORM, no Streamlit."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, time
from pathlib import Path

from core.models import Appointment, Direction, Dock, DockType, Status

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "dock_yard.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS docks (
    id      TEXT PRIMARY KEY,
    name    TEXT NOT NULL,
    type    TEXT NOT NULL CHECK (type IN ('inbound', 'outbound', 'both')),
    reefer  INTEGER NOT NULL,
    active  INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS appointments (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    carrier       TEXT NOT NULL,
    truck_plate   TEXT NOT NULL,
    reference     TEXT NOT NULL,
    direction     TEXT NOT NULL CHECK (direction IN ('inbound', 'outbound')),
    pallets       INTEGER NOT NULL,
    reefer        INTEGER NOT NULL,
    date          TEXT NOT NULL,  -- YYYY-MM-DD
    start_time    TEXT NOT NULL,  -- HH:MM
    duration_min  INTEGER NOT NULL,
    dock_id       TEXT NOT NULL REFERENCES docks(id),
    status        TEXT NOT NULL,
    arrived_at    TEXT,           -- YYYY-MM-DDTHH:MM
    docked_at     TEXT,
    completed_at  TEXT,
    notes         TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_appointments_date ON appointments(date);
"""

_APPT_COLUMNS = (
    "carrier", "truck_plate", "reference", "direction", "pallets", "reefer", "date",
    "start_time", "duration_min", "dock_id", "status", "arrived_at", "docked_at",
    "completed_at", "notes",
)


def connect(path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Open the database and make sure the tables exist."""
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def is_empty(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT COUNT(*) FROM docks").fetchone()[0] == 0


def clear(conn: sqlite3.Connection) -> None:
    with conn:
        conn.execute("DELETE FROM appointments")
        conn.execute("DELETE FROM docks")
        conn.execute("DELETE FROM sqlite_sequence WHERE name = 'appointments'")


# --- Conversion helpers -------------------------------------------------------
def _dt_to_text(value: datetime | None) -> str | None:
    return value.isoformat(timespec="minutes") if value else None


def _text_to_dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _row_to_dock(row: sqlite3.Row) -> Dock:
    return Dock(
        id=row["id"],
        name=row["name"],
        type=DockType(row["type"]),
        reefer=bool(row["reefer"]),
        active=bool(row["active"]),
    )


def _row_to_appointment(row: sqlite3.Row) -> Appointment:
    return Appointment(
        id=row["id"],
        carrier=row["carrier"],
        truck_plate=row["truck_plate"],
        reference=row["reference"],
        direction=Direction(row["direction"]),
        pallets=row["pallets"],
        reefer=bool(row["reefer"]),
        date=date.fromisoformat(row["date"]),
        start_time=time.fromisoformat(row["start_time"]),
        duration_min=row["duration_min"],
        dock_id=row["dock_id"],
        status=Status(row["status"]),
        arrived_at=_text_to_dt(row["arrived_at"]),
        docked_at=_text_to_dt(row["docked_at"]),
        completed_at=_text_to_dt(row["completed_at"]),
        notes=row["notes"],
    )


def _appointment_values(appt: Appointment) -> tuple:
    return (
        appt.carrier, appt.truck_plate, appt.reference, appt.direction.value, appt.pallets,
        int(appt.reefer), appt.date.isoformat(), appt.start_time.strftime("%H:%M"),
        appt.duration_min, appt.dock_id, appt.status.value, _dt_to_text(appt.arrived_at),
        _dt_to_text(appt.docked_at), _dt_to_text(appt.completed_at), appt.notes,
    )


# --- Docks --------------------------------------------------------------------
def insert_dock(conn: sqlite3.Connection, dock: Dock) -> None:
    with conn:
        conn.execute(
            "INSERT INTO docks (id, name, type, reefer, active) VALUES (?, ?, ?, ?, ?)",
            (dock.id, dock.name, dock.type.value, int(dock.reefer), int(dock.active)),
        )


def list_docks(conn: sqlite3.Connection, active_only: bool = False) -> list[Dock]:
    sql = "SELECT * FROM docks" + (" WHERE active = 1" if active_only else "") + " ORDER BY id"
    return [_row_to_dock(r) for r in conn.execute(sql)]


# --- Appointments -------------------------------------------------------------
def insert_appointment(conn: sqlite3.Connection, appt: Appointment) -> int:
    placeholders = ", ".join("?" for _ in _APPT_COLUMNS)
    with conn:
        cur = conn.execute(
            f"INSERT INTO appointments ({', '.join(_APPT_COLUMNS)}) VALUES ({placeholders})",
            _appointment_values(appt),
        )
    return cur.lastrowid


def update_appointment(conn: sqlite3.Connection, appt: Appointment) -> None:
    if appt.id is None:
        raise ValueError("Can't update an appointment that has no id.")
    assignments = ", ".join(f"{col} = ?" for col in _APPT_COLUMNS)
    with conn:
        conn.execute(
            f"UPDATE appointments SET {assignments} WHERE id = ?",
            (*_appointment_values(appt), appt.id),
        )


def get_appointment(conn: sqlite3.Connection, appt_id: int) -> Appointment | None:
    row = conn.execute("SELECT * FROM appointments WHERE id = ?", (appt_id,)).fetchone()
    return _row_to_appointment(row) if row else None


def list_appointments(
    conn: sqlite3.Connection,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[Appointment]:
    """Appointments between two dates (inclusive), ordered by date, time and dock."""
    sql, params = "SELECT * FROM appointments WHERE 1 = 1", []
    if from_date:
        sql += " AND date >= ?"
        params.append(from_date.isoformat())
    if to_date:
        sql += " AND date <= ?"
        params.append(to_date.isoformat())
    sql += " ORDER BY date, start_time, dock_id"
    return [_row_to_appointment(r) for r in conn.execute(sql, params)]


def list_appointments_for_day(conn: sqlite3.Connection, day: date) -> list[Appointment]:
    return list_appointments(conn, day, day)

"""A truck's trip through the gate, using the rules and the database together."""

from datetime import date, datetime

import pytest

from core import db
from core.models import Status
from core.rules import BookingError, apply_transition
from data.seed import seed

WED = date(2026, 11, 4)


@pytest.fixture
def conn(tmp_path):
    connection = db.connect(tmp_path / "test.db")
    seed(connection, today=WED)
    yield connection
    connection.close()


def find(conn, plate):
    return next(a for a in db.list_appointments_for_day(conn, WED) if a.truck_plate == plate)


def step(conn, plate, status, hhmm):
    appt = find(conn, plate)
    now = datetime.combine(WED, datetime.strptime(hhmm, "%H:%M").time())
    updated = apply_transition(appt, status, now, db.list_appointments_for_day(conn, WED))
    db.update_appointment(conn, updated)
    return db.get_appointment(conn, appt.id)


def test_booked_truck_goes_gate_to_dock_to_done(conn):
    # Alpine Cargo, D6 13:00 outbound, booked in the seed
    step(conn, "AC-129-LP", Status.ARRIVED, "12:50")
    step(conn, "AC-129-LP", Status.AT_DOCK, "13:00")
    done = step(conn, "AC-129-LP", Status.COMPLETED, "13:55")
    assert done.status == Status.COMPLETED
    assert (done.arrived_at.hour, done.docked_at.hour, done.completed_at.minute) == (12, 13, 55)


def test_waiting_truck_cannot_take_an_occupied_dock(conn):
    # FR-447-BV (waiting for D3) takes the dock, then a second D3 truck tries to follow it.
    step(conn, "FR-447-BV", Status.AT_DOCK, "11:00")
    second = find(conn, "SE-215-DA")  # the cancelled D3 booking, turned into a waiting truck
    second.status, second.arrived_at = Status.ARRIVED, datetime(2026, 11, 4, 11, 0)
    db.update_appointment(conn, second)
    with pytest.raises(BookingError, match="occupied"):
        step(conn, "SE-215-DA", Status.AT_DOCK, "11:05")


def test_completing_frees_the_dock(conn):
    step(conn, "CC-903-JN", Status.COMPLETED, "11:30")  # was at D1
    assert all(a.status != Status.AT_DOCK for a in db.list_appointments_for_day(conn, WED) if a.dock_id == "D1")


def test_no_show_only_after_grace_period(conn):
    # Alpine Cargo D6 13:00: too early at 13:20, allowed at 13:30
    with pytest.raises(BookingError):
        step(conn, "AC-129-LP", Status.NO_SHOW, "13:20")
    assert step(conn, "AC-129-LP", Status.NO_SHOW, "13:30").status == Status.NO_SHOW

from collections import Counter
from datetime import date, datetime, time

import pytest

from core import db
from core.models import Direction, DockType, Status
from core.rules import validate_booking
from data.seed import DOCKS, NEXT_DAY, TODAY, demo_days, seed

WED = date(2026, 11, 4)


@pytest.fixture
def conn(tmp_path):
    connection = db.connect(tmp_path / "test.db")
    yield connection
    connection.close()


@pytest.fixture
def seeded(conn):
    seed(conn, today=WED)
    return conn


def test_new_database_is_empty(conn):
    assert db.is_empty(conn)


def test_appointment_round_trip(seeded):
    original = db.list_appointments_for_day(seeded, WED)[0]
    loaded = db.get_appointment(seeded, original.id)
    assert loaded == original


def test_update_appointment(seeded):
    appt = db.list_appointments_for_day(seeded, WED)[-1]
    appt.status = Status.ARRIVED
    appt.arrived_at = datetime(2026, 11, 4, 18, 20)
    appt.notes = "Driver called ahead"
    db.update_appointment(seeded, appt)
    assert db.get_appointment(seeded, appt.id) == appt


def test_seed_docks_match_the_brief(seeded):
    docks = {d.id: d for d in db.list_docks(seeded)}
    assert sorted(docks) == ["D1", "D2", "D3", "D4", "D5", "D6"]
    assert {i for i, d in docks.items() if d.type == DockType.INBOUND} == {"D1", "D2", "D3"}
    assert {i for i, d in docks.items() if d.type == DockType.OUTBOUND} == {"D4", "D5"}
    assert docks["D6"].type == DockType.BOTH
    assert {i for i, d in docks.items() if d.reefer} == {"D2", "D6"}


def test_seed_covers_two_days(seeded):
    day1, day2 = demo_days(WED)
    assert len(db.list_appointments_for_day(seeded, day1)) == len(TODAY)
    assert len(db.list_appointments_for_day(seeded, day2)) == len(NEXT_DAY)
    assert 20 <= len(TODAY) + len(NEXT_DAY) <= 30


def test_seed_skips_sunday():
    assert demo_days(date(2026, 11, 7)) == (date(2026, 11, 7), date(2026, 11, 9))  # Sat → Mon
    assert demo_days(date(2026, 11, 8))[0] == date(2026, 11, 9)  # Sun → Mon


def test_every_seed_booking_passes_the_rules(seeded):
    docks = {d.id: d for d in DOCKS}
    all_appts = db.list_appointments(seeded)
    for appt in all_appts:
        assert validate_booking(appt, docks[appt.dock_id], all_appts) == [], appt


def test_seed_today_has_a_demo_mix_of_statuses(seeded):
    counts = Counter(a.status for a in db.list_appointments_for_day(seeded, WED))
    for status in Status:
        assert counts[status] >= 1, status


def test_list_appointments_filters_by_date(seeded):
    assert all(a.date == WED for a in db.list_appointments_for_day(seeded, WED))
    assert db.list_appointments_for_day(seeded, date(2026, 11, 20)) == []


def test_reseed_resets_ids(seeded):
    seed(seeded, today=WED)
    assert db.list_appointments(seeded)[0].id == 1

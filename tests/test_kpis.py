from datetime import date, datetime, time

import pytest

from core.kpis import day_kpis, dock_utilisation, open_minutes_per_dock, yard_wait_minutes
from core.models import Appointment, Direction, Dock, DockType, Status
from data.seed import DOCKS, TODAY, build_appointments

WED = date(2026, 11, 4)
D1 = Dock("D1", "Dock 1", DockType.INBOUND, reefer=False)
D2 = Dock("D2", "Dock 2", DockType.INBOUND, reefer=False)


def at(hhmm):
    return datetime.combine(WED, time.fromisoformat(hhmm))


def make(start="08:00", duration=60, dock="D1", status=Status.BOOKED, arrived=None, docked=None):
    return Appointment(
        carrier="Test", truck_plate="TS-000-AA", reference="ASN-1", direction=Direction.INBOUND,
        pallets=20, reefer=False, date=WED, start_time=time.fromisoformat(start), duration_min=duration,
        dock_id=dock, status=status, arrived_at=at(arrived) if arrived else None,
        docked_at=at(docked) if docked else None,
    )


def test_site_is_open_16_hours():
    assert open_minutes_per_dock() == 16 * 60


def test_utilisation_counts_booked_minutes_per_dock():
    appts = [make(duration=480), make(start="16:00", duration=96, dock="D2")]
    assert dock_utilisation(appts, [D1, D2]) == {"D1": 50.0, "D2": 10.0}


def test_cancelled_and_no_show_do_not_use_the_dock():
    appts = [make(duration=96, status=Status.CANCELLED), make(duration=96, status=Status.NO_SHOW)]
    assert dock_utilisation(appts, [D1]) == {"D1": 0.0}


def test_inactive_dock_is_left_out():
    closed = Dock("D2", "Dock 2", DockType.INBOUND, reefer=False, active=False)
    kpis = day_kpis([make(duration=96)], [D1, closed])
    assert kpis.utilisation_pct == pytest.approx(10.0)  # 96 of 960 min on the only active dock


def test_on_time_rate_and_breakdown():
    appts = [
        make(arrived="07:50"),  # on time
        make(arrived="08:15"),  # on time (edge)
        make(arrived="07:30"),  # early
        make(arrived="08:40"),  # late
        make(),                 # not arrived: not counted
    ]
    k = day_kpis(appts, [D1])
    assert (k.arrivals, k.early, k.on_time, k.late) == (4, 1, 2, 1)
    assert k.on_time_pct == 50.0


def test_average_yard_wait_uses_only_trucks_that_reached_a_dock():
    appts = [
        make(arrived="07:50", docked="08:00"),  # 10 min
        make(arrived="07:30", docked="08:00"),  # 30 min
        make(arrived="07:55"),                  # still waiting: not counted
    ]
    assert day_kpis(appts, [D1]).avg_yard_wait_min == 20.0
    assert yard_wait_minutes(appts[2]) is None


def test_empty_day_has_no_rates():
    k = day_kpis([], [D1])
    assert (k.bookings, k.utilisation_pct, k.on_time_pct, k.avg_yard_wait_min, k.no_shows) == (0, 0.0, None, None, 0)


def test_counts_no_shows_and_cancellations():
    appts = [make(status=Status.NO_SHOW), make(status=Status.CANCELLED), make()]
    k = day_kpis(appts, [D1])
    assert (k.bookings, k.no_shows, k.cancelled) == (2, 1, 1)


def test_seed_day_numbers():
    """Worked out by hand from the seed table, so a change to the seed shows up here."""
    k = day_kpis(build_appointments(WED, TODAY), DOCKS)
    assert k.utilisation_pct == pytest.approx(100 * 990 / (6 * 960))  # 17.2 %
    assert (k.arrivals, k.early, k.on_time, k.late) == (11, 4, 6, 1)
    assert k.on_time_pct == pytest.approx(100 * 6 / 11)
    assert k.avg_yard_wait_min == pytest.approx(107 / 8)
    assert (k.no_shows, k.cancelled, k.bookings) == (1, 1, 17)

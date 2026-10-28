from datetime import date, datetime, time

import pytest

from core.models import Appointment, Direction, Dock, DockType, Punctuality, Status
from core.rules import (
    BookingError,
    apply_transition,
    arrival_punctuality,
    arrival_text,
    can_mark_no_show,
    duration_for_pallets,
    format_minutes,
    next_statuses,
    suggest_slots,
    validate_booking,
    waiting_minutes,
    yard_overflow,
)

WED = date(2026, 11, 4)
SAT = date(2026, 11, 7)
SUN = date(2026, 11, 8)

D1 = Dock("D1", "Dock 1", DockType.INBOUND, reefer=False)
D2 = Dock("D2", "Dock 2", DockType.INBOUND, reefer=True)
D4 = Dock("D4", "Dock 4", DockType.OUTBOUND, reefer=False)
D6 = Dock("D6", "Dock 6", DockType.BOTH, reefer=True)
DOCKS = [D1, D2, D4, D6]


def make(start="08:00", pallets=10, dock="D1", day=WED, direction=Direction.INBOUND,
         reefer=False, status=Status.BOOKED, appt_id=None, carrier="Test Carrier"):
    return Appointment(
        carrier=carrier, truck_plate="TS-000-AA", reference="ASN-1", direction=direction,
        pallets=pallets, reefer=reefer, date=day, start_time=time.fromisoformat(start),
        duration_min=duration_for_pallets(pallets), dock_id=dock, status=status, id=appt_id,
    )


# --- Duration -----------------------------------------------------------------
@pytest.mark.parametrize(
    "pallets, minutes",
    [(1, 30), (10, 30), (11, 60), (26, 60), (27, 90), (33, 90)],
)
def test_duration_bands(pallets, minutes):
    assert duration_for_pallets(pallets) == minutes


@pytest.mark.parametrize("pallets", [0, -3, 34, 50])
def test_duration_rejects_out_of_range(pallets):
    with pytest.raises(BookingError):
        duration_for_pallets(pallets)


# --- Validation ---------------------------------------------------------------
def test_valid_booking_has_no_errors():
    assert validate_booking(make(), D1, []) == []


def test_saturday_is_open_sunday_is_closed():
    assert validate_booking(make(day=SAT), D1, []) == []
    assert any("closed" in e for e in validate_booking(make(day=SUN), D1, []))


def test_rejects_start_before_opening():
    assert any("opening hours" in e for e in validate_booking(make(start="05:30"), D1, []))


def test_rejects_slot_ending_after_closing():
    # 27 pallets = 90 min, 21:00 + 90 = 22:30
    assert any("opening hours" in e for e in validate_booking(make(start="21:00", pallets=27), D1, []))


def test_accepts_last_slot_ending_exactly_at_closing():
    assert validate_booking(make(start="21:30", pallets=5), D1, []) == []


def test_rejects_start_off_the_grid():
    assert any("grid" in e for e in validate_booking(make(start="08:15"), D1, []))


def test_rejects_dock_type_mismatch():
    errors = validate_booking(make(dock="D4"), D4, [])  # inbound load on outbound dock
    assert any("outbound-only" in e for e in errors)


def test_both_dock_accepts_either_direction():
    assert validate_booking(make(dock="D6"), D6, []) == []
    assert validate_booking(make(dock="D6", direction=Direction.OUTBOUND), D6, []) == []


def test_rejects_reefer_load_on_non_reefer_dock():
    assert any("reefer" in e for e in validate_booking(make(reefer=True), D1, []))


def test_dry_load_on_reefer_dock_is_fine():
    assert validate_booking(make(dock="D2"), D2, []) == []


def test_rejects_inactive_dock():
    closed = Dock("D9", "Dock 9", DockType.INBOUND, reefer=False, active=False)
    assert any("not active" in e for e in validate_booking(make(dock="D9"), closed, []))


def test_rejects_too_many_pallets():
    appt = make()
    appt.pallets = 40
    assert any("more than one truck" in e for e in validate_booking(appt, D1, []))


def test_rejects_overlap_on_same_dock():
    existing = [make(start="08:00", pallets=20, appt_id=1, carrier="Nordic Haul")]  # 08:00–09:00
    errors = validate_booking(make(start="08:30"), D1, existing)
    assert any("already booked" in e and "Nordic Haul" in e for e in errors)


def test_back_to_back_bookings_do_not_overlap():
    existing = [make(start="08:00", pallets=20, appt_id=1)]  # 08:00–09:00
    assert validate_booking(make(start="09:00"), D1, existing) == []


def test_same_time_on_other_dock_is_fine():
    existing = [make(start="08:00", dock="D2", appt_id=1)]
    assert validate_booking(make(start="08:00"), D1, existing) == []


@pytest.mark.parametrize("status", [Status.CANCELLED, Status.NO_SHOW])
def test_cancelled_and_no_show_do_not_block(status):
    existing = [make(start="08:00", appt_id=1, status=status)]
    assert validate_booking(make(start="08:00"), D1, existing) == []


@pytest.mark.parametrize("field, label", [
    ("carrier", "Carrier"), ("truck_plate", "Truck plate"), ("reference", "Reference"),
])
def test_rejects_missing_required_fields(field, label):
    appt = make()
    setattr(appt, field, "  ")
    assert f"{label} is required." in validate_booking(appt, D1, [])


def test_rejects_slot_that_already_started_when_now_given():
    appt = make(start="08:00")
    assert any("already started" in e for e in validate_booking(appt, D1, [], now=datetime(2026, 11, 4, 8, 10)))
    assert validate_booking(appt, D1, [], now=datetime(2026, 11, 4, 8, 0)) == []
    assert validate_booking(appt, D1, []) == []  # no `now` = no time check (e.g. existing bookings)


def test_booking_does_not_clash_with_itself():
    appt = make(appt_id=7)
    assert validate_booking(appt, D1, [appt]) == []


# --- Suggestions --------------------------------------------------------------
def test_suggests_three_slots_after_a_clash():
    existing = [make(start="08:00", pallets=20, appt_id=1)]  # D1 08:00–09:00
    request = make(start="08:00", pallets=20)
    options = suggest_slots(request, DOCKS, existing)
    assert len(options) == 3
    for opt in options:
        dock = next(d for d in DOCKS if d.id == opt.dock_id)
        assert validate_booking(opt, dock, existing) == []
    # D1 is taken 08:00–09:00, so the earliest options are the other inbound docks
    assert [(o.dock_id, o.start_time) for o in options] == [
        ("D2", time(8, 0)), ("D6", time(8, 0)), ("D2", time(8, 30)),
    ]


def test_suggestions_prefer_requested_dock_on_tie():
    request = make(start="08:00", dock="D6")
    assert suggest_slots(request, DOCKS, [], n=1)[0].dock_id == "D6"


def test_suggestions_only_use_compatible_docks():
    request = make(start="08:00", reefer=True)  # reefer inbound → D2 or D6 only
    options = suggest_slots(request, DOCKS, [], n=5)
    assert {o.dock_id for o in options} <= {"D2", "D6"}


def test_suggestions_roll_over_to_next_open_day():
    request = make(start="21:30", pallets=5, day=SAT, dock="D4", direction=Direction.OUTBOUND)
    existing = [make(start="21:30", pallets=5, day=SAT, dock="D4", direction=Direction.OUTBOUND, appt_id=1)]
    docks = [D4]
    options = suggest_slots(request, docks, existing, n=1)
    # Saturday is full at 21:30, Sunday is closed → Monday 06:00
    assert (options[0].date, options[0].start_time) == (date(2026, 11, 9), time(6, 0))


def test_suggestions_skip_slots_already_started():
    now = datetime(2026, 11, 4, 10, 10)
    options = suggest_slots(make(start="08:00"), [D1], [], n=1, now=now)
    assert options[0].start_time == time(10, 30)


def test_no_suggestions_for_too_many_pallets():
    appt = make()
    appt.pallets = 40
    assert suggest_slots(appt, DOCKS, []) == []


# --- Arrival ------------------------------------------------------------------
@pytest.mark.parametrize(
    "arrived, expected",
    [
        ("07:44", Punctuality.EARLY),
        ("07:45", Punctuality.ON_TIME),
        ("08:00", Punctuality.ON_TIME),
        ("08:15", Punctuality.ON_TIME),
        ("08:16", Punctuality.LATE),
    ],
)
def test_arrival_punctuality(arrived, expected):
    slot = datetime(2026, 11, 4, 8, 0)
    assert arrival_punctuality(slot, datetime.combine(WED, time.fromisoformat(arrived))) == expected


@pytest.mark.parametrize(
    "arrived, expected",
    [("08:10", "on time"), ("07:35", "25 min early"), ("09:10", "1 h 10 min late"),
     ("08:16", "16 min late"), ("06:00", "2 h early")],
)
def test_arrival_text(arrived, expected):
    slot = datetime(2026, 11, 4, 8, 0)
    assert arrival_text(slot, datetime.combine(WED, time.fromisoformat(arrived))) == expected


@pytest.mark.parametrize("minutes, expected", [(0, "0 min"), (25, "25 min"), (60, "1 h"), (220, "3 h 40 min")])
def test_format_minutes(minutes, expected):
    assert format_minutes(minutes) == expected


def test_no_show_only_after_30_minutes():
    appt = make(start="08:00")
    assert not can_mark_no_show(appt, datetime(2026, 11, 4, 8, 29))
    assert can_mark_no_show(appt, datetime(2026, 11, 4, 8, 30))


def test_no_show_only_for_booked_trucks():
    appt = make(start="08:00", status=Status.ARRIVED)
    assert not can_mark_no_show(appt, datetime(2026, 11, 4, 9, 0))


# --- Status transitions -------------------------------------------------------
def test_next_statuses():
    assert next_statuses(Status.BOOKED) == {Status.ARRIVED, Status.NO_SHOW, Status.CANCELLED}
    assert next_statuses(Status.ARRIVED) == {Status.AT_DOCK}
    assert next_statuses(Status.AT_DOCK) == {Status.COMPLETED}
    assert next_statuses(Status.COMPLETED) == set()


def test_full_happy_path_sets_timestamps():
    appt = make(start="08:00", appt_id=1)
    t1, t2, t3 = (datetime(2026, 11, 4, h, m) for h, m in [(7, 55), (8, 5), (8, 30)])
    appt = apply_transition(appt, Status.ARRIVED, t1)
    appt = apply_transition(appt, Status.AT_DOCK, t2)
    appt = apply_transition(appt, Status.COMPLETED, t3)
    assert (appt.status, appt.arrived_at, appt.docked_at, appt.completed_at) == (Status.COMPLETED, t1, t2, t3)


def test_cannot_skip_a_step():
    with pytest.raises(BookingError):
        apply_transition(make(), Status.COMPLETED, datetime(2026, 11, 4, 9, 0))


def test_cannot_mark_no_show_too_early():
    with pytest.raises(BookingError):
        apply_transition(make(start="08:00"), Status.NO_SHOW, datetime(2026, 11, 4, 8, 10))


def test_cannot_move_to_occupied_dock():
    busy = make(start="07:00", appt_id=1, status=Status.AT_DOCK)
    waiting = make(start="08:00", appt_id=2, status=Status.ARRIVED)
    with pytest.raises(BookingError, match="occupied"):
        apply_transition(waiting, Status.AT_DOCK, datetime(2026, 11, 4, 8, 0), [busy, waiting])


def test_original_appointment_is_not_changed():
    appt = make()
    apply_transition(appt, Status.ARRIVED, datetime(2026, 11, 4, 7, 50))
    assert appt.status == Status.BOOKED


# --- Yard ---------------------------------------------------------------------
def test_waiting_minutes():
    appt = make(status=Status.ARRIVED)
    appt.arrived_at = datetime(2026, 11, 4, 7, 40)
    assert waiting_minutes(appt, datetime(2026, 11, 4, 8, 5)) == 25
    assert waiting_minutes(make(), datetime(2026, 11, 4, 8, 5)) == 0


def test_yard_overflow_warning():
    assert yard_overflow(12) is None
    assert "13 trucks" in yard_overflow(13)

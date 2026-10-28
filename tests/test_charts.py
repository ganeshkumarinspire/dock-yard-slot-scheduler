from datetime import date, datetime

from charts import STATUS_COLORS, STATUS_LABELS, build_timeline, build_utilisation_chart, dock_label
from data.seed import DOCKS, TODAY, build_appointments

WED = date(2026, 11, 4)


def bar_count(fig):
    return sum(len(trace.x) for trace in fig.data)


def test_one_bar_per_booking():
    appointments = build_appointments(WED, TODAY)
    fig = build_timeline(appointments, DOCKS, WED)
    assert bar_count(fig) == len(appointments)


def test_every_dock_gets_a_row_even_when_empty():
    appointments = [a for a in build_appointments(WED, TODAY) if a.dock_id == "D1"]
    fig = build_timeline(appointments, DOCKS, WED)
    assert list(fig.layout.yaxis.categoryarray) == [dock_label(d) for d in DOCKS]


def test_empty_day_still_draws_the_grid():
    fig = build_timeline([], DOCKS, WED)
    assert bar_count(fig) == 0
    assert list(fig.layout.xaxis.range) == [datetime(2026, 11, 4, 6), datetime(2026, 11, 4, 22)]


def test_each_status_has_its_own_colour():
    assert set(STATUS_LABELS.values()) == set(STATUS_COLORS)
    assert len(set(STATUS_COLORS.values())) == len(STATUS_COLORS)
    fig = build_timeline(build_appointments(WED, TODAY), DOCKS, WED)
    for trace in fig.data:
        assert trace.marker.color == STATUS_COLORS[trace.name]


def test_now_line_only_on_the_day_shown():
    appointments = build_appointments(WED, TODAY)
    on_day = build_timeline(appointments, DOCKS, WED, now=datetime(2026, 11, 4, 11, 0))
    other_day = build_timeline(appointments, DOCKS, WED, now=datetime(2026, 11, 5, 11, 0))
    assert len(on_day.layout.shapes) == 1
    assert len(other_day.layout.shapes) == 0


def test_utilisation_chart_has_one_bar_per_dock_in_order():
    per_dock = {"D1": 40.0, "D2": 10.0, "D3": 0.0, "D4": 25.0, "D5": 5.0, "D6": 20.0}
    fig = build_utilisation_chart(per_dock, DOCKS, 16.7)
    assert list(fig.data[0].x) == list(per_dock.values())
    assert list(fig.data[0].text) == ["40%", "10%", "0%", "25%", "5%", "20%"]
    assert fig.layout.shapes[0].x0 == 16.7  # site average line


def test_inactive_docks_left_out():
    active = [d for d in DOCKS if d.id != "D6"]
    appointments = build_appointments(WED, TODAY)
    fig = build_timeline(appointments, active, WED)
    assert bar_count(fig) == sum(a.dock_id != "D6" for a in appointments)

"""Book a slot: booking form with rule checks and suggested alternatives."""

from __future__ import annotations

from datetime import datetime, time, timedelta

import streamlit as st

from charts import dock_label
from core import db
from core.models import CLOSE_TIME, OPEN_TIME, SLOT_GRID_MIN, Appointment, Direction
from core.rules import BookingError, duration_for_pallets, is_open_day, suggest_slots, validate_booking
from data.seed import first_open_day
from ui import current_time, get_conn, sidebar

st.set_page_config(page_title="Book a slot · Dock & Yard", page_icon="✍️", layout="wide")

conn = get_conn()
sidebar(conn)
docks = db.list_docks(conn, active_only=True)
docks_by_id = {d.id: d for d in docks}

GRID_TIMES = []
_t = datetime.combine(datetime.today(), OPEN_TIME)
while _t.time() < CLOSE_TIME:
    GRID_TIMES.append(_t.time())
    _t += timedelta(minutes=SLOT_GRID_MIN)

FIELDS = {
    "bk_carrier": "",
    "bk_plate": "",
    "bk_reference": "",
    "bk_direction": Direction.INBOUND,
    "bk_pallets": 12,
    "bk_reefer": False,
    "bk_date": current_time().date(),
    "bk_start": time(8, 0),
    "bk_dock": docks[0].id,
    "bk_notes": "",
}
for key, default in FIELDS.items():
    st.session_state.setdefault(key, default)


# --- Callbacks ----------------------------------------------------------------
def load_example() -> None:
    """A reefer load on a non-reefer dock: shows a rejection and suggestions."""
    st.session_state.update(
        bk_carrier="Polar Express Freight", bk_plate="PX-482-CF", bk_reference="ASN-40200",
        bk_direction=Direction.INBOUND, bk_pallets=20, bk_reefer=True,
        bk_date=first_open_day(current_time().date() + timedelta(days=1)),
        bk_start=time(6, 0), bk_dock="D1", bk_notes="Chilled yoghurt",
    )
    st.session_state.pop("bk_result", None)


def clear_form() -> None:
    st.session_state.update(FIELDS)


def save(appt: Appointment) -> None:
    """Re-check against the latest bookings, then save."""
    existing = db.list_appointments_for_day(conn, appt.date)
    errors = validate_booking(appt, docks_by_id[appt.dock_id], existing, current_time())
    if errors:
        st.session_state.bk_result = {"appt": appt, "errors": errors, "options": []}
        return
    appt.id = db.insert_appointment(conn, appt)
    st.session_state.bk_result = {"booked": appt}
    st.session_state.day = appt.date  # Day view opens on the booked day
    clear_form()


def submit(appt: Appointment) -> None:
    now = current_time()
    existing = db.list_appointments(conn, appt.date, appt.date + timedelta(days=8))
    errors = validate_booking(appt, docks_by_id[appt.dock_id], existing, now)
    if not errors:
        save(appt)
        return
    missing_info = any("required" in e for e in errors)
    options = [] if missing_info else suggest_slots(appt, docks, existing, n=3, now=now)
    st.session_state.bk_result = {"appt": appt, "errors": errors, "options": options}


# --- Form ---------------------------------------------------------------------
st.title("✍️ Book a slot")
st.caption(
    f"Site open {OPEN_TIME:%H:%M}–{CLOSE_TIME:%H:%M}, Monday–Saturday. "
    "Slot length comes from the pallet count."
)
st.button("Fill with an example", on_click=load_example,
          help="A chilled load on a dock without a reefer plug — shows a rejection and suggestions.")

left, right = st.columns(2)
with left:
    carrier = st.text_input("Carrier", key="bk_carrier")
    plate = st.text_input("Truck plate", key="bk_plate", placeholder="AB-123-CD")
    reference = st.text_input("Reference (PO / ASN)", key="bk_reference")
    direction = st.radio("Direction", list(Direction), key="bk_direction", horizontal=True,
                         format_func=lambda d: d.value.capitalize())
    pallets = st.number_input("Pallets", key="bk_pallets", min_value=1, max_value=99, step=1)
    reefer = st.checkbox("Reefer (temperature-controlled)", key="bk_reefer")
with right:
    day = st.date_input("Date", key="bk_date", format="DD/MM/YYYY")
    start = st.selectbox("Start time", GRID_TIMES, key="bk_start", format_func=lambda t: t.strftime("%H:%M"))
    dock_id = st.selectbox("Dock", list(docks_by_id), key="bk_dock",
                           format_func=lambda i: dock_label(docks_by_id[i]))
    notes = st.text_area("Notes", key="bk_notes", height=68)

    try:
        duration = duration_for_pallets(int(pallets))
        end = (datetime.combine(day, start) + timedelta(minutes=duration)).time()
        st.info(f"**Slot length: {duration} min** — {start:%H:%M} to {end:%H:%M}"
                + ("" if is_open_day(day) else " · ⚠️ the site is closed on Sundays"))
    except BookingError as exc:
        duration = None
        st.error(str(exc))

request = Appointment(
    carrier=carrier.strip(), truck_plate=plate.strip().upper(), reference=reference.strip(),
    direction=Direction(direction), pallets=int(pallets), reefer=reefer, date=day,
    start_time=start, duration_min=duration or 0, dock_id=dock_id, notes=notes.strip(),
)
st.button("Book slot", type="primary", on_click=submit, args=(request,), disabled=duration is None)


# --- Result -------------------------------------------------------------------
def describe(appt: Appointment) -> str:
    return f"{appt.date:%a %d %b} · {appt.start_time:%H:%M}–{appt.end:%H:%M} · {dock_label(docks_by_id[appt.dock_id])}"


result = st.session_state.get("bk_result")
if result and "booked" in result:
    booked = result["booked"]
    st.success(f"✅ Booked #{booked.id}: **{booked.carrier}** ({booked.truck_plate}) — {describe(booked)}")
    st.page_link("pages/1_Day_view.py", label="See it on the Day view", icon="🗓️")
elif result:
    st.error("**This booking can't go ahead:**\n" + "\n".join(f"- {e}" for e in result["errors"]))
    if result["options"]:
        st.markdown("**Next free slots that would work:**")
        for i, option in enumerate(result["options"]):
            col_text, col_btn = st.columns([4, 1], vertical_alignment="center")
            col_text.markdown(f"**{i + 1}.** {describe(option)}")
            col_btn.button("Book this one", key=f"bk_option_{i}", on_click=save, args=(option,))
    elif not any("required" in e for e in result["errors"]):
        st.warning("No free slot found in the next 7 days for this load.")

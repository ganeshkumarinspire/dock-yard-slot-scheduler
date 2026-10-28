"""Yard & gate: check trucks in, move them to a dock, complete them, mark no-shows."""

from __future__ import annotations

import streamlit as st

from core import db
from core.models import YARD_SPOTS, Appointment, Status
from core.rules import (
    BookingError,
    apply_transition,
    arrival_text,
    can_mark_no_show,
    format_minutes,
    waiting_minutes,
    yard_overflow,
)
from ui import current_time, get_conn, sidebar

st.set_page_config(page_title="Yard & gate · Dock & Yard", page_icon="🚧", layout="wide")

conn = get_conn()
sidebar(conn)
now = current_time()
today = db.list_appointments_for_day(conn, now.date())

ACTION_WORDS = {
    Status.ARRIVED: "checked in",
    Status.AT_DOCK: "moved to its dock",
    Status.COMPLETED: "completed",
    Status.NO_SHOW: "marked as no-show",
    Status.CANCELLED: "cancelled",
}


def change_status(appt: Appointment, new_status: Status) -> None:
    """Apply a status change through the rules, save it, and leave a message for the next run."""
    appt = db.get_appointment(conn, appt.id)  # latest copy, in case it changed since the page drew
    try:
        updated = apply_transition(appt, new_status, now, db.list_appointments_for_day(conn, now.date()))
    except BookingError as exc:
        st.session_state.yard_msg = ("error", str(exc))
        return
    db.update_appointment(conn, updated)
    text = f"{updated.truck_plate} ({updated.carrier}) {ACTION_WORDS[new_status]}"
    if new_status == Status.ARRIVED:
        text += f" — {arrival_text(updated.start, now)}"
    st.session_state.yard_msg = ("success", text + ".")


def who(appt: Appointment) -> str:
    return f"**{appt.truck_plate}** · {appt.carrier} · {appt.reference}"


def slot(appt: Appointment) -> str:
    return f"{appt.dock_id} · {appt.start_time:%H:%M}–{appt.end:%H:%M}"


# --- Header -------------------------------------------------------------------
st.title("🚧 Yard & gate")
st.caption(f"{now:%A %d %B %Y} · it is **{now:%H:%M}** · change the time in the sidebar")

if msg := st.session_state.pop("yard_msg", None):
    (st.success if msg[0] == "success" else st.error)(msg[1])

expected = [a for a in today if a.status == Status.BOOKED]
waiting = sorted((a for a in today if a.status == Status.ARRIVED), key=lambda a: a.start)
at_dock = sorted((a for a in today if a.status == Status.AT_DOCK), key=lambda a: a.dock_id)
done = [a for a in today if a.status in {Status.COMPLETED, Status.NO_SHOW, Status.CANCELLED}]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Expected at gate", len(expected))
c2.metric("Waiting in yard", f"{len(waiting)} / {YARD_SPOTS}")
c3.metric("At a dock", len(at_dock))
c4.metric("Longest wait", format_minutes(max((waiting_minutes(a, now) for a in waiting), default=0)))

if warning := yard_overflow(len(waiting)):
    st.warning(f"⚠️ {warning}")
st.progress(min(len(waiting) / YARD_SPOTS, 1.0), text=f"Yard parking: {len(waiting)} of {YARD_SPOTS} spots used")

# --- Gate ---------------------------------------------------------------------
st.subheader("🚪 Gate — expected today")
plate_filter = st.text_input("Find a truck by plate", placeholder="e.g. AC-129", key="yard_plate").strip().upper()
shown = [a for a in expected if plate_filter in a.truck_plate.upper()]
if not shown:
    st.info("No trucks expected." if not plate_filter else f"No expected truck matches '{plate_filter}'.")
for appt in shown:
    cols = st.columns([4, 2, 1.2, 1.2, 1.2], vertical_alignment="center")
    cols[0].markdown(who(appt))
    cols[1].markdown(slot(appt) + (" · :red[overdue]" if now >= appt.start else ""))
    cols[2].button("Check in", key=f"in_{appt.id}", type="primary", width="stretch",
                   on_click=change_status, args=(appt, Status.ARRIVED))
    cols[3].button("No-show", key=f"ns_{appt.id}", width="stretch",
                   disabled=not can_mark_no_show(appt, now),
                   help="Allowed 30 minutes after the slot start.",
                   on_click=change_status, args=(appt, Status.NO_SHOW))
    cols[4].button("Cancel", key=f"cx_{appt.id}", width="stretch",
                   on_click=change_status, args=(appt, Status.CANCELLED))

# --- Yard ---------------------------------------------------------------------
st.subheader("🅿️ Yard — trucks waiting")
if not waiting:
    st.info("The yard is empty.")
busy_docks = {a.dock_id: a for a in at_dock}
for appt in waiting:
    cols = st.columns([4, 2, 2.4, 1.2], vertical_alignment="center")
    cols[0].markdown(who(appt))
    cols[1].markdown(slot(appt))
    cols[2].markdown(
        f"Arrived {appt.arrived_at:%H:%M} ({arrival_text(appt.start, appt.arrived_at)}) · "
        f"waiting **{format_minutes(waiting_minutes(appt, now))}**"
    )
    blocker = busy_docks.get(appt.dock_id)
    cols[3].button(f"To {appt.dock_id}", key=f"dock_{appt.id}", type="primary", width="stretch",
                   disabled=blocker is not None,
                   help=f"{appt.dock_id} is busy with {blocker.truck_plate}" if blocker else "Move to its dock",
                   on_click=change_status, args=(appt, Status.AT_DOCK))

# --- Docks --------------------------------------------------------------------
st.subheader("🏭 At the docks")
if not at_dock:
    st.info("No truck at a dock.")
for appt in at_dock:
    minutes = int((now - appt.docked_at).total_seconds() // 60) if appt.docked_at else 0
    overrun = appt.docked_at and minutes > appt.duration_min
    cols = st.columns([4, 2, 2.4, 1.2], vertical_alignment="center")
    cols[0].markdown(who(appt))
    cols[1].markdown(slot(appt))
    cols[2].markdown(
        f"Docked {appt.docked_at:%H:%M} · {format_minutes(minutes)} of {format_minutes(appt.duration_min)}"
        + (" · :orange[running over]" if overrun else "")
    )
    cols[3].button("Complete", key=f"done_{appt.id}", type="primary", width="stretch",
                   on_click=change_status, args=(appt, Status.COMPLETED))

# --- Finished -----------------------------------------------------------------
with st.expander(f"Finished today ({len(done)})"):
    for appt in sorted(done, key=lambda a: a.start):
        label = {Status.COMPLETED: "✅ completed", Status.NO_SHOW: "❌ no-show", Status.CANCELLED: "🚫 cancelled"}
        st.markdown(f"{who(appt)} · {slot(appt)} · {label[appt.status]}")

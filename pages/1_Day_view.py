"""Day view: the dock plan for one day as a timeline."""

from __future__ import annotations

from collections import Counter
from datetime import timedelta

import streamlit as st

from charts import STATUS_LABELS, build_timeline
from core import db
from core.rules import is_open_day
from ui import appointments_table, current_time, get_conn, sidebar

st.set_page_config(page_title="Day view · Dock & Yard", page_icon="🗓️", layout="wide")

conn = get_conn()
sidebar(conn)

if "day" not in st.session_state:
    st.session_state.day = current_time().date()


def shift_day(days: int) -> None:
    st.session_state.day += timedelta(days=days)


st.title("🗓️ Day view")

prev_col, date_col, next_col, _ = st.columns([1, 3, 1, 7], vertical_alignment="bottom")
prev_col.button("◀", on_click=shift_day, args=(-1,), help="Previous day", width="stretch")
date_col.date_input("Day", key="day", format="DD/MM/YYYY")
next_col.button("▶", on_click=shift_day, args=(1,), help="Next day", width="stretch")

day = st.session_state.day
st.caption(f"{day:%A %d %B %Y}")

if not is_open_day(day):
    st.info("The site is closed on Sundays — no slots to show.")
    st.stop()

docks = db.list_docks(conn, active_only=True)
appointments = db.list_appointments_for_day(conn, day)

counts = Counter(STATUS_LABELS[a.status] for a in appointments)
tiles = st.columns(len(STATUS_LABELS))
for tile, label in zip(tiles, STATUS_LABELS.values()):
    tile.metric(label, counts.get(label, 0))

st.plotly_chart(
    build_timeline(appointments, docks, day, now=current_time()),
    width="stretch",
    theme=None,  # Streamlit's theme overrides the hatched bar fill
    config={"displayModeBar": False},
)

if appointments:
    st.subheader("Bookings")
    st.dataframe(appointments_table(appointments), hide_index=True, width="stretch")
else:
    st.info("No bookings on this day yet.")

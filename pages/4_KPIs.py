"""KPIs for the selected day."""

from __future__ import annotations

import streamlit as st

from charts import build_utilisation_chart
from core import db
from core.kpis import day_kpis, dock_utilisation
from core.rules import format_minutes, is_open_day
from ui import current_time, get_conn, sidebar

st.set_page_config(page_title="KPIs · Dock & Yard", page_icon="📊", layout="wide")

conn = get_conn()
sidebar(conn)

st.title("📊 KPIs")
day = st.date_input("Day", value=current_time().date(), format="DD/MM/YYYY", width=200)
st.caption(f"{day:%A %d %B %Y}")

if not is_open_day(day):
    st.info("The site is closed on Sundays — nothing to measure.")
    st.stop()

docks = db.list_docks(conn, active_only=True)
appointments = db.list_appointments_for_day(conn, day)
k = day_kpis(appointments, docks)

c1, c2, c3, c4 = st.columns(4, border=True)
c1.metric("Dock utilisation", f"{k.utilisation_pct:.0f}%",
          help="Booked minutes ÷ opening hours of all active docks. Cancelled and no-show bookings don't count.")
c1.caption(f"{k.bookings} bookings across {len(docks)} docks")

c2.metric("On-time arrivals", "–" if k.on_time_pct is None else f"{k.on_time_pct:.0f}%",
          help="Arrived within ±15 minutes of the slot start, out of all trucks that arrived.")
c2.caption(f"{k.on_time} of {k.arrivals} arrived · {k.early} early · {k.late} late"
           if k.arrivals else "No arrivals yet")

c3.metric("Average yard wait", "–" if k.avg_yard_wait_min is None else format_minutes(round(k.avg_yard_wait_min)),
          help="From check-in at the gate to reaching the dock, for trucks that have reached a dock.")
c3.caption("Gate → dock")

c4.metric("No-shows", k.no_shows,
          help="Trucks marked no-show (not arrived 30 minutes after their slot start).")
c4.caption(f"{k.cancelled} cancelled")

st.subheader("Dock utilisation")
st.caption("Share of opening hours (06:00–22:00) booked on each dock")
st.plotly_chart(
    build_utilisation_chart(dock_utilisation(appointments, docks), docks, k.utilisation_pct),
    width="stretch",
    theme=None,
    config={"displayModeBar": False},
)

with st.expander("How these are calculated"):
    st.markdown(
        """
- **Dock utilisation** — minutes booked on each active dock ÷ 16 opening hours (960 min);
  the headline is the average across docks. Cancelled and no-show slots are left out.
- **On-time arrivals** — trucks that checked in within ±15 min of their slot start,
  out of all trucks that checked in that day.
- **Average yard wait** — time from check-in to reaching the dock, for trucks that got to a dock.
  Trucks still waiting are not counted yet; see *Yard & gate* for live waits.
- **No-shows** — bookings marked no-show that day.
"""
    )

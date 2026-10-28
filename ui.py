"""Small Streamlit helpers shared by the app and its pages."""

from __future__ import annotations

import sqlite3
from datetime import datetime

import pandas as pd
import streamlit as st

from core import db
from core.models import Appointment
from data.seed import DEMO_TIME, demo_days, seed


def current_time() -> datetime:
    """The app's idea of 'now': the demo clock when it's on, otherwise the real time."""
    if st.session_state.get("clock_on", True):
        return datetime.combine(demo_days()[0], st.session_state.get("clock_time", DEMO_TIME))
    return datetime.now().replace(second=0, microsecond=0)


def _keep(widget_key: str, key: str) -> None:
    # Widget values are dropped when you change page; copy them to a plain key that stays.
    st.session_state[key] = st.session_state[widget_key]


def sidebar(conn: sqlite3.Connection) -> None:
    """Demo clock and reset button, shown on every page."""
    with st.sidebar:
        st.markdown("**🕒 Clock**")
        st.toggle("Use demo clock", value=st.session_state.get("clock_on", True), key="_clock_on",
                  on_change=_keep, args=("_clock_on", "clock_on"),
                  help="The demo data is set up as the yard looks at about 11:00 today.")
        if st.session_state.get("clock_on", True):
            st.time_input("Demo time", value=st.session_state.get("clock_time", DEMO_TIME), key="_clock_time",
                          step=300, on_change=_keep, args=("_clock_time", "clock_time"))
        st.caption(f"Now: {current_time():%a %d %b, %H:%M}")

        st.divider()
        st.markdown("**Demo data**")
        if st.button("Reset demo data"):
            seed(conn)
            st.toast("Demo data reloaded.")
            st.rerun()


def get_conn() -> sqlite3.Connection:
    """Open the database, loading the demo data the first time."""
    conn = db.connect()
    if db.is_empty(conn):
        seed(conn)
    return conn


def appointments_table(appointments: list[Appointment]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Dock": a.dock_id,
                "Start": a.start_time.strftime("%H:%M"),
                "End": a.end.strftime("%H:%M"),
                "Carrier": a.carrier,
                "Plate": a.truck_plate,
                "Reference": a.reference,
                "Direction": a.direction.value,
                "Pallets": a.pallets,
                "Reefer": "yes" if a.reefer else "",
                "Status": a.status.value.replace("_", " "),
                "Arrived": a.arrived_at.strftime("%H:%M") if a.arrived_at else "",
                "Notes": a.notes,
            }
            for a in appointments
        ]
    )

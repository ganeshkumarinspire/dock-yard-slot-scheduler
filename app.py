"""Dock & Yard Slot Scheduler — home page."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core import db
from core.models import Status
from ui import appointments_table, current_time, get_conn, sidebar

st.set_page_config(page_title="Dock & Yard Scheduler", page_icon="🚚", layout="wide")

conn = get_conn()
sidebar(conn)
today = current_time().date()

st.title("🚚 Dock & Yard Slot Scheduler")
st.caption("Book truck slots at the docks and keep track of trucks waiting in the yard.")

appointments = db.list_appointments_for_day(conn, today)
waiting = sum(a.status == Status.ARRIVED for a in appointments)
col1, col2, col3 = st.columns(3)
col1.metric("Bookings today", len(appointments))
col2.metric("Waiting in yard", waiting)
col3.metric("Completed", sum(a.status == Status.COMPLETED for a in appointments))

st.subheader("Docks")
docks = db.list_docks(conn)
st.dataframe(
    pd.DataFrame(
        [
            {"Dock": d.id, "Name": d.name, "Type": d.type.value,
             "Reefer": "yes" if d.reefer else "", "Active": "yes" if d.active else "no"}
            for d in docks
        ]
    ),
    hide_index=True,
)

st.subheader(f"Appointments on {today:%A %d %B %Y}")
st.dataframe(appointments_table(appointments), hide_index=True, width="stretch")

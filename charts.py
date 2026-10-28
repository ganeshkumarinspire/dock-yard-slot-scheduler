"""Plotly figures for the app. No Streamlit here, so figures can be tested."""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from core.models import CLOSE_TIME, OPEN_TIME, Appointment, Dock, Status

STATUS_LABELS = {
    Status.BOOKED: "Booked",
    Status.ARRIVED: "In yard",
    Status.AT_DOCK: "At dock",
    Status.COMPLETED: "Completed",
    Status.NO_SHOW: "No-show",
    Status.CANCELLED: "Cancelled",
}

# Fixed colour per status, so a status always looks the same whatever is on screen.
STATUS_COLORS = {
    "Booked": "#2a78d6",     # blue
    "In yard": "#eda100",    # amber
    "At dock": "#6250d6",    # violet
    "Completed": "#008300",  # green
    "No-show": "#e34948",    # red
    "Cancelled": "#a8a7a0",  # grey
}

# Hatching is a second cue next to colour (helps colour-blind readers and print).
STATUS_PATTERNS = {label: "" for label in STATUS_COLORS} | {"No-show": "x", "Cancelled": "/"}

TEXT_MUTED = "#52514e"
TEXT_PRIMARY = "#0b0b0b"
GRID = "#e6e5e0"
SERIES_1 = "#2a78d6"


def dock_label(dock: Dock) -> str:
    extras = [dock.type.value] + (["reefer"] if dock.reefer else [])
    return f"{dock.id} · {' · '.join(extras)}"


def _timeline_rows(appointments: list[Appointment], labels: dict[str, str]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Start": a.start,
                "End": a.end,
                "Dock": labels[a.dock_id],
                "Status": STATUS_LABELS[a.status],
                "Carrier": a.carrier,
                "Plate": a.truck_plate,
                "Reference": a.reference,
                "Pallets": a.pallets,
                "Slot": f"{a.start:%H:%M}–{a.end:%H:%M}",
                "Arrival": a.arrived_at.strftime("%H:%M") if a.arrived_at else "–",
                "Reefer": " · reefer" if a.reefer else "",
            }
            for a in appointments
            if a.dock_id in labels
        ]
    )


def build_timeline(
    appointments: list[Appointment],
    docks: list[Dock],
    day: date,
    now: datetime | None = None,
) -> go.Figure:
    """Gantt-style day plan: one row per dock, one bar per booking, coloured by status."""
    labels = {d.id: dock_label(d) for d in docks}
    rows = _timeline_rows(appointments, labels)

    if rows.empty:
        fig = go.Figure()
    else:
        fig = px.timeline(
            rows,
            x_start="Start",
            x_end="End",
            y="Dock",
            color="Status",
            pattern_shape="Status",
            text="Carrier",
            color_discrete_map=STATUS_COLORS,
            pattern_shape_map=STATUS_PATTERNS,
            category_orders={"Status": list(STATUS_COLORS)},
            custom_data=["Carrier", "Plate", "Reference", "Pallets", "Slot", "Status", "Arrival", "Reefer"],
        )
        fig.update_traces(
            hovertemplate=(
                "<b>%{customdata[0]}</b> · %{customdata[1]}<br>"
                "%{customdata[4]} · %{customdata[5]}<br>"
                "%{customdata[2]} · %{customdata[3]} pallets%{customdata[7]}<br>"
                "Arrived: %{customdata[6]}<extra></extra>"
            ),
            textposition="inside",
            insidetextanchor="middle",
            marker_line_color="#ffffff",
            marker_line_width=2,
            marker_pattern_fgcolor="#ffffff",
        )
        for trace in fig.data:  # solid status colour behind the white hatching
            trace.marker.pattern.bgcolor = trace.marker.color

    open_at, close_at = datetime.combine(day, OPEN_TIME), datetime.combine(day, CLOSE_TIME)
    dock_order = [labels[d.id] for d in docks]

    fig.update_layout(
        height=110 + 56 * len(docks),
        margin=dict(l=10, r=10, t=70, b=10),
        bargap=0.3,
        legend=dict(orientation="h", yanchor="top", y=0.99, yref="container", x=0, title_text=""),
        uniformtext=dict(minsize=10, mode="hide"),  # hide labels that don't fit their bar
        hoverlabel=dict(bgcolor="white", font_color="#0b0b0b"),
        plot_bgcolor="rgba(0,0,0,0)",
    )
    fig.update_xaxes(
        type="date",
        range=[open_at, close_at],
        dtick=60 * 60 * 1000,
        tickformat="%H:%M",
        gridcolor=GRID,
        tickfont_color=TEXT_MUTED,
        title_text="",
    )
    fig.update_yaxes(
        type="category",
        categoryorder="array",
        categoryarray=dock_order,
        range=[len(dock_order) - 0.5, -0.5],  # D1 at the top, empty docks still shown
        tickfont_color=TEXT_MUTED,
        showgrid=False,
        automargin=True,
        title_text="",
    )

    if now and open_at <= now <= close_at:
        fig.add_shape(
            type="line", x0=now, x1=now, y0=0, y1=1, yref="paper",
            line=dict(color="#0b0b0b", width=2, dash="dot"),
        )
        fig.add_annotation(
            x=now, y=1, yref="paper", text=f"Now {now:%H:%M}", showarrow=False,
            yanchor="bottom", font=dict(size=11, color="#0b0b0b"),
        )
    return fig


def build_utilisation_chart(per_dock: dict[str, float], docks: list[Dock], site_pct: float) -> go.Figure:
    """Horizontal bars: % of opening hours booked on each dock, with the site average marked."""
    labels = {d.id: dock_label(d) for d in docks}
    ids = [d for d in per_dock if d in labels]
    fig = go.Figure(
        go.Bar(
            x=[per_dock[d] for d in ids],
            y=[labels[d] for d in ids],
            orientation="h",
            marker=dict(color=SERIES_1, cornerradius=4),
            text=[f"{per_dock[d]:.0f}%" for d in ids],
            textposition="inside",  # inside the bar end, clear of the site-average line
            insidetextanchor="end",
            textfont_color="#ffffff",
            hovertemplate="%{y}<br><b>%{x:.1f}%</b> of opening hours booked<extra></extra>",
        )
    )
    fig.add_vline(x=site_pct, line=dict(color=TEXT_PRIMARY, width=1.5, dash="dot"), layer="below")
    fig.add_annotation(x=site_pct, y=1, yref="paper", yanchor="bottom", showarrow=False,
                       text=f"Site {site_pct:.0f}%", font=dict(size=11, color=TEXT_PRIMARY))
    fig.update_layout(
        height=80 + 44 * len(ids),
        margin=dict(l=10, r=40, t=30, b=10),
        bargap=0.35,
        showlegend=False,
        plot_bgcolor="rgba(0,0,0,0)",
        hoverlabel=dict(bgcolor="white", font_color=TEXT_PRIMARY),
    )
    fig.update_xaxes(range=[0, 100], ticksuffix="%", dtick=25, gridcolor=GRID, tickfont_color=TEXT_MUTED,
                     zeroline=False)
    fig.update_yaxes(autorange="reversed", tickfont_color=TEXT_MUTED, automargin=True, ticksuffix="  ")
    return fig

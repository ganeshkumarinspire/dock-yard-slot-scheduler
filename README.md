# 🚚 Dock & Yard Slot Scheduler

[![Open the live demo](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://dock-yard-slot-scheduler-4hzx46hkp3zzb5pzp5g8rt.streamlit.app/)

**▶️ Try it live: [https://dock-yard-slot-scheduler-4hzx46hkp3zzb5pzp5g8rt.streamlit.app](https://dock-yard-slot-scheduler-4hzx46hkp3zzb5pzp5g8rt.streamlit.app/)** (free demo, no sign-up; demo data resets now and then)

**Book truck slots at warehouse docks and keep track of trucks waiting in the yard.**

A small web app for a warehouse planner: book loading/unloading slots, see the day
on a timeline, check trucks in at the gate, move them to a dock, and watch the
day's KPIs. Built with Python, Streamlit, SQLite and Plotly.

![Screenshot placeholder](docs/screenshots/01-day-view.png)
*(screenshot coming soon)*

---

## What it does

| Screen | What you get |
|---|---|
| 🗓️ **Day view** | Timeline with docks as rows and time across, coloured by status; ◀ ▶ and a date picker to move between days; hover a bar for carrier, plate, reference and pallets |
| ✍️ **Book a slot** | Booking form that shows the slot length as you type the pallet count, explains every reason a booking is refused, and offers the next 3 free slots with a one-click **Book this one**. Try **Fill with an example** for a chilled load sent to a dock with no reefer plug |
| 🚧 **Yard & gate** | Check trucks in at the gate (shows early / on time / late), see who is waiting and for how long, move them to their dock, complete them, cancel or mark no-shows. Buttons only appear active when the rules allow the move, and a warning shows when the yard is full |
| 📊 **KPIs** | For any day: dock utilisation %, on-time arrival %, average yard wait and no-shows, plus a utilisation bar per dock against the site average. A fold-out explains how each number is worked out |

## Booking rules

- Site open **06:00–22:00, Monday–Saturday**; slots start on a **30-minute grid**.
- Slot length from pallets: **≤10 → 30 min**, **11–26 → 60 min**, **27–33 → 90 min**; more than 33 is rejected (more than one truck).
- A booking is rejected if carrier, plate or reference is missing, the slot has already started, it is outside opening hours, the dock type doesn't match the direction,
  a reefer load is put on a non-reefer dock, or it overlaps another booking on the same dock.
- Arrival is **on time** within ±15 minutes of the slot start, otherwise early or late.
- A truck not arrived **30 minutes** after its slot start can be marked **no-show**.
- A warning shows when more trucks are waiting than the **12 yard parking spots**.

## Demo data

6 docks (D1–D3 inbound, D4–D5 outbound, D6 both; D2 and D6 have reefer plugs) and
26 invented appointments for today and the next open day. Today's bookings are
set up as the yard would look at about 11:00: some trucks done, two at a dock,
three waiting in the yard, one no-show and one cancellation.

**Demo clock.** The sidebar has a demo clock, on by default at 11:00 today, so the
story above makes sense whenever you open the app. Move it forward (say to 14:35) to
see a truck go overdue and the **No-show** button switch on. Turn it off to use the
real time. Refreshing the browser puts the clock back to 11:00.

## Run it

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
streamlit run app.py
```

The database (`data/dock_yard.db`) is created and filled with demo data on first run.
Reset it any time with the **Reset demo data** button in the sidebar, or:

```bash
python -m data.seed
```

## Run the tests

```bash
python -m pytest -q
```

## Project structure

```
app.py            home page
pages/            one file per screen
ui.py             shared Streamlit helpers
charts.py         Plotly figures (no Streamlit, so they can be tested)
core/             business logic, no Streamlit (models, db, rules, kpis)
data/seed.py      demo data
tests/            pytest tests
```

## Out of scope (for now)

Logins, a carrier self-service portal, email notifications, real company data.

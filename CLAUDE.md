# Dock & Yard Slot Scheduler — conventions

Portfolio project: a Streamlit app for a warehouse planner who books truck
loading/unloading slots at docks and tracks trucks waiting in the yard.
Keep it clean, simple and easy to demo.

## Stack
- Python 3.11+ (developed on 3.14), Streamlit UI, SQLite storage (plain `sqlite3`, no ORM),
  Plotly for charts, pytest for tests.
- Virtual env in `.venv/`; dependencies in `requirements.txt`.

## Layout
- `app.py` — home page; `pages/` — one file per screen (`1_Day_view.py`, …).
- `ui.py` — small Streamlit helpers shared by pages: DB connection, tables, the sidebar
  (demo clock + reset). Every page calls `sidebar(conn)` and uses `current_time()` for "now".
  Widget values vanish when you change page, so the clock is copied to plain session keys.
- `charts.py` — Plotly figures, no Streamlit (tested in `tests/test_charts.py`). Status colours live here.
  Pass `theme=None` to `st.plotly_chart`, otherwise Streamlit overrides the hatched bars.
- `core/` — **no Streamlit imports**. `models.py` (dataclasses, enums, site constants),
  `db.py` (schema + CRUD), `rules.py` (business rules), `kpis.py` (KPI maths).
- `data/seed.py` — demo docks and appointments; `python -m data.seed` resets the DB.
- `tests/` — pytest; DB tests use a temp file, never `data/dock_yard.db`.

## Rules of the road
- Business logic lives in `core/`, pages only gather input and display results.
- Anything time-dependent takes `now` as a parameter — never call `datetime.now()` in `core/`.
- Every rule gets a pytest test. Run `python -m pytest -q` before handing over.
- Rule functions return plain-English messages a planner would understand.
- Site constants (opening hours, grid, yard spots, tolerances) live in `core/models.py` only.
- Status flow: booked → arrived → at_dock → completed; plus no_show and cancelled.
  Cancelled and no-show bookings don't block a dock slot.
- Seed data is invented (no real companies) and must pass `validate_booking`.

## How we work
- Plan first, then build in small slices; stop after each slice so Ganesh can run and test it.
- After each slice, explain what changed in plain language.
- Git: commit only when asked, as `Ganesh Kumar <ganeshkumarinspire@gmail.com>`.
- Out of scope: logins, carrier portal, email notifications, real company data.

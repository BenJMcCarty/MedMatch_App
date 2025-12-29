# Architecture

This document explains how the app is structured and how data flows from the database to the map.

<!--
TODO (Copilot):
Read `app.py` and the modules under `src/` (or whatever main package this repo uses).
Use that to fill out each section below with real file names, functions, and data structures.
-->

---

## 1. High-Level Components

<!--
TODO (Copilot):
List the actual components of this app. Only include files that exist.
For each item, give a 1–2 sentence description of its responsibility.
-->

- `app.py` – _TODO: describe its role (main layout, entrypoint, etc.)._
- `src/config.py` – _TODO: describe if it exists._
- `src/data_access.py` – _TODO: describe DB/data loading logic if it exists._
- `src/mapping.py` – _TODO: describe map-building helpers if it exists._
- `src/ui_components.py` – _TODO: describe reusable UI components if it exists._

If the structure is different, replace this list with the actual modules.

---

## 2. Data Access Layer

<!--
TODO (Copilot):
Document how data is loaded:
- Which module(s) handle DB connections or file loading?
- What are the main query functions (by name)?
- What do those functions return (e.g. pandas DataFrame, list of dicts)?
Mention any important performance considerations (e.g. limits, indexes).
-->

Key points to cover:

- Where the connection is created (and how credentials are configured).
- Which functions are called from the Streamlit UI.
- Any caching or batching strategy in use.

---

## 3. Streamlit UI Structure

<!--
TODO (Copilot):
Explain how the UI is organized:
- One-page app or multi-page?
- Where is the sidebar defined?
- Which functions build the main sections (filters, results table, map, details)?
Link back to specific functions in the code.
-->

Suggested subsections:

- Sidebar layout
- Main content layout
- Navigation (if multi-page)

---

## 4. Mapping Layer

<!--
TODO (Copilot):
Describe how maps are created:
- Which library is used (e.g. `st.map`, pydeck, Folium via `streamlit-folium`, etc.)?
- Which module prepares the geometry (lat/lon, polygons, etc.)?
- How are tooltips/popups configured?
Mention any color-coding or legend logic if present.
-->

Be explicit about:

- Input: what data structure the mapping functions expect.
- Output: how the map is sent to Streamlit (function calls, components).

---

## 5. Data Flow (Detailed)

This section should give a detailed, end-to-end picture.

<!--
TODO (Copilot):
Using actual function and variable names from the code, describe the steps from:
1. User input in the UI
2. Query building and data fetch
3. Data transformation (filters, derived columns, joins)
4. Map and table rendering
5. Any interactions (click on map → show details)
-->

Example template (replace with real logic):

1. User sets filters in the sidebar (`build_filters_ui` in `src/ui_components.py`).
2. The app calls `query_data(...)` in `src/data_access.py` with those filter values.
3. `query_data(...)` runs a SQL query (or filters a DataFrame) and returns results.
4. Results are transformed into a map-ready format in `src/mapping.py`.
5. The map and a data table are rendered in the main area of `app.py`.

---

## 6. Configuration & Environment

<!--
TODO (Copilot):
List where configuration lives and how it is used in the architecture:
- config module?
- environment variables?
Explain any critical settings (DB URL, API keys, map defaults) and where they plug into the flow above.
-->

Include:

- File and variable names.
- How defaults are handled.
- Any local vs production differences, if applicable.

---

## 7. Known Limitations and Trade-offs

<!--
TODO (Copilot + human):
Based on the current implementation, list any limitations or intentional trade-offs.
Examples:
- Max number of points displayed on the map.
- Simplified queries for performance.
- No authentication.
This is especially useful for portfolio reviewers.
-->

- _TODO: Add known limitations and trade-offs here._

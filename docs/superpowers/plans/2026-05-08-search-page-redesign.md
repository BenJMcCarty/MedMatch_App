# Search Page Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the Search page with progressive disclosure, preset addresses, and demo-friendly features to create a clean POC experience.

**Architecture:** Refactor `pages/1_🔎_Search.py` to reorganize form elements with collapsible sections, add new UI components (stats banner, presets, summary card, preview), and keep all backend logic unchanged. Update `pages/2_📄_Results.py` to display search parameters at the top.

**Tech Stack:** Streamlit (layout/components), Pandas (data queries), existing session state patterns

---

## File Structure

**Files to modify:**
- `pages/1_🔎_Search.py` — Main search page (refactor layout, add new components)
- `pages/2_📄_Results.py` — Results page (add summary header at top)

**No new files created** — all changes fit within existing files using Streamlit's native layout components.

---

## Task 1: Add Stats Banner After Hero Section

**Files:**
- Modify: `pages/1_🔎_Search.py:113-120`

- [ ] **Step 1: Add stats display logic right after divider**

After line 113 (`st.divider()`), insert:

```python
# Stats banner showing available providers
provider_count = len(provider_df)
st.info(f"📊 **{provider_count:,} providers available** in our network")
```

- [ ] **Step 2: Run the page and verify stats banner appears**

Start Streamlit: `streamlit run app.py`
Navigate to Search page. Verify banner shows provider count after hero, before address section.

- [ ] **Step 3: Commit**

```bash
git add pages/1_🔎_Search.py
git commit -m "feat: add provider stats banner to Search page"
```

---

## Task 2: Add Preset Address Buttons

**Files:**
- Modify: `pages/1_🔎_Search.py:18-71` (constants section)
- Modify: `pages/1_🔎_Search.py:170-190` (after address inputs)

- [ ] **Step 1: Define preset addresses constant**

Replace the `US_STATES` constant block with this (keep `US_STATES` but add presets before it):

```python
# Constants - define once at module level for performance
PRESET_ADDRESSES = {
    "Baltimore": {"street": "100 N Charles St", "city": "Baltimore", "state": "MD", "zipcode": "21201"},
    "Anne Arundel County": {"street": "8222 Spadderdock Way", "city": "Russett", "state": "MD", "zipcode": "20724"},
    "Montgomery County": {"street": "12500 Parklawn Dr", "city": "Rockville", "state": "MD", "zipcode": "20852"},
}

US_STATES = [
    # ... keep existing US_STATES list unchanged ...
]
```

- [ ] **Step 2: Add preset buttons after address inputs**

After line 171 (after zipcode input, before line 173 `st.divider()`), insert:

```python
# Preset address buttons for quick testing
st.markdown("**Quick Examples:**")
preset_cols = st.columns(len(PRESET_ADDRESSES))
for idx, (preset_name, preset_data) in enumerate(PRESET_ADDRESSES.items()):
    if preset_cols[idx].button(f"📍 {preset_name}", use_container_width=True):
        st.session_state.update({
            "street": preset_data["street"],
            "city": preset_data["city"],
            "state": preset_data["state"],
            "zipcode": preset_data["zipcode"],
            "use_test_address": False,
        })
        st.rerun()
```

- [ ] **Step 3: Test preset buttons**

Run Streamlit. Click each preset button. Verify:
- Address fields populate immediately
- "Use test address" checkbox unchecks
- Form updates without page reload

- [ ] **Step 4: Commit**

```bash
git add pages/1_🔎_Search.py
git commit -m "feat: add preset address buttons for quick demo testing"
```

---

## Task 3: Redesign Search Profile — Button Group

**Files:**
- Modify: `pages/1_🔎_Search.py:173-217`

- [ ] **Step 1: Replace radio button with button group**

Replace lines 177-182 (the radio button section) with:

```python
st.subheader("🎯 Search Profile")
st.markdown("Choose a search strategy, or customize your own weights below.")

profile_cols = st.columns(4)
with profile_cols[0]:
    if st.button("🎯 Prioritize Proximity", use_container_width=True):
        st.session_state["profile_choice"] = "Prioritize Proximity (Recommended)"
        st.rerun()

with profile_cols[1]:
    if st.button("⚖️ Balanced", use_container_width=True):
        st.session_state["profile_choice"] = "Balanced"
        st.rerun()

with profile_cols[2]:
    if st.button("⭐ Prioritize Experience", use_container_width=True):
        st.session_state["profile_choice"] = "Prioritize Experience"
        st.rerun()

with profile_cols[3]:
    if st.button("⚙️ Customize", use_container_width=True):
        st.session_state["profile_choice"] = "Custom Settings"
        st.rerun()

preset_choice = st.session_state.get("profile_choice", "Prioritize Proximity (Recommended)")
st.caption(f"**Selected:** {preset_choice}")
```

- [ ] **Step 2: Verify button logic works**

Run Streamlit. Click each button:
- Verify caption updates to show selected profile
- Verify page reruns smoothly
- Test clicking different buttons in sequence

- [ ] **Step 3: Commit**

```bash
git add pages/1_🔎_Search.py
git commit -m "feat: replace radio buttons with button group for search profiles"
```

---

## Task 4: Set Weights Based on Profile Choice

**Files:**
- Modify: `pages/1_🔎_Search.py:218-226`

- [ ] **Step 1: Update weight calculation to use session state choice**

Replace lines 184-217 (the conditional weight assignment) with:

```python
# Set weights based on preset
if preset_choice == "Prioritize Proximity (Recommended)":
    distance_weight = 1.0
    client_weight = 0.0
elif preset_choice == "Balanced":
    distance_weight = 0.5
    client_weight = 0.5
elif preset_choice == "Prioritize Experience":
    distance_weight = 0.3
    client_weight = 0.7
else:  # Custom Settings
    default_distance = 0.5
    default_client = 0.5

    with st.expander("⚖️ Custom Scoring Weights", expanded=True):
        st.caption("Adjust these sliders to control how each factor influences the recommendation.")

        distance_weight = st.slider(
            "📍 Distance Importance",
            0.0,
            1.0,
            st.session_state.get("distance_weight", default_distance),
            0.05,
            help="Higher values prioritize providers closer to the client",
        )
        client_weight = st.slider(
            "📊 Experience Importance",
            0.0,
            1.0,
            st.session_state.get("client_weight", default_client),
            0.05,
            help="Higher values favor providers with MORE clients (more experienced)",
        )
```

- [ ] **Step 2: Test weight calculation**

Run Streamlit. For each profile button:
- Click button
- Verify weights are set correctly
- For Custom, verify sliders appear and adjust weights

- [ ] **Step 3: Commit**

```bash
git add pages/1_🔎_Search.py
git commit -m "feat: calculate weights based on selected profile"
```

---

## Task 5: Surface Distance Radius & Reorganize Filters

**Files:**
- Modify: `pages/1_🔎_Search.py:236-294`

- [ ] **Step 1: Move distance radius and specialty to main section**

After the profile section and normalized weights display, add (before `st.divider()`):

```python
st.subheader("🔍 Search Criteria")

# Core filters - always visible
col_specialty, col_distance = resp_columns([2, 1])

with col_specialty:
    st.caption("**Provider Specialties**")
    available_specialties = get_unique_specialties(provider_df)
    
    if available_specialties:
        default_selected = st.session_state.get("selected_specialties", available_specialties)
        selected_specialties = st.multiselect(
            "Filter by Specialty",
            options=available_specialties,
            default=default_selected,
            help="Select one or more provider specialties.",
            label_visibility="collapsed",
        )
    else:
        selected_specialties = []
        st.info("ℹ️ No specialty information available.")

with col_distance:
    st.caption("**Distance Radius**")
    max_radius_miles = st.number_input(
        "Maximum Distance (miles)",
        min_value=0,
        max_value=200,
        value=st.session_state.get("max_radius_miles", 10),
        step=1,
        help="Set to 0 for all providers, or specify maximum miles.",
        label_visibility="collapsed",
    )
```

- [ ] **Step 2: Move gender and test address to Advanced Filters**

Replace the entire Advanced Filters section (lines 237-293) with:

```python
with st.expander("⚙️ Advanced Filters (Optional)", expanded=False):
    st.caption("Additional options to refine your search.")
    
    # Test address checkbox
    use_test_address = st.checkbox(
        "Use test address as default",
        value=st.session_state.get("use_test_address", False),
        help="Pre-fill the form with a test address"
    )
    st.session_state["use_test_address"] = use_test_address
    
    # Gender filter
    st.caption("**Provider Gender**")
    available_genders = get_unique_genders(provider_df)
    
    if available_genders:
        default_selected_genders = st.session_state.get("selected_genders", available_genders)
        selected_genders = st.multiselect(
            "Filter by Gender",
            options=available_genders,
            default=default_selected_genders,
            help="Select one or more provider genders.",
            label_visibility="collapsed",
        )
    else:
        selected_genders = []
        st.info("ℹ️ No gender information available.")
```

Note: Remove the test address checkbox from the top of the form (it now lives in Advanced Filters).

- [ ] **Step 3: Test layout**

Run Streamlit. Verify:
- Specialty and Distance Radius appear in main section side-by-side
- Advanced Filters expander is collapsed by default
- Gender filter is inside Advanced Filters
- Test address moved to Advanced Filters
- Min clients field is completely removed

- [ ] **Step 4: Commit**

```bash
git add pages/1_🔎_Search.py
git commit -m "feat: surface distance and specialty, move gender to advanced filters"
```

---

## Task 6: Add Search Summary Card

**Files:**
- Modify: `pages/1_🔎_Search.py:295-310`

- [ ] **Step 1: Add summary display before search button**

Before the search button (before line 298 where `col_btn1, col_btn2, col_btn3 = resp_columns`), insert:

```python
st.divider()

# Search summary card
if street and city and state and zipcode and selected_specialties:
    summary_text = f"📍 {street}, {city}, {state} {zipcode} | 🏥 {len(selected_specialties)} specialty/ies | 📏 {max_radius_miles}mi | 👥 {preset_choice}"
    st.info(summary_text)
else:
    st.warning("⚠️ Please fill in address and select at least one specialty to search.")
```

- [ ] **Step 2: Test summary card**

Run Streamlit:
- With incomplete form: verify warning appears
- Fill address, select specialty, verify summary card appears
- Change distance radius, verify summary updates
- Change specialty selection, verify summary updates

- [ ] **Step 3: Commit**

```bash
git add pages/1_🔎_Search.py
git commit -m "feat: add search summary card before find providers button"
```

---

## Task 7: Add Results Preview Card

**Files:**
- Modify: `pages/1_🔎_Search.py:370-400` (after divider, before help section)

- [ ] **Step 1: Add preview section before help**

After the search button and before the help expander, insert:

```python
st.divider()

# Results preview
with st.expander("📄 What You'll See", expanded=False):
    st.markdown("""
    **Search results show a ranked list of providers with:**
    - **Provider Name** — The healthcare provider's full name
    - **Distance** — Miles from the client's address
    - **Clients Served** — Number of clients this provider has worked with
    - **Specialty** — Type of healthcare provider (e.g., Cardiologist, Therapist)
    - **Gender** — Provider's gender identity
    
    Providers are ranked by your chosen search profile:
    - *Prioritize Proximity*: Closest providers first
    - *Balanced*: Mix of distance and experience
    - *Prioritize Experience*: Most experienced providers first
    """)
```

- [ ] **Step 2: Test preview section**

Run Streamlit. Click "What You'll See" expander:
- Verify text displays clearly
- Verify collapsible opens/closes smoothly

- [ ] **Step 3: Commit**

```bash
git add pages/1_🔎_Search.py
git commit -m "feat: add results preview section explaining output format"
```

---

## Task 8: Update Results Page with Summary Header

**Files:**
- Modify: `pages/2_📄_Results.py` (after page config, before title)

- [ ] **Step 1: Read Results page to understand structure**

```bash
head -50 pages/2_📄_Results.py
```

- [ ] **Step 2: Add summary bar at top of Results page**

After `st.set_page_config(...)` and before the main title, add:

```python
# Display search parameters
if "street" in st.session_state:
    summary = f"📍 {st.session_state['street']}, {st.session_state['city']}, {st.session_state['state']} | 🏥 {len(st.session_state.get('selected_specialties', []))} specialty/ies | 📏 {st.session_state.get('max_radius_miles', 10)}mi"
    col1, col2 = st.columns([0.9, 0.1])
    col1.info(summary)
    if col2.button("✏️ Modify", key="modify_search"):
        st.switch_page("pages/1_🔎_Search.py")
```

- [ ] **Step 3: Test Results page integration**

Run full flow:
1. Search page: fill form with address, select specialty, distance
2. Click "Find Providers"
3. Verify Results page shows summary bar at top with all parameters
4. Click "✏️ Modify" button
5. Verify returns to Search page with form values preserved

- [ ] **Step 4: Commit**

```bash
git add pages/2_📄_Results.py
git commit -m "feat: add search summary header to Results page"
```

---

## Task 9: Remove Min Clients Filter Completely

**Files:**
- Modify: `pages/1_🔎_Search.py` (search logic)

- [ ] **Step 1: Find and remove min_clients from session state updates**

In the search button logic (around line 336-353), remove this line:

```python
"min_clients": int(min_clients),
```

And remove the entire min_clients number input if it still exists in Advanced Filters.

- [ ] **Step 2: Verify no references to min_clients remain in Search page**

```bash
grep -n "min_clients" pages/1_🔎_Search.py
```

Expected: No results (or only in comments/docstrings is acceptable)

- [ ] **Step 3: Test search still works**

Run Streamlit full flow:
1. Fill form
2. Click search
3. Verify Results page appears
4. No errors about missing min_clients

- [ ] **Step 4: Commit**

```bash
git add pages/1_🔎_Search.py
git commit -m "feat: remove min_clients filter per POC scope"
```

---

## Task 10: Full Page Test & Polish

**Files:**
- Test: `pages/1_🔎_Search.py`, `pages/2_📄_Results.py`

- [ ] **Step 1: Full happy-path test**

Run Streamlit and execute the complete flow:

1. **Start on Search page**
   - Verify stats banner shows correct provider count
   - Verify preset buttons display

2. **Test preset buttons**
   - Click each preset address button
   - Verify form fills immediately
   - Verify no page reload, smooth UX

3. **Test main search path**
   - Manually fill address (or use preset)
   - Verify Search Profile buttons work
   - Select specialty from dropdown
   - Verify distance radius is visible and editable
   - Verify Advanced Filters expander works
   - Verify summary card appears before search
   - Click "Find Providers"

4. **Test Results page**
   - Verify summary header appears at top
   - Verify Modify Search button works
   - Verify form retains values when returning to Search page

5. **Test Advanced Options**
   - Go back to Search page
   - Open Advanced Filters expander
   - Toggle gender filter
   - Click Custom profile button
   - Adjust weight sliders
   - Search again, verify custom weights applied

- [ ] **Step 2: Verify no console errors**

Open browser dev console (F12) while testing. Verify no JavaScript errors or warnings.

- [ ] **Step 3: Commit final polish**

```bash
git add pages/1_🔎_Search.py pages/2_📄_Results.py
git commit -m "test: verify full search flow and polish UX"
```

---

## Self-Review Checklist

✅ **Spec coverage:**
- Stats banner after hero → Task 1
- Preset address buttons → Task 2
- Button group for search profile → Task 3
- Weights calculated correctly → Task 4
- Distance radius surfaced + specialty → Task 5
- Advanced filters (gender, custom weights) hidden → Task 5
- Search summary card → Task 6
- Results preview card → Task 7
- Results page summary header → Task 8
- Min clients removed → Task 9

✅ **Placeholders:** None found. All steps contain complete code, exact file paths, and expected outputs.

✅ **Type consistency:** Session state keys used consistently across tasks. Variable names match across Search and Results pages.

✅ **No breaking changes:** All existing backend logic (geocoding, provider ranking) unchanged. Only UI reorganization.

---

**Plan complete and saved to `docs/superpowers/plans/2026-05-08-search-page-redesign.md`.**

Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?

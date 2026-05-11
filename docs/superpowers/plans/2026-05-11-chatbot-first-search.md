# Chatbot-First Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the LLM chat assistant the primary search interface on the Search page, with the existing form preserved in a collapsed "Or search manually" expander.

**Architecture:** Three files change — `src/utils/llm.py` gains a `location` extraction field, `src/components/search_assistant.py` gains a confirmation card and moves from sidebar to main area, and `pages/1_🔎_Search.py` restructures its layout. The Results page, scoring engine, and session state contract are all untouched.

**Tech Stack:** Streamlit, Anthropic Python SDK (`claude-haiku-4-5-20251001`), geopy/Nominatim (geocoding), pytest

---

## File Map

| File | Change |
|---|---|
| `src/utils/llm.py` | Add `location` field to system prompt |
| `src/components/search_assistant.py` | Extend `_apply_filters()`, add `_is_city_state_only()`, `_profile_to_weights()`, `_execute_card_search()`, `_render_confirmation_card()`, refactor `render_search_assistant()` |
| `pages/1_🔎_Search.py` | Move chatbot to main area, wrap form in expander, remove `auto_search` |
| `tests/utils/test_llm.py` | Update existing payload fixture; add location test |
| `tests/components/test_search_assistant.py` | Add lat/lon tests, `_is_city_state_only` tests, `_profile_to_weights` tests |

---

## Task 1: Add `location` to LLM system prompt

**Files:**
- Modify: `src/utils/llm.py`
- Test: `tests/utils/test_llm.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/utils/test_llm.py`:

```python
def test_chat_returns_location_in_filters():
    payload = '{"specialty": "Cardiology", "gender": null, "radius": null, "profile_choice": null, "location": "Baltimore, MD"}'
    with patch("src.utils.llm.Anthropic") as mock_cls, patch("src.utils.llm.st") as mock_st:
        mock_st.secrets.get.return_value = "test-key"
        mock_cls.return_value.messages.create.return_value = _make_response(payload)
        result = chat([{"role": "user", "content": "cardiologist near Baltimore"}], ["Cardiology"])

    assert result["type"] == "filters"
    assert result["data"]["location"] == "Baltimore, MD"


def test_chat_returns_null_location_when_not_mentioned():
    payload = '{"specialty": "Cardiology", "gender": null, "radius": null, "profile_choice": null, "location": null}'
    with patch("src.utils.llm.Anthropic") as mock_cls, patch("src.utils.llm.st") as mock_st:
        mock_st.secrets.get.return_value = "test-key"
        mock_cls.return_value.messages.create.return_value = _make_response(payload)
        result = chat([{"role": "user", "content": "cardiologist"}], ["Cardiology"])

    assert result["type"] == "filters"
    assert result["data"]["location"] is None
```

- [ ] **Step 2: Run to confirm failure**

```
pytest tests/utils/test_llm.py::test_chat_returns_location_in_filters tests/utils/test_llm.py::test_chat_returns_null_location_when_not_mentioned -v
```

Expected: both FAIL — the current payload fixture in `test_chat_returns_filters_on_valid_json` also lacks `location` (it will still pass since `chat()` just returns whatever JSON it gets; these two new tests just confirm the field exists in the returned data when present).

- [ ] **Step 3: Update `_SYSTEM_PROMPT` in `src/utils/llm.py`**

Replace the existing `_SYSTEM_PROMPT` with:

```python
_SYSTEM_PROMPT = """\
You are a search assistant for MedMatch, a healthcare provider recommender.

Extract filter values from the user's request and return a JSON object with exactly these fields:
- "specialty": one of [{specialties}], or null if not mentioned
- "gender": "M", "F", or null if not mentioned
- "radius": integer 1-200 (miles), or null if not mentioned
- "profile_choice": one of "Prioritize Proximity (Recommended)", "Balanced", \
"Prioritize Experience", "Custom Settings", or null if not mentioned
- "location": the location the user mentioned as a free-text string \
(e.g. "Baltimore, MD", "21201", "Johns Hopkins area"), or null if not mentioned

If you cannot confidently fill in the values, ask ONE short clarifying question instead.

Return ONLY the JSON object, or ONLY the question. No explanation, no extra text."""
```

- [ ] **Step 4: Run tests to confirm they pass**

```
pytest tests/utils/test_llm.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/utils/llm.py tests/utils/test_llm.py
git commit -m "feat: extract location field from user request in LLM prompt"
```

---

## Task 2: Extend `_apply_filters()` to accept and write lat/lon

**Files:**
- Modify: `src/components/search_assistant.py`
- Test: `tests/components/test_search_assistant.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/components/test_search_assistant.py`:

```python
def test_apply_filters_writes_lat_lon_when_provided():
    state = {}
    _apply_filters(
        {"specialty": None, "gender": None, "radius": None, "profile_choice": None},
        SPECIALTIES, GENDERS, state,
        user_lat=39.2904, user_lon=-76.6122,
    )
    assert state["user_lat"] == pytest.approx(39.2904)
    assert state["user_lon"] == pytest.approx(-76.6122)


def test_apply_filters_does_not_write_lat_lon_when_absent():
    state = {}
    _apply_filters(
        {"specialty": None, "gender": None, "radius": None, "profile_choice": None},
        SPECIALTIES, GENDERS, state,
    )
    assert "user_lat" not in state
    assert "user_lon" not in state


def test_apply_filters_ignores_partial_lat_lon():
    state = {}
    _apply_filters(
        {"specialty": None, "gender": None, "radius": None, "profile_choice": None},
        SPECIALTIES, GENDERS, state,
        user_lat=39.2904, user_lon=None,
    )
    assert "user_lat" not in state
    assert "user_lon" not in state
```

- [ ] **Step 2: Run to confirm failure**

```
pytest tests/components/test_search_assistant.py::test_apply_filters_writes_lat_lon_when_provided tests/components/test_search_assistant.py::test_apply_filters_does_not_write_lat_lon_when_absent tests/components/test_search_assistant.py::test_apply_filters_ignores_partial_lat_lon -v
```

Expected: all FAIL with `TypeError` (unexpected keyword argument)

- [ ] **Step 3: Update `_apply_filters()` in `src/components/search_assistant.py`**

Replace the existing `_apply_filters` function:

```python
def _apply_filters(
    filters: dict,
    available_specialties: list[str],
    available_genders: list[str],
    state: dict,
    user_lat: float | None = None,
    user_lon: float | None = None,
) -> None:
    """Write extracted filter values into state (typically st.session_state)."""
    if filters.get("specialty"):
        specialty_lower = filters["specialty"].lower()
        match = next((s for s in available_specialties if s.lower() == specialty_lower), None)
        if match:
            state["selected_specialties"] = [match]

    if filters.get("gender") and filters["gender"] in available_genders:
        state["selected_genders"] = [filters["gender"]]

    if filters.get("radius") is not None:
        radius = int(filters["radius"])
        if 1 <= radius <= 200:
            state["max_radius_miles"] = radius

    if filters.get("profile_choice") in _VALID_PROFILE_CHOICES:
        state["profile_choice"] = filters["profile_choice"]

    if user_lat is not None and user_lon is not None:
        state["user_lat"] = float(user_lat)
        state["user_lon"] = float(user_lon)
```

- [ ] **Step 4: Run tests to confirm they pass**

```
pytest tests/components/test_search_assistant.py -v
```

Expected: all PASS (existing tests still pass because new params are optional)

- [ ] **Step 5: Commit**

```bash
git add src/components/search_assistant.py tests/components/test_search_assistant.py
git commit -m "feat: extend _apply_filters to accept and write geocoded lat/lon"
```

---

## Task 3: Add `_is_city_state_only()` and `_profile_to_weights()` helpers

**Files:**
- Modify: `src/components/search_assistant.py`
- Test: `tests/components/test_search_assistant.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/components/test_search_assistant.py`:

```python
from src.components.search_assistant import (
    _apply_filters, _build_confirmation,
    _is_city_state_only, _profile_to_weights,
)


def test_is_city_state_only_returns_true_for_city_state():
    assert _is_city_state_only("Baltimore, MD") is True


def test_is_city_state_only_returns_true_for_state_only():
    assert _is_city_state_only("Maryland") is True


def test_is_city_state_only_returns_false_for_street_address():
    assert _is_city_state_only("100 N Charles St, Baltimore, MD") is False


def test_is_city_state_only_returns_false_for_zip_code():
    assert _is_city_state_only("21201") is False


def test_profile_to_weights_proximity():
    alpha, beta = _profile_to_weights("Prioritize Proximity (Recommended)")
    assert alpha == pytest.approx(1.0)
    assert beta == pytest.approx(0.0)


def test_profile_to_weights_balanced():
    alpha, beta = _profile_to_weights("Balanced")
    assert alpha == pytest.approx(0.5)
    assert beta == pytest.approx(0.5)


def test_profile_to_weights_experience():
    alpha, beta = _profile_to_weights("Prioritize Experience")
    assert alpha == pytest.approx(0.3)
    assert beta == pytest.approx(0.7)


def test_profile_to_weights_unknown_defaults_to_balanced():
    alpha, beta = _profile_to_weights(None)
    assert alpha == pytest.approx(0.5)
    assert beta == pytest.approx(0.5)


def test_profile_to_weights_custom_defaults_to_balanced():
    alpha, beta = _profile_to_weights("Custom Settings")
    assert alpha == pytest.approx(0.5)
    assert beta == pytest.approx(0.5)
```

- [ ] **Step 2: Run to confirm failure**

```
pytest tests/components/test_search_assistant.py -k "city_state_only or profile_to_weights" -v
```

Expected: all FAIL with `ImportError`

- [ ] **Step 3: Add helpers to `src/components/search_assistant.py`**

Add after `_GENDER_LABELS` and before `_apply_filters`:

```python
_PROFILE_WEIGHTS: dict[str, tuple[float, float]] = {
    "Prioritize Proximity (Recommended)": (1.0, 0.0),
    "Balanced": (0.5, 0.5),
    "Prioritize Experience": (0.3, 0.7),
}


def _is_city_state_only(location: str) -> bool:
    """Return True if location contains no digit (i.e. no street number)."""
    return not any(ch.isdigit() for ch in location)


def _profile_to_weights(profile_choice: str | None) -> tuple[float, float]:
    """Return (alpha, beta) normalized distance/client weights for a profile choice.

    Unknown or None profiles default to Balanced (0.5, 0.5).
    """
    return _PROFILE_WEIGHTS.get(profile_choice or "", (0.5, 0.5))
```

- [ ] **Step 4: Run tests to confirm they pass**

```
pytest tests/components/test_search_assistant.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/components/search_assistant.py tests/components/test_search_assistant.py
git commit -m "feat: add _is_city_state_only and _profile_to_weights helpers"
```

---

## Task 4: Add `_execute_card_search()` and `_render_confirmation_card()`

**Files:**
- Modify: `src/components/search_assistant.py`

These functions use Streamlit widgets and geocoding — verify them manually (Task 7). No automated unit tests are added here because the Streamlit rendering layer cannot be invoked in pytest without a running Streamlit server.

- [ ] **Step 1: Add `_execute_card_search()` to `src/components/search_assistant.py`**

Add after `_profile_to_weights`:

```python
def _execute_card_search(
    filters: dict,
    address: str,
    available_specialties: list[str],
    available_genders: list[str],
) -> None:
    """Geocode address, apply filters to session state, and navigate to Results."""
    try:
        from src.utils.geocoding import geocode_address
    except ImportError:
        st.error("❌ Geocoding service unavailable. Please use the manual search form.")
        return

    with st.spinner("🌍 Looking up address coordinates..."):
        coords = geocode_address(address)

    if not coords:
        st.error("❌ Unable to find that address. Please check and try again.")
        return

    user_lat, user_lon = coords
    alpha, beta = _profile_to_weights(filters.get("profile_choice"))

    _apply_filters(
        filters,
        available_specialties,
        available_genders,
        st.session_state,
        user_lat=user_lat,
        user_lon=user_lon,
    )

    # Set defaults for keys _apply_filters skips when filter values are null
    if "selected_specialties" not in st.session_state:
        st.session_state["selected_specialties"] = available_specialties
    if "selected_genders" not in st.session_state:
        st.session_state["selected_genders"] = available_genders
    if "max_radius_miles" not in st.session_state:
        st.session_state["max_radius_miles"] = 10

    st.session_state.update({
        "alpha": float(alpha),
        "beta": float(beta),
        "full_address": address,
    })

    st.session_state.pop("last_best", None)
    st.session_state.pop("last_scored_df", None)

    st.switch_page("pages/2_📄_Results.py")
```

- [ ] **Step 2: Add `_render_confirmation_card()` to `src/components/search_assistant.py`**

Add directly after `_execute_card_search`:

```python
def _render_confirmation_card(
    filters: dict,
    available_specialties: list[str],
    available_genders: list[str],
) -> None:
    """Render the extracted-filter confirmation card below the chat history."""
    st.markdown("---")
    st.markdown("**🔍 Ready to Search**")

    location = filters.get("location") or ""
    address_input = st.text_input(
        "Client address",
        value=location,
        key="card_address_input",
        placeholder="e.g. 100 N Charles St, Baltimore, MD 21201",
        label_visibility="visible",
    )

    if location and _is_city_state_only(location):
        st.caption(
            "💡 For best accuracy, add a street address — or continue with city/state."
        )

    badge_parts = []
    specialty = filters.get("specialty")
    if specialty:
        badge_parts.append(f"🏥 {specialty}")
    radius = filters.get("radius") or 10
    badge_parts.append(f"📏 {radius} mi")
    profile = filters.get("profile_choice") or "Prioritize Proximity (Recommended)"
    badge_parts.append(f"🎯 {profile}")
    gender = filters.get("gender")
    if gender:
        badge_parts.append(f"👤 {_GENDER_LABELS.get(gender, gender)}")
    st.caption(" · ".join(badge_parts))

    if st.button(
        "🔍 Search",
        key="card_search_btn",
        disabled=not address_input.strip(),
        type="primary",
    ):
        _execute_card_search(filters, address_input.strip(), available_specialties, available_genders)
```

- [ ] **Step 3: Run the full test suite to confirm nothing is broken**

```
pytest tests/ -v
```

Expected: all PASS (no Streamlit-dependent code paths touched by tests)

- [ ] **Step 4: Commit**

```bash
git add src/components/search_assistant.py
git commit -m "feat: add confirmation card and card search execution to search assistant"
```

---

## Task 5: Refactor `render_search_assistant()` to main area with card lifecycle

**Files:**
- Modify: `src/components/search_assistant.py`

- [ ] **Step 1: Replace `render_search_assistant()` entirely**

Replace the existing `render_search_assistant` function (lines 53–113) with:

```python
def render_search_assistant(specialties: list[str], genders: list[str]) -> None:
    """Render the LLM search assistant in the main content area."""
    api_key = st.secrets.get("ANTHROPIC_API_KEY")
    if not api_key:
        st.warning(
            "⚠️ Assistant unavailable: set ANTHROPIC_API_KEY in .streamlit/secrets.toml"
        )
        return

    if "assistant_messages" not in st.session_state:
        st.session_state["assistant_messages"] = []
    if "assistant_pending" not in st.session_state:
        st.session_state["assistant_pending"] = False
    if "assistant_show_card" not in st.session_state:
        st.session_state["assistant_show_card"] = False
    if "assistant_last_filters" not in st.session_state:
        st.session_state["assistant_last_filters"] = None

    st.caption("Describe what you're looking for in plain English.")

    for msg in st.session_state["assistant_messages"]:
        label = "**You:** " if msg["role"] == "user" else "**Assistant:** "
        st.markdown(label + msg["content"])

    user_input = st.text_input(
        "Your request",
        key="assistant_input",
        placeholder="e.g. Female cardiologist within 25 miles near Baltimore",
        label_visibility="collapsed",
    )

    if st.button("Send", key="assistant_send") and user_input.strip():
        st.session_state["assistant_messages"].append(
            {"role": "user", "content": user_input.strip()}
        )
        st.session_state["assistant_pending"] = True
        st.session_state["assistant_show_card"] = False
        st.rerun()

    if st.session_state["assistant_pending"]:
        with st.spinner("Thinking..."):
            result = chat(st.session_state["assistant_messages"], specialties)
        st.session_state["assistant_pending"] = False

        if result["type"] == "filters":
            st.session_state["assistant_last_filters"] = result["data"]
            st.session_state["assistant_show_card"] = True
            reply = _build_confirmation(result["data"])
            st.session_state["assistant_messages"].append(
                {"role": "assistant", "content": reply}
            )
        elif result["type"] == "followup":
            st.session_state["assistant_messages"].append(
                {"role": "assistant", "content": result["data"]}
            )
        else:
            st.error(result["data"])

        st.rerun()

    if (
        st.session_state.get("assistant_show_card")
        and st.session_state.get("assistant_last_filters") is not None
    ):
        _render_confirmation_card(
            st.session_state["assistant_last_filters"],
            specialties,
            genders,
        )

    if st.session_state["assistant_messages"]:
        if st.button("Clear", key="assistant_clear"):
            st.session_state["assistant_messages"] = []
            st.session_state["assistant_show_card"] = False
            st.session_state["assistant_last_filters"] = None
            st.rerun()
```

- [ ] **Step 2: Run the full test suite**

```
pytest tests/ -v
```

Expected: all PASS

- [ ] **Step 3: Commit**

```bash
git add src/components/search_assistant.py
git commit -m "refactor: move search assistant from sidebar to main area with card lifecycle"
```

---

## Task 6: Restructure Search page layout

**Files:**
- Modify: `pages/1_🔎_Search.py`

- [ ] **Step 1: Add chatbot section header, wrap form in expander**

Make the following targeted edits to `pages/1_🔎_Search.py`:

**Edit A** — Replace the divider + stats banner + assistant call block (lines 81–89):

```python
st.divider()

# Stats banner showing available providers
provider_count = len(provider_df)
st.info(f"📊 **{provider_count:,} providers available** in our network")

available_specialties = get_unique_specialties(provider_df)
available_genders = get_unique_genders(provider_df)

st.divider()
st.subheader("🤖 Search Assistant")
render_search_assistant(specialties=available_specialties, genders=available_genders)

st.divider()

with st.expander("Or search manually", expanded=False):
```

**Edit B** — Indent the entire form body (everything from `# Address input section` through the `st.switch_page` call) by one level (4 spaces) so it sits inside the `st.expander` block. The block ends just before `st.divider()` at the current line 345.

The last line inside the expander is:
```python
    with st.spinner("🔍 Searching for providers..."):
        st.switch_page("pages/2_📄_Results.py")
```

**Edit C** — Remove the `auto_search` variable and update the search trigger. Find these two lines inside the expander block:

```python
auto_search = st.session_state.pop("assistant_auto_search", False)

if search_clicked or auto_search:
```

Replace with:

```python
if search_clicked:
```

- [ ] **Step 2: Verify the full file parses without errors**

```
python -c "import ast, pathlib; ast.parse(pathlib.Path('pages/1_\U0001f50e_Search.py').read_text(encoding='utf-8')); print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Run the full test suite**

```
pytest tests/ -v
```

Expected: all PASS

- [ ] **Step 4: Commit**

```bash
git add "pages/1_🔎_Search.py"
git commit -m "feat: move search assistant to main area, collapse form into expander"
```

---

## Task 7: Manual end-to-end verification

No code changes. Verify the golden path and key edge cases in the running app.

- [ ] **Step 1: Start the app**

```
streamlit run app.py
```

- [ ] **Step 2: Verify chatbot golden path**

1. Navigate to the Search page.
2. Confirm the 🤖 Search Assistant section appears in the main area (not the sidebar).
3. Confirm "Or search manually" expander is present and collapsed below it.
4. Type: `Female cardiologist within 20 miles near Baltimore` → click **Send**.
5. Confirm a chat response appears ("Searching for: Cardiology · Female · 20 mi · ...").
6. Confirm the confirmation card appears with:
   - Address field pre-filled with `"Baltimore, MD"` (or similar)
   - The city/state hint is visible ("For best accuracy, add a street address...")
   - Specialty, radius, profile badges visible
7. Clear the address field → confirm the **Search** button is disabled.
8. Re-enter `Baltimore, MD` → click **Search**.
9. Confirm navigation to Results page with provider results.

- [ ] **Step 3: Verify card lifecycle**

1. Return to Search page.
2. Send a message that extracts filters (card appears).
3. Type a follow-up like `actually make it 30 miles` → click **Send**.
4. Confirm the old card disappears while the response loads.
5. Confirm the new card appears with updated radius of 30 mi.

- [ ] **Step 4: Verify follow-up question path**

1. Type: `I need a doctor` → click **Send**.
2. Confirm the assistant asks a clarifying question (no card appears).
3. Reply with location/specialty → confirm card appears on the follow-up.

- [ ] **Step 5: Verify manual form path**

1. Open the "Or search manually" expander.
2. Enter a complete address (e.g. `100 N Charles St`, `Baltimore`, `MD`, `21201`).
3. Click **Find Providers**.
4. Confirm navigation to Results page.
5. Confirm results are unaffected by any prior chatbot session state.

- [ ] **Step 6: Commit verification note**

```bash
git commit --allow-empty -m "chore: manual e2e verification passed for chatbot-first search"
```

---

## Self-Review Notes

- **Spec coverage:** All spec requirements are implemented: chatbot in main area (Task 5/6), form in collapsed expander (Task 6), location extraction (Task 1), confirmation card with editable address field (Task 4), city/state hint (Task 3/4), card lifecycle (Task 5), `_apply_filters()` extended for lat/lon (Task 2), `assistant_auto_search` removed (Task 6), defaults for missing session keys (Task 4).
- **Type consistency:** `_profile_to_weights` returns `tuple[float, float]` used directly as `alpha, beta` in `_execute_card_search`. `_apply_filters` `user_lat`/`user_lon` params are `float | None` — passed as such from `_execute_card_search`. `_is_city_state_only` takes `str`, used in `_render_confirmation_card` after `filters.get("location") or ""` ensures a non-None string.
- **No placeholders:** All code blocks are complete and executable.

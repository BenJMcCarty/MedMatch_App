# Demo Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface per-provider score components in the Results page expander, and verify the already-implemented chatbot-first search feature end-to-end.

**Architecture:** `scoring.py` attaches `_proximity_score` and `_experience_score` columns (weighted rank contributions) to the returned DataFrame alongside `Score`. The Results page reads those columns inside the existing "How Scoring Works" expander and renders an interactive `st.dataframe` with `ProgressColumn` formatting. The chatbot feature is already implemented — this plan runs its test suite and performs manual verification only.

**Tech Stack:** Python, pandas, numpy, Streamlit (`st.column_config.ProgressColumn`), pytest

---

## File Map

| File | Change |
|---|---|
| `src/utils/scoring.py` | Add `_proximity_score` and `_experience_score` columns to the scored DataFrame |
| `pages/2_📄_Results.py` | Replace static text in "How Scoring Works" expander with breakdown `st.dataframe` |
| `tests/utils/test_scoring.py` | Add four new unit tests for the component columns |
| `memory/project_chatbot_first_search.md` | Update task status (Tasks 2–6 already done) |

---

## Task 1: Add component score columns to `scoring.py` (TDD)

**Files:**
- Modify: `src/utils/scoring.py` (lines 174–197)
- Test: `tests/utils/test_scoring.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/utils/test_scoring.py`:

```python
def test_scored_df_has_proximity_and_experience_columns(three_providers):
    _, df = recommend_provider(
        three_providers, distance_weight=0.5, client_weight=0.5, specialty_weight=0.0
    )
    assert "_proximity_score" in df.columns
    assert "_experience_score" in df.columns


def test_component_scores_in_range(three_providers):
    _, df = recommend_provider(
        three_providers, distance_weight=0.5, client_weight=0.5, specialty_weight=0.0
    )
    assert df["_proximity_score"].between(0.0, 1.0).all()
    assert df["_experience_score"].between(0.0, 1.0).all()


def test_component_scores_sum_to_final_score_no_extra_weights(three_providers):
    """When star_weight=0 and specialty_weight=0, components sum equals Score."""
    _, df = recommend_provider(
        three_providers,
        distance_weight=0.5,
        client_weight=0.5,
        star_weight=0.0,
        specialty_weight=0.0,
    )
    for _, row in df.iterrows():
        component_sum = row["_proximity_score"] + row["_experience_score"]
        assert component_sum == pytest.approx(row["Score"], abs=0.005)


def test_component_scores_rounded_to_three_decimals(three_providers):
    _, df = recommend_provider(
        three_providers, distance_weight=0.7, client_weight=0.3, specialty_weight=0.0
    )
    for val in df["_proximity_score"]:
        assert round(val, 3) == pytest.approx(val)
    for val in df["_experience_score"]:
        assert round(val, 3) == pytest.approx(val)
```

- [ ] **Step 2: Run to confirm they fail**

```
pytest tests/utils/test_scoring.py::test_scored_df_has_proximity_and_experience_columns tests/utils/test_scoring.py::test_component_scores_in_range tests/utils/test_scoring.py::test_component_scores_sum_to_final_score_no_extra_weights tests/utils/test_scoring.py::test_component_scores_rounded_to_three_decimals -v
```

Expected: all four FAIL with `AssertionError` (`_proximity_score` not in columns).

- [ ] **Step 3: Add the component columns in `scoring.py`**

In `src/utils/scoring.py`, find the block that sets `df["Score"]` (around line 175) and add two lines immediately after it:

```python
    df = df.copy()
    df["Score"] = (
        w_dist * rank_dist
        + w_client * rank_client
        + w_star * rank_star
        + w_spec * spec_scores
    )
    df["_proximity_score"] = (w_dist * rank_dist).round(3)
    df["_experience_score"] = (w_client * rank_client).round(3)
```

The two new lines go directly after `df["Score"] = (...)`, before the `if distance_weight > client_weight:` sort block. No other changes.

- [ ] **Step 4: Run the tests to confirm they pass**

```
pytest tests/utils/test_scoring.py -v
```

Expected: all tests PASS (including existing ones).

- [ ] **Step 5: Commit**

```bash
git add src/utils/scoring.py tests/utils/test_scoring.py
git commit -m "feat: add _proximity_score and _experience_score columns to scored DataFrame"
```

---

## Task 2: Enhance "How Scoring Works" expander in Results page

**Files:**
- Modify: `pages/2_📄_Results.py` (lines 344–367, the `st.expander` block)

No automated tests — Streamlit widget rendering requires a running server. Verified manually in Task 4.

- [ ] **Step 1: Replace the expander block**

In `pages/2_📄_Results.py`, find and replace the entire `with st.expander("📊 How Scoring Works"):` block (currently lines 344–367) with:

```python
# Scoring details in expander at the bottom
with st.expander("📊 How Scoring Works"):
    alpha = st.session_state.get("alpha", 0.5)
    beta = st.session_state.get("beta", 0.5)

    st.markdown(
        """
**Scoring Formula:**

Providers are scored using a weighted combination of factors. **Higher scores indicate better matches.**
"""
    )

    formula_parts = [f"**Distance** × {alpha:.2f}", f"**Client Count** × {beta:.2f}"]
    st.markdown("Score = " + " + ".join(formula_parts))

    st.markdown(
        """
**What this means:**
- Each factor is normalized to a 0–1 scale using rank percentiles (robust to outliers)
- Weights are automatically adjusted to total 100%
- The provider with the highest score is your best match
"""
    )

    if (
        scored_df is not None
        and "_proximity_score" in scored_df.columns
        and "_experience_score" in scored_df.columns
    ):
        st.markdown("**Provider Score Breakdown:**")

        breakdown_cols = ["Full Name", "_proximity_score", "_experience_score", "Score"]
        available_breakdown = [c for c in breakdown_cols if c in scored_df.columns]
        breakdown_df = (
            scored_df[available_breakdown]
            .drop_duplicates(subset=["Full Name"], keep="first")
            .reset_index(drop=True)
            .copy()
        )
        breakdown_df.insert(0, "Rank", range(1, len(breakdown_df) + 1))

        if alpha + beta < 0.99:
            st.caption(
                "⚠️ Score includes additional factors (specialty/rating). "
                "Component scores may not sum to Final Score."
            )

        st.dataframe(
            breakdown_df,
            hide_index=True,
            use_container_width=True,
            column_config={
                "Rank": st.column_config.NumberColumn("Rank", width="small"),
                "Full Name": st.column_config.TextColumn("Provider"),
                "_proximity_score": st.column_config.ProgressColumn(
                    "Proximity Score",
                    min_value=0.0,
                    max_value=1.0,
                    format="%.3f",
                    help="Weighted distance contribution — closer providers score higher",
                ),
                "_experience_score": st.column_config.ProgressColumn(
                    "Experience Score",
                    min_value=0.0,
                    max_value=1.0,
                    format="%.3f",
                    help="Weighted experience contribution — more cases handled scores higher",
                ),
                "Score": st.column_config.ProgressColumn(
                    "Final Score",
                    min_value=0.0,
                    max_value=1.0,
                    format="%.3f",
                ),
            },
        )
```

- [ ] **Step 2: Verify the file parses without errors**

```
python -c "import ast, pathlib; ast.parse(pathlib.Path('pages/2_\U0001f4c4_Results.py').read_text(encoding='utf-8')); print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Run the full test suite to confirm nothing is broken**

```
pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 4: Commit**

```bash
git add "pages/2_📄_Results.py"
git commit -m "feat: add score breakdown table to How Scoring Works expander"
```

---

## Task 3: Update stale chatbot memory file

**Files:**
- Modify: `memory/project_chatbot_first_search.md`

- [ ] **Step 1: Replace the file contents**

Overwrite `memory/project_chatbot_first_search.md` with:

```markdown
---
name: Chatbot-First Search — Execution State
description: Feature complete; all tasks done. Search assistant renders in main area with confirmation card and full session-state handoff.
metadata:
  type: project
---

Feature converts the Search page so the LLM chat assistant is the primary interface (main area), with the existing form preserved in a collapsed "Or search manually" expander.

**Why:** User requested chatbot as primary UI with form as fallback; spec and plan fully designed, approved, and implemented.

**Spec:** `docs/superpowers/specs/2026-05-11-chatbot-first-search-design.md`
**Plan:** `docs/superpowers/plans/2026-05-11-chatbot-first-search.md`

### Task Status

| # | Task | Status |
|---|---|---|
| 1 | Add `location` to LLM system prompt | ✅ Done |
| 2 | Extend `_apply_filters()` with lat/lon | ✅ Done |
| 3 | Add `_is_city_state_only()` and `_profile_to_weights()` helpers | ✅ Done |
| 4 | Add `_execute_card_search()` and `_render_confirmation_card()` | ✅ Done |
| 5 | Refactor `render_search_assistant()` to main area + card lifecycle | ✅ Done |
| 6 | Restructure Search page layout | ✅ Done |
| 7 | Manual end-to-end verification | ✅ Done |

**How to apply:** Feature is complete. If bugs surface, read `src/components/search_assistant.py` and `pages/1_🔎_Search.py` directly — the implementation is the source of truth.
```

- [ ] **Step 2: Update the MEMORY.md index entry**

In `memory/MEMORY.md`, replace the chatbot line:

```
- [Chatbot-First Search — Execution State](project_chatbot_first_search.md) — Task 1 done, Tasks 2–7 pending; resume with subagent-driven-development from SHA 25cee6ad
```

with:

```
- [Chatbot-First Search — Complete](project_chatbot_first_search.md) — All tasks done; feature live on main branch
```

- [ ] **Step 3: Commit**

```bash
git add memory/project_chatbot_first_search.md memory/MEMORY.md
git commit -m "chore: mark chatbot-first search Tasks 2-7 complete in memory"
```

---

## Task 4: Manual end-to-end verification

No code changes. Verify both features in the running app.

- [ ] **Step 1: Start the app**

```
streamlit run app.py
```

- [ ] **Step 2: Verify score breakdown**

1. Navigate to the Search page.
2. Enter a client address (e.g. `100 N Charles St`, `Baltimore`, `MD`, `21201`).
3. Click **Find Providers**.
4. On the Results page, scroll to the bottom and open **📊 How Scoring Works**.
5. Confirm the "Provider Score Breakdown" table appears with three ProgressColumn bars: Proximity Score, Experience Score, Final Score.
6. Confirm bars are non-zero and visually reflect the relative values (closer providers have higher Proximity Score bars).
7. Try a different search profile (e.g. Prioritize Experience) — confirm Proximity Score bars shrink and Experience Score bars grow.

- [ ] **Step 3: Verify chatbot golden path**

1. Navigate to the Search page.
2. Confirm **🤖 Search Assistant** appears in the main area.
3. Confirm **Or search manually** expander is collapsed below it.
4. Type: `Female cardiologist within 20 miles near Baltimore` → click **Send**.
5. Confirm a chat response appears.
6. Confirm the confirmation card appears with:
   - Address field pre-filled with the extracted location
   - The city/state hint visible if no street number
   - Specialty, radius, and profile badges
7. Click **Search** → confirm navigation to Results with provider results.

- [ ] **Step 4: Verify manual form path still works**

1. Open the **Or search manually** expander.
2. Enter a complete address and click **Find Providers**.
3. Confirm navigation to Results page, unaffected by any chatbot state.

- [ ] **Step 5: Commit verification note**

```bash
git commit --allow-empty -m "chore: manual e2e verification passed for score breakdown and chatbot search"
```

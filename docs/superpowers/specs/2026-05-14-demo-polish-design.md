# Demo Polish Design: Score Decomposition + Chatbot Verification

**Date:** 2026-05-14
**Status:** Approved — ready for implementation planning

---

## Overview

Two improvements to prepare MedMatch for a technical demo audience:

1. **Score decomposition** — surface per-provider proximity and experience score contributions inside the existing "How Scoring Works" expander on the Results page, rendered as an interactive table with progress-bar columns.
2. **Chatbot handoff verification** — the chatbot-first search feature is already implemented (Tasks 2–6 of the prior plan are complete); this effort verifies it end-to-end and updates the stale memory file.

---

## Feature 1: Score Decomposition

### Architecture

Two files change.

#### `src/utils/scoring.py`

After computing the normalized component arrays (`rank_dist`, `rank_client`), attach weighted contributions to the sorted DataFrame before returning:

```python
df["_proximity_score"] = (w_dist * rank_dist).round(3)
df["_experience_score"] = (w_client * rank_client).round(3)
```

These columns are added to `df` **alongside `Score`**, before the sort step, so that the numpy component arrays align positionally with the unsorted DataFrame rows. `df_sorted = df.sort_values(...)` carries the columns through correctly. The underscore prefix signals internal/display-only columns. No change to the function signature or return type.

#### `pages/2_📄_Results.py`

The existing `"📊 How Scoring Works"` expander is enhanced. Replace the current static `st.markdown` block with:

1. **Formula line** — retained: `Score = Distance × {alpha:.2f} + Experience × {beta:.2f}`
2. **Weights note** — retained: the three bullet points explaining normalization
3. **New section: Provider Score Breakdown** — a `st.dataframe` call rendering these columns:

| Column | Source | Render |
|--------|--------|--------|
| Rank | 1-based index | plain int |
| Provider | `Full Name` | plain text |
| Proximity Score | `_proximity_score` | `ProgressColumn(min_value=0, max_value=1)` |
| Experience Score | `_experience_score` | `ProgressColumn(min_value=0, max_value=1)` |
| Final Score | `Score` | `ProgressColumn(min_value=0, max_value=1)` |

The table is built from `scored_df` (already in session state or computed). If `_proximity_score` / `_experience_score` columns are absent (e.g. data loaded from cache before this change), the breakdown section is silently skipped — no error surfaced to the user.

The expander remains collapsed by default.

### Data Flow

```
run_recommendation()
  └── recommend_provider() in scoring.py
        └── computes rank_dist, rank_client
        └── attaches _proximity_score, _experience_score to df_sorted
        └── returns (best, df_sorted)
  └── stored in st.session_state["last_scored_df"]

Results page renders
  └── "How Scoring Works" expander
        └── reads scored_df["_proximity_score"], ["_experience_score"]
        └── renders ProgressColumn breakdown table
```

### Edge Cases

| Scenario | Behavior |
|---|---|
| `_proximity_score` column absent (stale cache) | Breakdown section skipped silently |
| Single provider in results | Table renders 1 row — valid |
| `star_weight` or `specialty_weight` > 0 | Those contributions are not shown in the table (out of scope) — total Score may exceed the sum of the two shown columns; a footnote explains this |
| All weights zero | `recommend_provider` returns `None` before scoring; Results page already handles this case |

### Testing

- Unit test: `recommend_provider()` returns a DataFrame with `_proximity_score` and `_experience_score` columns
- Unit test: values are in [0, 1] range and round to 3 decimal places
- Unit test: `_proximity_score + _experience_score ≈ Score` when star/specialty weights are 0
- Manual: open Results page expander and verify table renders with progress bars

---

## Feature 2: Chatbot Handoff Verification

### Current State

Tasks 2–6 of the prior chatbot-first search plan (`docs/superpowers/plans/2026-05-11-chatbot-first-search.md`) are **already implemented** in the codebase. The project memory file (`memory/project_chatbot_first_search.md`) is stale and reports them as pending.

The following is already in place:
- `_apply_filters()` accepts and writes `user_lat` / `user_lon`
- `_is_city_state_only()` and `_profile_to_weights()` helpers exist
- `_execute_card_search()` and `_render_confirmation_card()` exist
- `render_search_assistant()` renders in the main area with card lifecycle
- Search page wraps form in `"Or search manually"` expander

### Work Required

1. Run the full test suite (`pytest tests/ -v`) — confirm all pass
2. Update `memory/project_chatbot_first_search.md` — mark Tasks 2–6 as done
3. Manual end-to-end verification (Task 7 from the prior plan):
   - Golden path: chatbot extracts filters → confirmation card → Search → Results
   - Card lifecycle: follow-up message replaces card
   - Follow-up question path: LLM asks clarifying question, no card appears
   - Manual form path: independent, navigates to Results correctly

No code changes are expected for the chatbot unless the test run or manual verification reveals a bug.

---

## Out of Scope

- Star rating or specialty score contributions in the breakdown table
- Syncing chatbot and form fields bidirectionally
- Any changes to the scoring algorithm itself
- Changes to the map visualization or export flow

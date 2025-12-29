# Guide for Using AI Assistants (Copilot, ChatGPT, etc.)

This project is designed to be **human-readable first**, even when AI helpers are used to generate code.

When using GitHub Copilot or other AI tools, please follow these guidelines.

---

## 1. Docstrings for public functions

Any function or class that is part of the public surface of the app should have a docstring.

Example pattern (adjust to match this repo’s style):

```python
def query_locations(conn, text: str, filters: dict):
    """
    Query locations matching the given text and filters.

    Parameters
    ----------
    conn :
        Database connection or engine used by this project.
    text : str
        Free-text search or keyword input from the UI.
    filters : dict
        Additional filters (date range, category, etc.) as used in this app.

    Returns
    -------
    DataFrame
        A dataframe of matching records, including coordinates for mapping.
    """
```

**Real example from this project:**

```python
def filter_providers_by_radius(df: pd.DataFrame, max_radius_miles: float) -> pd.DataFrame:
    """Filter providers by maximum radius distance.

    Args:
        df: Provider DataFrame with "Distance (Miles)" column
        max_radius_miles: Maximum distance threshold in miles

    Returns:
        pd.DataFrame: Filtered DataFrame with only providers within radius
    """
    if df is None or df.empty or "Distance (Miles)" not in df.columns:
        return df
    return df[df["Distance (Miles)"] <= max_radius_miles].copy()
```

This function is in [src/app_logic.py](../src/app_logic.py) and shows clear docstring structure:
- Explains the purpose concisely
- Documents each parameter with its type and meaning
- States exactly what gets returned

---

## 2. Comment the "why", not the obvious "what"

Good comments explain intent and assumptions, not trivial operations.

Bad:

```python
i = i + 1  # increment i
```

Good:

```python
# Limit the plotted points to avoid freezing the browser with very large queries.
visible_points = df.head(2000)
```

**Real example from this project:**

In [pages/2_📄_Results.py](../pages/2_📄_Results.py), when displaying provider results:

```python
# Round distance to 1 decimal place for cleaner display
if "Distance (Miles)" in display_df.columns:
    display_df["Distance (Miles)"] = display_df["Distance (Miles)"].round(1)
```

This comment explains *why* we round (cleaner display), not just *what* we're doing (rounding). It helps readers understand the user-facing design decision.

---

## 3. Keep the docs in sync with behavior

Whenever AI assistance helps you add or change:

- A new search or filter option.
- A new visualization or map behavior.
- A new configuration or environment variable.

You should update:

1. `README.md` – high-level behavior and user-facing features.
2. `docs/ARCHITECTURE.md` – how the modules and data flow are wired.

Make sure examples and descriptions match what the app actually does.

---

## 4. Prefer small, testable pieces

When prompting an AI assistant, structure your requests and code so that:

- Functions are focused and testable, for example:
  - `build_filters_ui()`
  - `query_data(...)`
  - `build_map_layer(df)`
- Business logic is separated from Streamlit calls where practical.

This makes it easier to:

- Understand what AI-generated code is doing.
- Replace or refine parts later.
- Add tests around critical logic.

**Refactoring Applied:**

Based on analysis of the codebase, the following refactoring was completed:

- **src/app_logic.py**: Extracted helper functions from `load_application_data()` (originally 155 lines):
  - `_clean_provider_addresses()` - Address and phone number standardization
  - `_enrich_inbound_referrals()` - Inbound referral count calculation
  - `_integrate_preferred_providers()` - Preferred provider list merging and validation
  - `_ensure_referral_counts()` - Referral count data validation
  - Main function reduced to ~50 lines with clear orchestration logic

These helper functions improve testability and make the data loading pipeline easier to understand and maintain.

---

## 5. No "mystery code" in this repo

Before committing any AI-generated code:

- Make sure you can explain what it does in plain language.
- Make sure docstrings and comments are present and accurate.
- If something feels too magical or unclear, simplify or rewrite it.

This is a **portfolio project**: reviewers should be able to understand the code on first read, without guessing.

---

## 6. When to add a short design note

If AI helps you add a non-trivial feature (e.g. new map layer type, caching, complex filtering), consider adding a brief note:

- As a comment at the top of the module, or
- As a bullet in a `docs/` file, or
- As a short note in the README.

That note should answer:

- What the feature does.
- How it’s wired into the existing app.
- Any important trade-offs or limitations.

**Design Notes Added:**

The following design notes have been added to document complex features:

1. **Recommendation Scoring Algorithm** (src/utils/scoring.py):
   - Explains the multi-criteria weighted scoring system
   - Documents normalization strategy and score calculation
   - Describes trade-offs (min-max sensitivity, haversine vs. driving distance)
   - Maps how scoring integrates with the rest of the app

2. **Data Caching Strategy** (src/data/ingestion.py):
   - Details the multi-layer caching approach (Streamlit cache + file modification + daily refresh)
   - Explains cache invalidation triggers and performance characteristics
   - Documents trade-offs between freshness and performance
   - Shows integration with background warming and update workflows

3. **Preferred Provider Integration** (src/app_logic.py):
   - Describes the outer merge strategy for combining provider lists
   - Explains validation checks and quality controls
   - Documents data flow from loading through scoring
   - Discusses design decisions (separate file, boolean flag, name matching)
   - Suggests future enhancements (tiers, fuzzy matching, reason codes)

These design notes provide context for reviewers and maintainers, making the codebase
more understandable without requiring extensive code archaeology.

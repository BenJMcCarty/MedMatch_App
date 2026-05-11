# Chatbot-First Search Design

**Date:** 2026-05-11
**Status:** Approved — ready for implementation planning

---

## Overview

Restructure the Search page so the LLM-powered chat assistant is the primary interface, with the existing form preserved as a secondary collapsed path. The chatbot extracts provider type (specialty), location, radius, gender, and search profile from natural language, pre-fills a confirmation card for user review, then navigates to the existing Results page. No changes to the Results page, scoring engine, or session state contract.

---

## Architecture

Three files change. Everything else is untouched.

### 1. `pages/1_🔎_Search.py`

Page layout changes from:
```
Sidebar: chatbot assistant
Main: hero → form
```
To:
```
Sidebar: (empty)
Main: hero → chatbot (primary) → collapsible form (secondary)
```

The hero banner is unchanged. The chatbot section renders directly below it. The existing form moves into a `st.expander` labeled **"Or search manually"**, collapsed by default, making the independence of the two paths explicit to the user. The form's own "Find Providers" button continues to work exactly as before — no changes to its logic.

The two paths are independent: both write to the same session state keys. The last one to submit wins. There is no synchronization between them.

### 2. `src/components/search_assistant.py`

`render_search_assistant()` is refactored to render in the main content area instead of the sidebar. The function signature and return type are unchanged; only the render target moves.

A **confirmation card** is added. It appears below the chat history whenever the most recent LLM response returned valid JSON (extracted filters). It is hidden whenever the user sends a new message and re-appears only if the new response also returns valid JSON. The card always reflects the most recent valid extraction — never a stale one.

Card contents:
- **Address input** — single free-text field, pre-filled with the `location` string extracted by the LLM (e.g. `"Baltimore, MD"` or `"21201"`). If the extracted location contains no digit (i.e. no street number pattern), it is treated as city/state only and an inline hint reads: *"For best accuracy, add a street address — or continue with city/state."* The field is editable. If the LLM extracted no location, the field is empty.
- **Search button** — disabled when address field is empty. Enabled otherwise.
- **Specialty** — read-only display of extracted specialties, or *"None detected"* if absent.
- **Radius** — badge showing extracted miles (e.g. `20 mi`), or default of `10 mi` if absent.
- **Search profile** — badge showing extracted profile choice, or default of `"Prioritize Proximity (Recommended)"` if absent.
- **Gender** — badge shown only if extracted.

On Search button click:
1. Geocode the address field value via `geocode_address()`.
2. If geocoding fails, show an inline error on the card; address field stays editable; no navigation.
3. If geocoding succeeds, call `_apply_filters()` with all extracted values plus geocoded coordinates, write to session state, navigate to Results via `st.switch_page()`.

> **Implementation note:** `_apply_filters()` currently does not write `user_lat`/`user_lon` — those are set by the form's geocoding step. The chatbot path requires this function to accept and write those coordinates as well. This is a required extension to `_apply_filters()`'s signature.

### 3. `src/utils/llm.py`

System prompt updated to extract one additional field:

```
"location": free-text string of the location the user mentioned
            (e.g. "Baltimore, MD", "21201", "Johns Hopkins area")
            null if no location mentioned
```

Returned alongside the existing `specialty`, `gender`, `radius`, and `profile_choice` fields. The `location` field is passed through to the confirmation card for pre-fill. It is never geocoded by the LLM step — geocoding only happens when the user clicks Search.

---

## Data Flow

```
User types request
       ↓
LLM extracts: specialty, gender, radius, profile_choice, location
       ↓
   Valid JSON?
   ├── No (follow-up question): render as chat message, hide any existing card
   └── Yes: render/update confirmation card with extracted values
                   ↓
           User edits address if needed
                   ↓
           User clicks Search
                   ↓
           geocode_address(address_field_value)
                   ↓
           Geocoding fails? → inline error, stay on page
           Geocoding succeeds?
                   ↓
           _apply_filters() → session state
                   ↓
           st.switch_page("pages/2_📄_Results.py")
```

---

## Edge Cases

| Scenario | Behavior |
|---|---|
| LLM returns follow-up question | Chat message rendered; card hidden if previously showing |
| LLM extracts no location | Address field empty; Search button disabled until user types |
| LLM extracts city/state only | Field pre-filled; inline hint prompts for street address; search allowed |
| User sends new message while card is showing | Card hidden immediately; re-appears only on next valid JSON response |
| User refines in a follow-up ("actually 30 miles") | New extraction replaces card entirely |
| Geocoding fails | Inline error on card; field stays editable; no navigation |
| Missing `ANTHROPIC_API_KEY` | Existing warning behavior preserved; chat unavailable; form still works |
| User ignores chatbot and uses form | Form path fully independent; writes same session state keys; navigates to Results normally |
| User fills chatbot, then submits form | Form overwrites chatbot session state — expected, documented by "Or search manually" label |

---

## Provider Type

"Provider type" (from the original requirements) is handled entirely through the `specialty` field. The LLM maps natural language terms ("therapist", "cardiologist", "physical therapist") to the specialty vocabulary from the dataset. No separate provider-type field exists in the data model or is needed.

---

## Session State Contract

Unchanged. The confirmation card's Search button writes the same keys the form currently writes:

| Key | Type | Description |
|---|---|---|
| `user_lat` | float | Geocoded latitude |
| `user_lon` | float | Geocoded longitude |
| `alpha` | float | Normalized distance weight |
| `beta` | float | Normalized client weight |
| `max_radius_miles` | int | Max search radius |
| `selected_specialties` | list[str] | Specialty filter |
| `selected_genders` | list[str] | Gender filter |
| `full_address` | str | Address string used for geocoding |

---

## Testing

Existing tests for `_apply_filters()` and `_build_confirmation()` remain valid — those functions are not changing behavior.

New tests needed:
- LLM system prompt returns `location` field in extracted JSON (mock API response)
- `location` is `null` when not mentioned by user
- Confirmation card address field pre-filled when location is present
- Confirmation card address field empty when location is absent
- Search button disabled when address field is empty
- Card hidden when user sends a new message
- Card updates (replaces) on new valid JSON response
- Inline hint shown when location appears to be city/state only (no street number)
- Geocoding failure shows inline card error, does not navigate
- Form path ("Or search manually") navigates to Results independently

---

## Out of Scope

- Results page changes
- Scoring algorithm changes
- Inline results on the Search page (no page navigation)
- Syncing chatbot and form fields bidirectionally
- Wizard-style sequential questioning

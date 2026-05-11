# LLM Search Assistant — Design Spec
**Date:** 2026-05-11
**Status:** Approved

## Overview

Add a natural language search assistant to the MedMatch Search page. Users type a plain-English description of what they need ("I need a female cardiologist near Baltimore") and the assistant extracts filter values and pre-fills the existing filter widgets. When the LLM cannot confidently extract a value, it asks one clarifying follow-up question before proceeding. The existing filter UI remains fully functional for manual adjustment.

The design is built to grow into a full conversational assistant (Option C) without structural changes.

---

## Architecture

Three new pieces:

### `src/utils/llm.py`
The only place Claude is called. Stateless — takes a message list, returns a typed result dict. No Streamlit imports.

**Public interface:**
```python
def chat(messages: list[dict], specialties: list[str]) -> dict:
    # Returns one of:
    # {"type": "filters", "data": {"specialty": ..., "gender": ..., "radius": ..., "profile_choice": ...}}
    # {"type": "followup", "data": "clarifying question string"}
    # {"type": "error",   "data": "user-facing error message"}
```

- Model: `claude-haiku-4-5-20251001` (fast, low cost ~$0.001/query)
- API key: `.streamlit/secrets.toml` → `ANTHROPIC_API_KEY`
- System prompt (constant in this file) includes: full specialty list, valid radius range (1–200 mi), gender values (`M`/`F`/`Any`), weight preset names (`proximity`/`balanced`/`experience`), and explicit instruction to return JSON matching the filter schema or ask exactly one clarifying question

### `src/components/search_assistant.py`
Sidebar UI component. Manages conversation state. Calls `llm.py`, then writes extracted values into `st.session_state` filter keys so existing filter widgets pick them up automatically.

**Public interface:**
```python
def render_search_assistant(specialties: list[str]) -> None:
    # Renders inside st.sidebar
    # Manages st.session_state["assistant_messages"] and st.session_state["assistant_pending"]
```

When filters are extracted, displays a confirmation summary chip:
> "Searching for: Female · Cardiology · 25 mi"

User can still adjust any filter manually before clicking Search.

### Search page integration
One import + one call added to `pages/1_🔎_Search.py`. No changes to filter logic, scoring, or results pages.

```python
from src.components.search_assistant import render_search_assistant
render_search_assistant(specialties=specialty_list)
```

---

## Data Flow

### Happy path (unambiguous query)
1. User types query in sidebar input
2. Component appends to `assistant_messages`, calls `llm.chat()`
3. Claude returns extracted filters as JSON
4. Component writes values to `st.session_state` filter keys
5. Confirmation chip shown in sidebar; existing filters update on rerun
6. User reviews, adjusts if needed, clicks Search

### Clarification path
1. Claude returns `{"type": "followup", "data": "question string"}`
2. Question displayed in sidebar as assistant message
3. User types answer; full history sent to Claude on next call
4. Claude extracts filters from combined context; flow continues from step 4 above

### Error path
- Unparseable Claude response → `{"type": "error"}` → friendly sidebar message, filters untouched
- Missing API key → startup warning in sidebar, assistant input disabled
- API timeout / network failure → error message in sidebar, filters untouched

---

## Session State Keys

| Key | Type | Purpose |
|-----|------|---------|
| `assistant_messages` | `list[dict]` | Full conversation history (`{"role": ..., "content": ...}`) |
| `assistant_pending` | `bool` | True while waiting for LLM response (shows spinner) |

Filter keys written by the assistant are the same keys the existing widgets already read — no new keys introduced.

---

## Option C Readiness

- `assistant_messages` history is stored from day one; multi-turn is already functional
- `chat()` accepts a full message list, not a single string
- When growing to Option C: `render_search_assistant` gains a message history display; `llm.py` gains no changes
- LLM logic is fully isolated from the page — the upgrade path is additive, not a rewrite

---

## Out of Scope

- Results explanation / provider narration (Option B)
- General Q&A about the algorithm or data (Option C)
- Admin-facing LLM features
- Streaming responses (not needed for short structured outputs)
- Conversation persistence across page reloads

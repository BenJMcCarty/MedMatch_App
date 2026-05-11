# LLM Search Assistant Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a sidebar LLM assistant to the Search page that accepts plain-English queries, extracts filter values via Claude, and pre-fills existing filter widgets — with follow-up clarification when the intent is ambiguous.

**Architecture:** A stateless `src/utils/llm.py` module handles all Claude API calls and returns typed result dicts. A `src/components/search_assistant.py` component owns sidebar rendering and session state, calling the LLM module and writing extracted values into the same `st.session_state` keys the existing filter widgets already read. The Search page adds one import and one call; no other page logic changes.

**Tech Stack:** `anthropic` Python SDK (`claude-haiku-4-5-20251001`), Streamlit session state, pytest + unittest.mock

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `src/utils/llm.py` | Claude API calls, response parsing, typed result dicts |
| Create | `src/components/__init__.py` | Package marker |
| Create | `src/components/search_assistant.py` | Sidebar UI, session state, calls llm.py |
| Create | `tests/utils/test_llm.py` | Unit tests for llm.py |
| Create | `tests/components/__init__.py` | Package marker |
| Create | `tests/components/test_search_assistant.py` | Unit tests for _apply_filters |
| Modify | `requirements.txt` | Add `anthropic>=0.40.0` |
| Modify | `.streamlit/secrets.toml` | Add `ANTHROPIC_API_KEY` placeholder |
| Modify | `pages/1_🔎_Search.py` | Import + hoist specialties/genders + render call |

---

## Task 1: Add anthropic dependency and API key placeholder

**Files:**
- Modify: `requirements.txt`
- Modify: `.streamlit/secrets.toml`

- [ ] **Step 1: Add anthropic to requirements.txt**

Open `requirements.txt` and add after the `geopy` line:

```
anthropic>=0.40.0
```

- [ ] **Step 2: Add API key placeholder to secrets.toml**

Open `.streamlit/secrets.toml` and add at the bottom:

```toml
ANTHROPIC_API_KEY = ""
```

Leave the value empty for now — you will fill it in with your real key before testing. The file is already gitignored.

- [ ] **Step 3: Install the new dependency**

```bash
pip install anthropic>=0.40.0
```

Expected: installs without error, `anthropic` appears in `pip list`.

- [ ] **Step 4: Commit**

```bash
git add requirements.txt .streamlit/secrets.toml
git commit -m "feat: add anthropic dependency and API key placeholder"
```

---

## Task 2: Create src/components package

**Files:**
- Create: `src/components/__init__.py`
- Create: `tests/components/__init__.py`

- [ ] **Step 1: Create the package files**

Create `src/components/__init__.py` as an empty file.

Create `tests/components/__init__.py` as an empty file.

- [ ] **Step 2: Verify pytest still passes**

```bash
pytest tests/ -v
```

Expected: all existing tests pass, no import errors.

- [ ] **Step 3: Commit**

```bash
git add src/components/__init__.py tests/components/__init__.py
git commit -m "feat: add src/components package"
```

---

## Task 3: Implement src/utils/llm.py with tests (TDD)

**Files:**
- Create: `tests/utils/test_llm.py`
- Create: `src/utils/llm.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/utils/test_llm.py`:

```python
import json
import pytest
from unittest.mock import MagicMock, patch


def _make_response(text):
    response = MagicMock()
    response.content = [MagicMock(text=text)]
    return response


def test_chat_returns_filters_on_valid_json():
    payload = '{"specialty": "Cardiology", "gender": "F", "radius": 25, "profile_choice": "Balanced"}'
    with patch("src.utils.llm.Anthropic") as mock_cls, patch("src.utils.llm.st") as mock_st:
        mock_st.secrets.get.return_value = "test-key"
        mock_cls.return_value.messages.create.return_value = _make_response(payload)

        from src.utils.llm import chat
        result = chat([{"role": "user", "content": "female cardiologist"}], ["Cardiology"])

    assert result["type"] == "filters"
    assert result["data"]["specialty"] == "Cardiology"
    assert result["data"]["gender"] == "F"
    assert result["data"]["radius"] == 25
    assert result["data"]["profile_choice"] == "Balanced"


def test_chat_returns_followup_on_plain_text():
    with patch("src.utils.llm.Anthropic") as mock_cls, patch("src.utils.llm.st") as mock_st:
        mock_st.secrets.get.return_value = "test-key"
        mock_cls.return_value.messages.create.return_value = _make_response(
            "How far are you willing to travel?"
        )

        from src.utils.llm import chat
        result = chat([{"role": "user", "content": "I need a doctor"}], ["Cardiology"])

    assert result["type"] == "followup"
    assert result["data"] == "How far are you willing to travel?"


def test_chat_returns_error_when_api_key_missing():
    with patch("src.utils.llm.st") as mock_st:
        mock_st.secrets.get.return_value = None

        from src.utils.llm import chat
        result = chat([{"role": "user", "content": "test"}], ["Cardiology"])

    assert result["type"] == "error"
    assert "ANTHROPIC_API_KEY" in result["data"]


def test_chat_returns_error_on_api_exception():
    with patch("src.utils.llm.Anthropic") as mock_cls, patch("src.utils.llm.st") as mock_st:
        mock_st.secrets.get.return_value = "test-key"
        mock_cls.return_value.messages.create.side_effect = Exception("network error")

        from src.utils.llm import chat
        result = chat([{"role": "user", "content": "test"}], ["Cardiology"])

    assert result["type"] == "error"


def test_chat_passes_full_message_history():
    payload = '{"specialty": "Cardiology", "gender": null, "radius": null, "profile_choice": null}'
    messages = [
        {"role": "user", "content": "I need a cardiologist"},
        {"role": "assistant", "content": "How far are you willing to travel?"},
        {"role": "user", "content": "Within 25 miles"},
    ]
    with patch("src.utils.llm.Anthropic") as mock_cls, patch("src.utils.llm.st") as mock_st:
        mock_st.secrets.get.return_value = "test-key"
        mock_create = mock_cls.return_value.messages.create
        mock_create.return_value = _make_response(payload)

        from src.utils.llm import chat
        chat(messages, ["Cardiology"])

    called_messages = mock_create.call_args.kwargs["messages"]
    assert len(called_messages) == 3
    assert called_messages[2]["content"] == "Within 25 miles"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/utils/test_llm.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.utils.llm'` or `ImportError`.

- [ ] **Step 3: Implement src/utils/llm.py**

Create `src/utils/llm.py`:

```python
import json

import streamlit as st
from anthropic import Anthropic

_SYSTEM_PROMPT = """\
You are a search assistant for MedMatch, a healthcare provider recommender.

Extract filter values from the user's request and return a JSON object with exactly these fields:
- "specialty": one of [{specialties}], or null if not mentioned
- "gender": "M", "F", or null if not mentioned
- "radius": integer 1-200 (miles), or null if not mentioned
- "profile_choice": one of "Prioritize Proximity (Recommended)", "Balanced", \
"Prioritize Experience", "Custom Settings", or null if not mentioned

If you cannot confidently fill in the values, ask ONE short clarifying question instead.

Return ONLY the JSON object, or ONLY the question. No explanation, no extra text."""


def chat(messages: list[dict], specialties: list[str]) -> dict:
    """Call Claude to extract filters or get a clarifying follow-up question.

    Returns one of:
      {"type": "filters",  "data": {"specialty": ..., "gender": ..., "radius": ..., "profile_choice": ...}}
      {"type": "followup", "data": "question string"}
      {"type": "error",    "data": "user-facing error message"}
    """
    api_key = st.secrets.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {"type": "error", "data": "Assistant unavailable: ANTHROPIC_API_KEY not configured in secrets.toml."}

    try:
        client = Anthropic(api_key=api_key)
        system = _SYSTEM_PROMPT.format(specialties=", ".join(specialties))
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            system=system,
            messages=messages,
        )
        content = response.content[0].text.strip()

        try:
            data = json.loads(content)
            return {"type": "filters", "data": data}
        except json.JSONDecodeError:
            return {"type": "followup", "data": content}

    except Exception as e:
        return {"type": "error", "data": f"Assistant temporarily unavailable. ({type(e).__name__})"}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/utils/test_llm.py -v
```

Expected: all 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/utils/llm.py tests/utils/test_llm.py
git commit -m "feat: add llm.py Claude API wrapper with tests"
```

---

## Task 4: Implement src/components/search_assistant.py with tests (TDD)

**Files:**
- Create: `tests/components/test_search_assistant.py`
- Create: `src/components/search_assistant.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/components/test_search_assistant.py`:

```python
import pytest
from src.components.search_assistant import _apply_filters

SPECIALTIES = ["Cardiology", "Internal Medicine", "Psychiatry"]
GENDERS = ["M", "F"]


def test_apply_filters_sets_specialty():
    state = {}
    _apply_filters(
        {"specialty": "Cardiology", "gender": None, "radius": None, "profile_choice": None},
        SPECIALTIES, GENDERS, state,
    )
    assert state["selected_specialties"] == ["Cardiology"]


def test_apply_filters_ignores_unknown_specialty():
    state = {}
    _apply_filters(
        {"specialty": "Unknown Specialty", "gender": None, "radius": None, "profile_choice": None},
        SPECIALTIES, GENDERS, state,
    )
    assert "selected_specialties" not in state


def test_apply_filters_sets_gender():
    state = {}
    _apply_filters(
        {"specialty": None, "gender": "F", "radius": None, "profile_choice": None},
        SPECIALTIES, GENDERS, state,
    )
    assert state["selected_genders"] == ["F"]


def test_apply_filters_ignores_unknown_gender():
    state = {}
    _apply_filters(
        {"specialty": None, "gender": "X", "radius": None, "profile_choice": None},
        SPECIALTIES, GENDERS, state,
    )
    assert "selected_genders" not in state


def test_apply_filters_sets_radius():
    state = {}
    _apply_filters(
        {"specialty": None, "gender": None, "radius": 50, "profile_choice": None},
        SPECIALTIES, GENDERS, state,
    )
    assert state["max_radius_miles"] == 50


def test_apply_filters_ignores_out_of_range_radius():
    state = {}
    _apply_filters(
        {"specialty": None, "gender": None, "radius": 500, "profile_choice": None},
        SPECIALTIES, GENDERS, state,
    )
    assert "max_radius_miles" not in state


def test_apply_filters_sets_profile_choice():
    state = {}
    _apply_filters(
        {"specialty": None, "gender": None, "radius": None, "profile_choice": "Balanced"},
        SPECIALTIES, GENDERS, state,
    )
    assert state["profile_choice"] == "Balanced"


def test_apply_filters_ignores_invalid_profile_choice():
    state = {}
    _apply_filters(
        {"specialty": None, "gender": None, "radius": None, "profile_choice": "Made Up"},
        SPECIALTIES, GENDERS, state,
    )
    assert "profile_choice" not in state


def test_apply_filters_sets_multiple_fields():
    state = {}
    _apply_filters(
        {"specialty": "Psychiatry", "gender": "M", "radius": 10, "profile_choice": "Prioritize Proximity (Recommended)"},
        SPECIALTIES, GENDERS, state,
    )
    assert state["selected_specialties"] == ["Psychiatry"]
    assert state["selected_genders"] == ["M"]
    assert state["max_radius_miles"] == 10
    assert state["profile_choice"] == "Prioritize Proximity (Recommended)"


def test_apply_filters_does_not_touch_unspecified_keys():
    state = {"selected_specialties": ["Internal Medicine"]}
    _apply_filters(
        {"specialty": None, "gender": "F", "radius": None, "profile_choice": None},
        SPECIALTIES, GENDERS, state,
    )
    assert state["selected_specialties"] == ["Internal Medicine"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/components/test_search_assistant.py -v
```

Expected: `ImportError: cannot import name '_apply_filters' from 'src.components.search_assistant'`.

- [ ] **Step 3: Implement src/components/search_assistant.py**

Create `src/components/search_assistant.py`:

```python
import streamlit as st

from src.utils.llm import chat

_VALID_PROFILE_CHOICES = {
    "Prioritize Proximity (Recommended)",
    "Balanced",
    "Prioritize Experience",
    "Custom Settings",
}

_GENDER_LABELS = {"M": "Male", "F": "Female"}


def _apply_filters(
    filters: dict,
    available_specialties: list[str],
    available_genders: list[str],
    state: dict,
) -> None:
    """Write extracted filter values into state (typically st.session_state)."""
    if filters.get("specialty") and filters["specialty"] in available_specialties:
        state["selected_specialties"] = [filters["specialty"]]

    if filters.get("gender") and filters["gender"] in available_genders:
        state["selected_genders"] = [filters["gender"]]

    if filters.get("radius") is not None:
        radius = int(filters["radius"])
        if 1 <= radius <= 200:
            state["max_radius_miles"] = radius

    if filters.get("profile_choice") in _VALID_PROFILE_CHOICES:
        state["profile_choice"] = filters["profile_choice"]


def _build_confirmation(filters: dict) -> str:
    parts = []
    if filters.get("specialty"):
        parts.append(filters["specialty"])
    if filters.get("gender"):
        parts.append(_GENDER_LABELS.get(filters["gender"], filters["gender"]))
    if filters.get("radius"):
        parts.append(f"{filters['radius']} mi")
    if filters.get("profile_choice"):
        parts.append(filters["profile_choice"])
    return "Searching for: " + (" · ".join(parts) if parts else "your criteria")


def render_search_assistant(specialties: list[str], genders: list[str]) -> None:
    """Render the LLM search assistant in the sidebar."""
    if "assistant_messages" not in st.session_state:
        st.session_state["assistant_messages"] = []
    if "assistant_pending" not in st.session_state:
        st.session_state["assistant_pending"] = False

    st.sidebar.title("🤖 Search Assistant")
    st.sidebar.caption("Describe what you're looking for in plain English.")

    for msg in st.session_state["assistant_messages"]:
        label = "**You:** " if msg["role"] == "user" else "**Assistant:** "
        st.sidebar.markdown(label + msg["content"])

    user_input = st.sidebar.text_input(
        "Your request",
        key="assistant_input",
        placeholder="e.g. Female cardiologist within 25 miles",
        label_visibility="collapsed",
    )

    if st.sidebar.button("Send", key="assistant_send") and user_input.strip():
        st.session_state["assistant_messages"].append(
            {"role": "user", "content": user_input.strip()}
        )
        st.session_state["assistant_pending"] = True
        st.rerun()

    if st.session_state["assistant_pending"]:
        with st.sidebar:
            with st.spinner("Thinking..."):
                result = chat(st.session_state["assistant_messages"], specialties)
        st.session_state["assistant_pending"] = False

        if result["type"] == "filters":
            _apply_filters(result["data"], specialties, genders, st.session_state)
            reply = _build_confirmation(result["data"])
        else:
            reply = result["data"]

        st.session_state["assistant_messages"].append(
            {"role": "assistant", "content": reply}
        )
        st.rerun()

    if st.session_state["assistant_messages"]:
        if st.sidebar.button("Clear", key="assistant_clear"):
            st.session_state["assistant_messages"] = []
            st.rerun()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/components/test_search_assistant.py -v
```

Expected: all 10 tests pass.

- [ ] **Step 5: Run full test suite to verify no regressions**

```bash
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/components/search_assistant.py tests/components/test_search_assistant.py
git commit -m "feat: add search_assistant component with _apply_filters"
```

---

## Task 5: Wire the assistant into the Search page

**Files:**
- Modify: `pages/1_🔎_Search.py`

- [ ] **Step 1: Add the import**

In `pages/1_🔎_Search.py`, add after the existing `from src.utils.geocoding import geocode_address` import block (around line 17):

```python
from src.components.search_assistant import render_search_assistant
```

- [ ] **Step 2: Hoist specialty and gender computation**

In `pages/1_🔎_Search.py`, find the line that reads (around line 83):

```python
st.info(f"📊 **{provider_count:,} providers available** in our network")
```

Add the following two lines immediately after it:

```python
available_specialties = get_unique_specialties(provider_df)
available_genders = get_unique_genders(provider_df)
render_search_assistant(specialties=available_specialties, genders=available_genders)
```

- [ ] **Step 3: Remove the duplicate specialty computation inside the expander**

Find this line inside the "Search Criteria" expander (around line 219):

```python
        available_specialties = get_unique_specialties(provider_df)
```

Delete that line. The variable is now defined above and available in scope.

- [ ] **Step 4: Remove the duplicate gender computation inside the expander**

Find this line inside the "Advanced Filters" expander (around line 258):

```python
    available_genders = get_unique_genders(provider_df)
```

Delete that line. The variable is now defined above and available in scope.

- [ ] **Step 5: Add your API key to secrets.toml**

Open `.streamlit/secrets.toml` and fill in your Anthropic API key:

```toml
ANTHROPIC_API_KEY = "sk-ant-..."
```

Get a key from https://console.anthropic.com/. The file is gitignored so it will not be committed.

- [ ] **Step 6: Start the app and manually test the assistant**

```bash
streamlit run app.py
```

Navigate to the Search page. The sidebar should show "🤖 Search Assistant" with a text input. Test these scenarios:

1. Type `"Female cardiologist within 20 miles"` → filters should pre-fill (Female gender, Cardiology specialty, 20 mi radius)
2. Type `"I need a doctor"` → assistant should ask a follow-up question
3. Answer the follow-up → filters should pre-fill from the combined context
4. Verify existing filter widgets still work independently after assistant pre-fills them
5. Click "Clear" → conversation history resets

- [ ] **Step 7: Commit**

```bash
git add "pages/1_🔎_Search.py"
git commit -m "feat: wire LLM search assistant into Search page sidebar"
```

---

## Done

All five tasks produce working, testable software. The assistant is live on the Search page.

**Option C upgrade path (future):** To grow into a full conversational assistant, expand `render_search_assistant` to display `assistant_messages` as a chat thread and add additional system prompt capabilities. `src/utils/llm.py` requires no changes — it already handles multi-turn via the full message history.

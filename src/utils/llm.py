import json
import re

import streamlit as st
from anthropic import Anthropic


def _strip_code_fence(text: str) -> str:
    """Remove markdown code fences that Claude sometimes wraps JSON in."""
    match = re.match(r"^```(?:json)?\s*([\s\S]*?)\s*```$", text.strip())
    return match.group(1) if match else text

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


def chat(messages: list[dict], specialties: list[str]) -> dict:
    """Call Claude to extract filters or get a clarifying follow-up question.

    Returns one of:
      {"type": "filters",  "data": {"specialty": ..., "gender": ..., "radius": ..., "profile_choice": ..., "location": ...}}
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
        content = _strip_code_fence(response.content[0].text.strip())

        try:
            data = json.loads(content)
            return {"type": "filters", "data": data}
        except json.JSONDecodeError:
            return {"type": "followup", "data": content}

    except Exception as e:
        return {"type": "error", "data": f"Assistant temporarily unavailable. ({type(e).__name__})"}

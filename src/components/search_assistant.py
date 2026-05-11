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
            st.session_state["assistant_messages"].append(
                {"role": "assistant", "content": reply}
            )
        elif result["type"] == "followup":
            st.session_state["assistant_messages"].append(
                {"role": "assistant", "content": result["data"]}
            )
        else:
            st.sidebar.error(result["data"])

        st.rerun()

    if st.session_state["assistant_messages"]:
        if st.sidebar.button("Clear", key="assistant_clear"):
            st.session_state["assistant_messages"] = []
            st.rerun()

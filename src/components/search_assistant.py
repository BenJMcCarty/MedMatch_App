import streamlit as st

from src.utils.llm import chat

_VALID_PROFILE_CHOICES = {
    "Prioritize Proximity (Recommended)",
    "Balanced",
    "Prioritize Experience",
    "Custom Settings",
}

_GENDER_LABELS = {"M": "Male", "F": "Female"}

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

    # Always reset to full defaults first so a second chatbot search never
    # inherits stale values from a previous search.
    st.session_state["selected_specialties"] = available_specialties
    st.session_state["selected_genders"] = available_genders
    st.session_state["max_radius_miles"] = 10

    # Now override defaults with whatever the LLM actually extracted.
    _apply_filters(
        filters,
        available_specialties,
        available_genders,
        st.session_state,
        user_lat=user_lat,
        user_lon=user_lon,
    )

    st.session_state.update({
        "alpha": float(alpha),
        "beta": float(beta),
        "full_address": address,
    })

    st.session_state.pop("last_best", None)
    st.session_state.pop("last_scored_df", None)

    st.switch_page("pages/2_📄_Results.py")


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
        # Exact case-insensitive match first (LLM returned the exact specialty name).
        matches = [s for s in available_specialties if s.lower() == specialty_lower]
        if not matches:
            # Partial fallback: LLM returned a variation (e.g. "Therapy" for
            # "Individual Therapy", "cardiologist" for "Cardiology"). Collect
            # every specialty that contains the term or is contained by it.
            matches = [
                s for s in available_specialties
                if specialty_lower in s.lower() or s.lower() in specialty_lower
            ]
        if matches:
            state["selected_specialties"] = matches

    if filters.get("gender"):
        raw_gender = filters["gender"]
        # LLM returns single-letter codes ("M"/"F"); available_genders uses full
        # words ("Male"/"Female") from the dataframe. Resolve to whichever format
        # is actually present so the downstream filter receives a matchable value.
        resolved_gender = _GENDER_LABELS.get(raw_gender, raw_gender)
        if resolved_gender in available_genders:
            state["selected_genders"] = [resolved_gender]
        elif raw_gender in available_genders:
            state["selected_genders"] = [raw_gender]

    if filters.get("radius") is not None:
        radius = int(filters["radius"])
        if 1 <= radius <= 200:
            state["max_radius_miles"] = radius

    if filters.get("profile_choice") in _VALID_PROFILE_CHOICES:
        state["profile_choice"] = filters["profile_choice"]

    if user_lat is not None and user_lon is not None:
        state["user_lat"] = float(user_lat)
        state["user_lon"] = float(user_lon)


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

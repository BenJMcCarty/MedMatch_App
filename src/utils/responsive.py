"""Small responsive helpers for Streamlit layouts.

This file provides a minimal, deterministic way to force a stacked (mobile)
layout during development or testing via a sidebar toggle. It intentionally
avoids fragile JS-based viewport detection so behavior is predictable in CI
and tests.
"""
from typing import List

import streamlit as st


def is_mobile_view() -> bool:
    """Return True when the app should render in stacked/mobile mode.

    This value is controlled by a sidebar checkbox named ``force_mobile_layout``.
    Keeping it explicit makes layout deterministic for screenshots and tests.
    """
    return bool(st.session_state.get("force_mobile_layout", False))


def responsive_sidebar_toggle() -> None:
    """Render a small sidebar toggle to force mobile layout (for debugging).

    Call this once near the top of pages that need responsive behavior so
    developers can switch layouts without resizing the browser.
    """
    # Create the checkbox only once per session/run. Calling this helper
    # multiple times (across pages or components) would otherwise attempt
    # to create multiple Streamlit widgets with the same key and raise
    # StreamlitDuplicateElementKey. We keep the value in session state.
    if "force_mobile_layout" not in st.session_state:
        st.session_state["force_mobile_layout"] = False
        st.sidebar.checkbox("Force mobile layout (debug)", key="force_mobile_layout")
    # If the key already exists in session state the checkbox has been
    # rendered earlier in this run; do not create it again.


def resp_columns(widths: List[float]):
    """Responsive replacement for st.columns.

    - On desktop (default) this returns the result of st.columns(widths).
    - When mobile is forced it returns a list of st.container objects which
      stack vertically but support the same "with <col>:" usage pattern.

    Example:
        col1, col2 = resp_columns([2, 1])
        with col1:
            st.write("left")
        with col2:
            st.write("right")
    """
    if is_mobile_view():
        return [st.container() for _ in widths]
    return st.columns(widths)

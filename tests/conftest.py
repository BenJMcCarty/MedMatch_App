import sys
from unittest.mock import MagicMock

# Mock streamlit before any src.utils module is imported.
# @st.cache_data(ttl=...) becomes a passthrough decorator in tests.
_st = MagicMock()
_st.cache_data = lambda **kwargs: (lambda func: func)
_st.warning = lambda *a, **k: None
_st.error = lambda *a, **k: None
sys.modules["streamlit"] = _st

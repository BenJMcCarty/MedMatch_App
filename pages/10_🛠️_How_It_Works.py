import streamlit as st

st.set_page_config(page_title="How It Works", page_icon="🛠️", layout="wide")

st.title("How the Provider Recommender Works")

st.markdown(
    """
    The Provider Recommender helps you quickly find and rank providers for a client by combining
    location, past referral activity, and simple preference controls.
    """
)

st.header("Quick Summary — For End-Users")
st.markdown(
    """
    - Enter a client's address and choose a few simple preferences.
    - The app returns a ranked list of providers optimized for distance and experience.
    - Results include contact details, distance, and export options.
    """
)

st.header("How to Use")
st.markdown(
    """
    1. Go to the Search page and enter the client's address.
    2. Adjust the sliders to set how important distance and experience are.
    3. Optionally set radius and minimum client count filters.
    4. Click Find Providers to get a ranked list.
    """
)

st.markdown("---")

st.header("Behind the Scenes (Brief)")
st.markdown(
    """
    - Addresses are geocoded to coordinates.
    - Distances are calculated using an accurate haversine formula.
    - Providers are scored using a combination of distance and client count (experience).
    - The app uses local parquet data files and applies cleaning, deduplication, and validation.
    """
)

with st.expander("Scoring Summary", expanded=False):
    st.markdown(
        """
        Scoring combines two factors: Distance (closer is better) and Client Count (more clients indicates more experience).
        You control the relative importance with sliders. The system normalizes weights automatically.
        """
    )

st.markdown("---")

st.header("Advanced technical details")
st.markdown(
    """
    Developers and administrators can find full technical documentation (S3 ingestion, caching, geocoding rate limits, scoring formulas and code examples) in README.md and the `docs/` folder.
    """
)

st.info("See README.md → Advanced Technical Details for full implementation and operational guidance.")
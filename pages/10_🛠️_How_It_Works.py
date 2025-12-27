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
    - The app returns a ranked list of providers optimized for distance, experience, and relationships.
    - Results include contact details, distance, and export options.
    """
)

st.header("How to Use")
st.markdown(
    """
    1. Go to the Search page and enter the client's address.
    2. Adjust the sliders to set how important distance, experience, and referrals are.
    3. Optionally set radius and minimum referral filters.
    4. Click Find Providers to get a ranked list and map.
    """
)

st.markdown("---")

st.header("Behind the Scenes (Brief)")
st.markdown(
    """
    - Addresses are geocoded to coordinates.
    - Distances are calculated using an accurate haversine formula.
    - Providers are scored using a combination of distance, outbound referrals, inbound referrals, and preferred status.
    - The app uses secure S3-based data and applies cleaning, deduplication, and validation.
    """
)

with st.expander("Scoring Summary", expanded=False):
    st.markdown(
        """
        Scoring mixes four factors: Distance (closer is better), Outbound referrals (experience), Inbound referrals (reciprocity), and Preferred provider status.
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
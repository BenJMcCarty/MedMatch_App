import datetime as dt

import streamlit as st

from app import show_auto_update_status
from src.app_logic import get_unique_genders, get_unique_specialties, load_application_data
from src.utils.addressing import validate_address_input
from src.utils.responsive import resp_columns

try:
    from src.utils.geocoding import geocode_address_with_cache

    GEOCODE_AVAILABLE = True
except Exception:
    geocode_address_with_cache = None
    GEOCODE_AVAILABLE = False

# Constants - define once at module level for performance
PRESET_ADDRESSES = {
    "Baltimore": {"street": "100 N Charles St", "city": "Baltimore", "state": "MD", "zipcode": "21201"},
    "Anne Arundel County": {"street": "8222 Spadderdock Way", "city": "Russett", "state": "MD", "zipcode": "20724"},
    "Montgomery County": {"street": "12500 Parklawn Dr", "city": "Rockville", "state": "MD", "zipcode": "20852"},
}

US_STATES = [
    "MD",
    "AL",
    "AK",
    "AZ",
    "AR",
    "CA",
    "CO",
    "CT",
    "DE",
    "FL",
    "GA",
    "HI",
    "ID",
    "IL",
    "IN",
    "IA",
    "KS",
    "KY",
    "LA",
    "ME",
    "MA",
    "MI",
    "MN",
    "MS",
    "MO",
    "MT",
    "NE",
    "NV",
    "NH",
    "NJ",
    "NM",
    "NY",
    "NC",
    "ND",
    "OH",
    "OK",
    "OR",
    "PA",
    "RI",
    "SC",
    "SD",
    "TN",
    "TX",
    "UT",
    "VT",
    "VA",
    "WA",
    "WV",
    "WI",
    "WY",
    "DC",
]

st.set_page_config(page_title="MedMatch - Provider Recommender", page_icon="🏥", layout="wide")

# # Show S3 auto-update status if available
# show_auto_update_status()

# Hero section - welcoming landing page
st.title("🏥 MedMatch Provider Recommender")
st.subheader("Find the right healthcare provider for your client — quickly and confidently!")

# Load data once - this is cached by @st.cache_data in load_application_data
try:
    provider_df, detailed_referrals_df = load_application_data()
except Exception as e:
    st.error("❌ Failed to load provider data. Please ensure data files are available or contact support.")
    st.info(f"**Error Type:** {type(e).__name__}")
    st.info(f"**Technical details:** {str(e)}")

    # Show more helpful context
    with st.expander("🔍 Troubleshooting Information"):
        st.markdown("""
        **Common causes:**
        - Missing required Python packages (openpyxl, pandas, etc.)

        **Next steps:**
        1. Check Streamlit logs for detailed error messages
        2. Try refreshing the page or restarting the app
        """)

        # Show the full exception for debugging
        import traceback
        st.code(traceback.format_exc(), language="python")

    st.stop()

# Validate data is available before proceeding
if provider_df.empty:
    st.error("❌ No provider data available.")
    st.info("💡 Please upload data using the 'Update Data' page or contact support.")
    st.stop()

st.divider()

# Stats banner showing available providers
provider_count = len(provider_df)
st.info(f"📊 **{provider_count:,} providers available** in our network")

# Address input section with improved layout
st.subheader("📍 Client Address")
st.markdown("⚠️ Currently only Maryland (MD) providers are supported. More states coming soon! ⚠️")

# Set defaults based on session state
prev_street = st.session_state.get("street", "")
prev_city = st.session_state.get("city", "")
prev_state = st.session_state.get("state", None)
prev_zipcode = st.session_state.get("zipcode", "")

col1, col2 = resp_columns([1, 1])

with col1:
    street = str(st.text_input("Street Address", prev_street, help="Enter the client's street address"))
with col2:
    city = str(st.text_input("City", prev_city, help="Enter the client's city"))

col3, col4 = resp_columns([1, 1])

with col3:
    default_index = US_STATES.index(prev_state) if prev_state in US_STATES else 0

    state = st.selectbox(
        "State", options=US_STATES, index=default_index, help="Select the client's state (2-letter abbreviation)"
    )

    state = state.upper() if isinstance(state, str) else None

with col4:
    zipcode = str(st.text_input("ZIP Code", prev_zipcode, help="5-digit ZIP code"))

# Preset address buttons for quick testing
st.markdown("**Quick Examples:**")
preset_cols = st.columns(len(PRESET_ADDRESSES))
for idx, (preset_name, preset_data) in enumerate(PRESET_ADDRESSES.items()):
    if preset_cols[idx].button(f"📍 {preset_name}", use_container_width=True):
        st.session_state.update({
            "street": preset_data["street"],
            "city": preset_data["city"],
            "state": preset_data["state"],
            "zipcode": preset_data["zipcode"],
            "use_test_address": False,
        })
        st.rerun()

st.divider()

# Search Profile — button group
st.subheader("🎯 Search Profile")
st.markdown("Choose a search strategy, or customize your own weights below.")

profile_cols = st.columns(4)
with profile_cols[0]:
    if st.button("🎯 Prioritize Proximity", use_container_width=True):
        st.session_state["profile_choice"] = "Prioritize Proximity (Recommended)"
        st.rerun()

with profile_cols[1]:
    if st.button("⚖️ Balanced", use_container_width=True):
        st.session_state["profile_choice"] = "Balanced"
        st.rerun()

with profile_cols[2]:
    if st.button("⭐ Prioritize Experience", use_container_width=True):
        st.session_state["profile_choice"] = "Prioritize Experience"
        st.rerun()

with profile_cols[3]:
    if st.button("⚙️ Customize", use_container_width=True):
        st.session_state["profile_choice"] = "Custom Settings"
        st.rerun()

preset_choice = st.session_state.get("profile_choice", "Prioritize Proximity (Recommended)")
st.caption(f"**Selected:** {preset_choice}")

# Set weights based on preset
if preset_choice == "Prioritize Proximity (Recommended)":
    distance_weight = 1.0
    client_weight = 0.0
elif preset_choice == "Balanced":
    distance_weight = 0.5
    client_weight = 0.5
elif preset_choice == "Prioritize Experience":
    distance_weight = 0.3
    client_weight = 0.7
else:  # Custom Settings
    default_distance = 0.5
    default_client = 0.5

    with st.expander("⚖️ Custom Scoring Weights", expanded=True):
        st.caption("Adjust these sliders to control how each factor influences the recommendation.")

        distance_weight = st.slider(
            "📍 Distance Importance",
            0.0,
            1.0,
            st.session_state.get("distance_weight", default_distance),
            0.05,
            help="Higher values prioritize providers closer to the client",
        )
        client_weight = st.slider(
            "📊 Experience Importance",
            0.0,
            1.0,
            st.session_state.get("client_weight", default_client),
            0.05,
            help="Higher values favor providers with MORE clients (more experienced)",
        )

# Calculate normalized weights
total = distance_weight + client_weight
if total == 0:
    st.error("⚠️ At least one weight must be greater than 0. Please adjust your settings.")
    alpha = beta = 0.0
else:
    alpha = distance_weight / total
    beta = client_weight / total

if preset_choice == "Custom Settings":
    with st.expander("📊 View Normalized Weights"):
        st.caption("Your settings automatically adjusted to total 100%:")
        cols = st.columns(2)
        cols[0].metric("Distance", f"{alpha*100:.0f}%")
        cols[1].metric("Experience", f"{beta*100:.0f}%")

# Search Criteria — always visible
st.subheader("🔍 Search Criteria")

col_specialty, col_distance = resp_columns([2, 1])

with col_specialty:
    st.caption("**Provider Specialties**")
    available_specialties = get_unique_specialties(provider_df)

    if available_specialties:
        default_selected = st.session_state.get("selected_specialties", available_specialties)
        selected_specialties = st.multiselect(
            "Filter by Specialty",
            options=available_specialties,
            default=default_selected,
            help="Select one or more provider specialties.",
            label_visibility="collapsed",
        )
    else:
        selected_specialties = []
        st.info("ℹ️ No specialty information available.")

with col_distance:
    st.caption("**Distance Radius**")
    max_radius_miles = st.number_input(
        "Maximum Distance (miles)",
        min_value=0,
        max_value=200,
        value=st.session_state.get("max_radius_miles", 10),
        step=1,
        help="Set to 0 for all providers, or specify maximum miles.",
        label_visibility="collapsed",
    )

# Advanced filters — collapsed by default
with st.expander("⚙️ Advanced Filters (Optional)", expanded=False):
    st.caption("Additional options to refine your search.")

    use_test_address = st.checkbox(
        "Use test address as default",
        value=st.session_state.get("use_test_address", False),
        help="Pre-fill the form with a test address"
    )
    st.session_state["use_test_address"] = use_test_address

    st.caption("**Provider Gender**")
    available_genders = get_unique_genders(provider_df)

    if available_genders:
        default_selected_genders = st.session_state.get("selected_genders", available_genders)
        selected_genders = st.multiselect(
            "Filter by Gender",
            options=available_genders,
            default=default_selected_genders,
            help="Select one or more provider genders.",
            label_visibility="collapsed",
        )
    else:
        selected_genders = []
        st.info("ℹ️ No gender information available.")

st.divider()

# Search summary card
if street and city and state and zipcode and selected_specialties:
    summary_text = f"📍 {street}, {city}, {state} {zipcode} | 🏥 {len(selected_specialties)} specialty/ies | 📏 {max_radius_miles}mi | 👥 {preset_choice}"
    st.info(summary_text)
else:
    st.warning("⚠️ Please fill in address and select at least one specialty to search.")

# Prominent search button
col_btn1, col_btn2, col_btn3 = resp_columns([2, 1, 2])
with col_btn2:
    search_clicked = st.button("🔍 Find Providers", type="primary", width="stretch")

if search_clicked:
    # Clear cached results from any previous search
    st.session_state.pop("last_best", None)
    st.session_state.pop("last_scored_df", None)

    # Construct full address from current form values
    state_for_addr = state or ""
    full_address = f"{street}, {city}, {state_for_addr} {zipcode}".strip(", ")

    # Validate address
    addr_valid, addr_msg = validate_address_input(street, city, state_for_addr, zipcode)
    if not addr_valid:
        st.error("⚠️ Please fix the following address issues:")
        if addr_msg:
            st.info(addr_msg)
        st.stop()

    if not GEOCODE_AVAILABLE or geocode_address_with_cache is None:
        st.error("❌ Geocoding service unavailable. Please contact support.")
        st.info("Technical note: geopy package is not installed")
        st.stop()

    with st.spinner("🌍 Looking up address coordinates..."):
        coords = geocode_address_with_cache(full_address)

    if not coords:
        st.error("❌ Unable to find the address. Please check and try again.")
        st.info(f"Tried to geocode: {full_address}")
        st.stop()

    user_lat, user_lon = coords
    st.session_state.update(
        {
            "street": street,
            "city": city,
            "state": state or "",
            "zipcode": zipcode,
            "user_lat": float(user_lat),
            "user_lon": float(user_lon),
            "alpha": float(alpha),
            "beta": float(beta),
            "distance_weight": float(distance_weight),
            "client_weight": float(client_weight),
            "max_radius_miles": int(max_radius_miles),
            "selected_specialties": selected_specialties,
            "selected_genders": selected_genders,
        }
    )

    with st.spinner("🔍 Searching for providers..."):
        st.switch_page("pages/2_📄_Results.py")

st.divider()

# Results preview
with st.expander("📄 What You'll See", expanded=False):
    st.markdown("""
    **Search results show a ranked list of providers with:**
    - **Provider Name** — The healthcare provider's full name
    - **Distance** — Miles from the client's address
    - **Clients Served** — Number of clients this provider has worked with
    - **Specialty** — Type of healthcare provider (e.g., Cardiologist, Therapist)
    - **Gender** — Provider's gender identity

    Providers are ranked by your chosen search profile:
    - *Prioritize Proximity*: Closest providers first
    - *Balanced*: Mix of distance and experience
    - *Prioritize Experience*: Most experienced providers first
    """)

# Help section at bottom
with st.expander("❓ Need Help?"):
    st.markdown(
        """
    **How to use this search:**
    1. Enter the client's complete address
    2. Choose a search profile or customize your own weights
    3. (Optional) Set advanced filters to refine results
    4. Click "Find Providers" to see recommendations

    **Tips:**
    - Use "Balanced (Recommended)" for most situations
    - "Prioritize Proximity" is best for clients with mobility concerns
    - "Prioritize Experience" helps find providers with more case history
    - Advanced filters help narrow results for specific needs

    For more information, visit the [How It Works](/10_🛠️_How_It_Works) page.
    """
    )

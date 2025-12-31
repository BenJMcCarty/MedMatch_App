import datetime as dt

import streamlit as st

from app import show_auto_update_status
from src.app_logic import get_unique_specialties, load_application_data
from src.utils.addressing import validate_address_input
from src.utils.responsive import resp_columns

try:
    from src.utils.geocoding import geocode_address_with_cache

    GEOCODE_AVAILABLE = True
except Exception:
    geocode_address_with_cache = None
    GEOCODE_AVAILABLE = False

# Constants - define once at module level for performance
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

st.set_page_config(page_title="Provider Recommender", page_icon="🏥", layout="wide")

# Show data loading status if available
show_auto_update_status()

# Hero section - welcoming landing page
st.title("🏥 Provider Recommender")
st.markdown("Find the right healthcare provider for your client — quickly and confidently!")

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

# Cache the column check to avoid repeated lookups
has_inbound = ("Inbound Referral Count" in provider_df.columns) if not provider_df.empty else False

st.divider()

# Address input section with improved layout
st.subheader("📍 Client Address")

# Toggle for using test address as default
use_test_address = st.checkbox(
    "Use test address as default",
    value=st.session_state.get("use_test_address", False),
    help=("Check this box to pre-fill the form with a test address")
)

# Store the checkbox state in session
st.session_state["use_test_address"] = use_test_address

# Set defaults based on checkbox state
if use_test_address:
    default_street = ""
    default_city = ""
    default_state = None
    default_zipcode = ""
else:
    default_street = ""
    default_city = ""
    default_state = None
    default_zipcode = ""

col1, col2 = resp_columns([1, 1])

# Cache session state lookups - use firm defaults if checkbox is checked, otherwise use previous values or empty
prev_street = st.session_state.get("street", default_street) or default_street
prev_city = st.session_state.get("city", default_city) or default_city

with col1:
    street = str(st.text_input("Street Address", prev_street, help="Enter the client's street address"))
with col2:
    city = str(st.text_input("City", prev_city, help="Enter the client's city"))


col3, col4 = resp_columns([1, 1])

# Cache session state lookups
prev_state = st.session_state.get("state", default_state)
prev_zipcode = st.session_state.get("zipcode", default_zipcode) or default_zipcode

with col3:
    # Calculate default index once
    default_index = US_STATES.index(prev_state) if prev_state in US_STATES else 0

    state = st.selectbox(
        "State", options=US_STATES, index=default_index, help="Select the client's state (2-letter abbreviation)"
    )

    # Ensure state is an uppercase string or None
    state = state.upper() if isinstance(state, str) else None

with col4:
    zipcode = str(st.text_input("ZIP Code", prev_zipcode, help="5-digit ZIP code"))

# Quick search presets
st.divider()
st.subheader("🎯 Search Preferences")

preset_choice = st.radio(
    "Choose a search profile:",
    ["Prioritize Proximity (Recommended)", "Balanced", "Prioritize Referrals", "Custom Settings"],
    horizontal=True,
    help="Select a preset to automatically configure search weights, or choose Custom to set your own",
)

# Set weights based on preset - use conditional assignment to minimize branching
if preset_choice == "Prioritize Proximity (Recommended)":
    distance_weight = 0.7
    outbound_weight = 0.2
    inbound_weight = 0.05 if has_inbound else 0.0
    preferred_weight = 0.05
elif preset_choice == "Balanced":
    distance_weight = 0.4
    outbound_weight = 0.4
    inbound_weight = 0.1 if has_inbound else 0.0
    preferred_weight = 0.1
elif preset_choice == "Prioritize Referrals":
    distance_weight = 0.2
    outbound_weight = 0.6
    inbound_weight = 0.1 if has_inbound else 0.0
    preferred_weight = 0.1
else:  # Custom Settings
    # Cache default values to avoid repeated session state lookups
    default_distance = 0.4 if has_inbound else 0.6
    default_outbound = 0.0
    default_inbound = 0.2
    default_preferred = 0.1

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
        outbound_weight = st.slider(
            "📊 Outbound Referral Importance",
            0.0,
            1.0,
            st.session_state.get("outbound_weight", default_outbound),
            0.05,
            help="Higher values favor providers with MORE outbound referrals (more experienced)",
        )
        if has_inbound:
            inbound_weight = st.slider(
                "🤝 Inbound Referral Importance",
                0.0,
                1.0,
                st.session_state.get("inbound_weight", default_inbound),
                0.05,
                help="Higher values favor providers with MORE inbound referrals (refer more cases to us)",
            )
        else:
            inbound_weight = 0.0
        preferred_weight = st.slider(
            "⭐ Preferred Provider Importance",
            0.0,
            1.0,
            st.session_state.get("preferred_weight", default_preferred),
            0.05,
            help="Higher values favor designated preferred providers",
        )

# Calculate normalized weights - only compute once
total = distance_weight + outbound_weight + inbound_weight + preferred_weight
if total == 0:
    st.error("⚠️ At least one weight must be greater than 0. Please adjust your settings.")
    alpha = beta = gamma = pref_norm = 0.0
else:
    alpha = distance_weight / total
    beta = outbound_weight / total
    gamma = inbound_weight / total if has_inbound else 0.0
    pref_norm = preferred_weight / total

# Show normalized weights in a more visual way
if preset_choice == "Custom Settings":
    with st.expander("📊 View Normalized Weights"):
        st.caption("Your settings automatically adjusted to total 100%:")
        cols = st.columns(4 if has_inbound else 3)
        cols[0].metric("Distance", f"{alpha*100:.0f}%")
        cols[1].metric("Outbound", f"{beta*100:.0f}%")
        if has_inbound:
            cols[2].metric("Inbound", f"{gamma*100:.0f}%")
            cols[3].metric("Preferred", f"{pref_norm*100:.0f}%")
        else:
            cols[2].metric("Preferred", f"{pref_norm*100:.0f}%")

# Advanced filters in collapsible section
with st.expander("⚙️ Advanced Filters (Optional)"):
    st.caption("Set additional criteria to refine your search results.")

    # Cache session state lookups and compute defaults once
    default_time_period = [dt.date.today() - dt.timedelta(days=365), dt.date.today()]

    max_radius_miles = st.slider(
        "Maximum Distance (miles)",
        1,
        200,
        st.session_state.get("max_radius_miles", 25),
        5,
        help="Only show providers within this distance",
    )

    min_referrals = st.number_input(
        "Minimum Experience (referral count)",
        0,
        100,
        value=st.session_state.get("min_referrals", 0),
        help="Require providers to have handled at least this many cases",
    )

    col_time1, col_time2 = resp_columns([3, 1])
    with col_time1:
        time_period = st.date_input(
            "Referral Time Period",
            value=st.session_state.get("time_period", default_time_period),
            help="Consider only referrals within this date range",
        )
    with col_time2:
        use_time_filter = st.checkbox(
            "Enable", value=st.session_state.get("use_time_filter", True), help="Apply time period filter"
        )

    # Specialty filter
    st.caption("**Provider Specialties**")
    available_specialties = get_unique_specialties(provider_df)

    if available_specialties:
        # Get previously selected specialties from session state, default to all
        default_selected = st.session_state.get("selected_specialties", available_specialties)

        selected_specialties = st.multiselect(
            "Filter by Specialty",
            options=available_specialties,
            default=default_selected,
            help="Select one or more provider specialties. Leave all selected to include all providers.",
        )
    else:
        selected_specialties = []
        st.info("ℹ️ No specialty information available in provider data.")

    # Gender filter
    st.caption("**Provider Gender**")
    available_genders = []
    if 'Gender' in provider_df.columns:
        available_genders = sorted([g for g in provider_df['Gender'].dropna().unique() if str(g).strip()])
    
    if available_genders:
        default_genders = st.session_state.get("selected_genders", available_genders)
        selected_genders = st.multiselect(
            "Filter by Gender",
            options=available_genders,
            default=default_genders,
            help="Select one or more genders. Leave all selected to include all providers.",
        )
    else:
        selected_genders = []
        st.info("ℹ️ No gender information available in provider data.")

st.divider()

# Prominent search button
col_btn1, col_btn2, col_btn3 = resp_columns([2, 1, 2])
with col_btn2:
    search_clicked = st.button("🔍 Find Providers", type="primary", width="stretch")

if search_clicked:
    # Clear cached results from any previous search
    st.session_state.pop("last_best", None)
    st.session_state.pop("last_scored_df", None)

    # Construct full address from current form values. Use empty string when state is None
    state_for_addr = state or ""
    full_address = f"{street}, {city}, {state_for_addr} {zipcode}".strip(", ")

    # Validate address (validation expects strings, so pass empty string when state is None)
    addr_valid, addr_msg = validate_address_input(street, city, state_for_addr, zipcode)
    if not addr_valid:
        st.error("⚠️ Please fix the following address issues:")
        if addr_msg:
            st.info(addr_msg)
        st.stop()

    # Check geocoding availability (already checked at import)
    if not GEOCODE_AVAILABLE or geocode_address_with_cache is None:
        st.error("❌ Geocoding service unavailable. Please contact support.")
        st.info("Technical note: geopy package is not installed")
        st.stop()

    # Geocode the address
    with st.spinner("🌍 Looking up address coordinates..."):
        coords = geocode_address_with_cache(full_address)

    if not coords:
        st.error("❌ Unable to find the address. Please check and try again.")
        st.info(f"Tried to geocode: {full_address}")
        st.stop()

    # Success! Store search parameters in a single batch update
    user_lat, user_lon = coords
    st.session_state.update(
        {
            "street": street,
            "city": city,
            "state": state or "",  # store empty string for backward compatibility
            "zipcode": zipcode,
            "user_lat": float(user_lat),
            "user_lon": float(user_lon),
            "alpha": float(alpha),
            "beta": float(beta),
            "gamma": float(gamma),
            "preferred_weight": float(preferred_weight),
            "preferred_norm": float(pref_norm),
            "distance_weight": float(distance_weight),
            "outbound_weight": float(outbound_weight),
            "inbound_weight": float(inbound_weight),
            "min_referrals": int(min_referrals),
            "time_period": time_period,
            "use_time_filter": bool(use_time_filter),
            "max_radius_miles": int(max_radius_miles),
            "selected_specialties": selected_specialties,
            "selected_genders": selected_genders,
        }
    )

    # Navigate to results
    with st.spinner("🔍 Searching for providers..."):
        st.switch_page("pages/2_📄_Results.py")

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
    - "Balance Workload" helps distribute cases fairly among providers
    - Advanced filters help narrow results for specific needs

    For more information, visit the [How It Works](/10_🛠️_How_It_Works) page.
    """
    )

import pandas as pd
import streamlit as st

try:
    import pydeck as pdk
    PYDECK_AVAILABLE = True
except ImportError:
    PYDECK_AVAILABLE = False

from src.app_logic import apply_time_filtering, load_application_data, run_recommendation, validate_provider_data
from src.utils.io_utils import format_phone_number, get_word_bytes, sanitize_filename
from src.utils.responsive import resp_columns
from src.utils.freshness import format_last_verified_display


st.set_page_config(page_title="Results", page_icon=":bar_chart:", layout="wide")

# Sidebar navigation
if st.sidebar.button("← New Search", type="secondary", width="stretch"):
    st.switch_page("pages/1_🔎_Search.py")

st.sidebar.divider()
st.sidebar.caption("**Your Search Criteria:**")
if "max_radius_miles" in st.session_state:
    st.sidebar.write(f"📍 Radius: {st.session_state['max_radius_miles']} miles")
if "min_clients" in st.session_state:
    st.sidebar.write(f"📊 Min. Clients: {st.session_state['min_clients']} cases")
if "selected_specialties" in st.session_state and st.session_state["selected_specialties"]:
    specialties_str = ", ".join(st.session_state["selected_specialties"])
    st.sidebar.write(f"🏥 Specialties: {specialties_str}")
if "selected_genders" in st.session_state and st.session_state["selected_genders"]:
    genders_str = ", ".join(st.session_state["selected_genders"])
    st.sidebar.write(f"👤 Genders: {genders_str}")
if "street" in st.session_state and "city" in st.session_state:
    st.sidebar.write(f"🏠 From: {st.session_state.get('city', 'N/A')}, {st.session_state.get('state', 'N/A')}")

required_keys = ["user_lat", "user_lon", "alpha", "beta", "min_clients", "max_radius_miles"]
if any(k not in st.session_state for k in required_keys):
    st.warning("No search parameters found. Redirecting to search.")
    st.switch_page("pages/1_🔎_Search.py")

try:
    provider_df, detailed_referrals_df = load_application_data()
except Exception as e:
    st.error("❌ Failed to load provider data. Please return to the search page and try again.")
    st.info(f"Technical details: {str(e)}")
    if st.button("← Back to Search"):
        st.switch_page("pages/1_🔎_Search.py")
    st.stop()

if provider_df.empty:
    st.error("❌ No provider data available.")
    st.info("💡 Please upload data using the 'Update Data' page or contact support.")
    if st.button("← Back to Search"):
        st.switch_page("pages/1_🔎_Search.py")
    st.stop()

if (
    st.session_state.get("use_time_filter")
    and isinstance(st.session_state.get("time_period"), list)
    and len(st.session_state["time_period"]) == 2
):
    start_date, end_date = st.session_state["time_period"]
    try:
        provider_df = apply_time_filtering(provider_df, detailed_referrals_df, start_date, end_date)
    except Exception as e:
        st.warning(f"⚠️ Failed to apply time filtering. Using all available data. Details: {str(e)}")

valid, msg = validate_provider_data(provider_df)
if not valid and msg:
    # st.warning(msg)
    pass

best = st.session_state.get("last_best")
scored_df = st.session_state.get("last_scored_df")

if best is None or scored_df is None or (isinstance(scored_df, pd.DataFrame) and scored_df.empty):
    try:
        best, scored_df = run_recommendation(
            provider_df,
            st.session_state["user_lat"],
            st.session_state["user_lon"],
            min_clients=st.session_state["min_clients"],
            max_radius_miles=st.session_state["max_radius_miles"],
            alpha=st.session_state["alpha"],
            beta=st.session_state["beta"],
            selected_specialties=st.session_state.get("selected_specialties"),
            selected_genders=st.session_state.get("selected_genders"),
        )
        st.session_state["last_best"] = best
        st.session_state["last_scored_df"] = scored_df
    except Exception as e:
        st.error("❌ Failed to calculate recommendations.")
        st.info(f"Technical details: {str(e)}")
        if st.button("← Back to Search"):
            st.switch_page("pages/1_🔎_Search.py")
        st.stop()

st.title("🎯 Provider Recommendations")

if best is None or scored_df is None or (isinstance(scored_df, pd.DataFrame) and scored_df.empty):
    st.warning("⚠️ No providers matched your search criteria.")
    st.info("💡 Try adjusting your filters or expanding the search radius.")
    st.stop()

# Top recommendation in a prominent card
st.subheader("✨ Best Match")

provider_name = best.get("Full Name", "Unknown Provider") if isinstance(best, pd.Series) else "Unknown Provider"

# Create a nice card-like display for the top provider
with st.container():
    col1, col2 = resp_columns([2, 1])

    with col1:
        st.markdown(f"### 🧑‍⚕️ {provider_name}")

        if isinstance(best, pd.Series):
            # Display key information
            info_items = []

            if "Full Address" in best and best["Full Address"]:
                info_items.append(("🏥 Address", best["Full Address"]))

            # Find phone number
            phone_value = None
            for phone_key in ["Work Phone Number", "Work Phone", "Phone Number", "Phone 1"]:
                candidate = best.get(phone_key)
                if candidate:
                    phone_value = format_phone_number(candidate)
                    break
            if phone_value:
                info_items.append(("📞 Phone", phone_value))

            if "Specialty" in best and best["Specialty"]:
                info_items.append(("🩺 Specialty", best["Specialty"]))

            if "Distance (Miles)" in best:
                info_items.append(("📍 Distance", f"{best['Distance (Miles)']:.1f} miles"))

            if "Client Count" in best:
                info_items.append(("📊 Cases Handled", int(best["Client Count"])))

            if "Last Verified Date" in best and pd.notna(best["Last Verified Date"]):
                formatted_date = format_last_verified_display(best["Last Verified Date"])
                info_items.append(("📅 Last Verified", formatted_date))

            # Display in a clean format
            for label, value in info_items:
                st.write(f"**{label}:** {value}")

    with col2:
        # Key metrics
        if isinstance(best, pd.Series):
            if "Score" in best:
                st.metric("Match Score", f"{best['Score']:.3f}", help="Higher scores indicate better matches")

st.divider()

# Export button in a prominent position
try:
    base_filename = f"Provider_{sanitize_filename(provider_name)}"
    st.download_button(
        "📄 Export to Word Document",
        data=get_word_bytes(best),
        file_name=f"{base_filename}.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        use_container_width=False,
        type="primary",
    )
except Exception as e:
    st.error(f"❌ Export failed: {e}")

st.divider()

# All results in a clean table
st.subheader("📋 All Matching Providers")

cols = ["Full Name", "Work Phone Number", "Full Address"]
if "Specialty" in scored_df.columns:
    cols.append("Specialty")
cols.extend(["Distance (Miles)", "Client Count"])
if "Last Verified Date" in scored_df.columns:
    cols.append("Last Verified Date")
if "Score" in scored_df.columns:
    cols.append("Score")
available = [c for c in cols if c in scored_df.columns]

if available:
    sort_col = "Score" if "Score" in available else available[0]
    sort_order = False if "Score" in available else True  # Score: descending, others: ascending
    display_df = (
        scored_df[available]
        .drop_duplicates(subset=["Full Name"], keep="first")
        .sort_values(by=sort_col, ascending=sort_order)
        .reset_index(drop=True)
        .copy()  # Ensure we have a copy to modify
    )

    # Format phone numbers - handle all possible phone field names
    phone_fields = ["Work Phone Number", "Work Phone", "Phone Number", "Phone 1"]
    for phone_field in phone_fields:
        if phone_field in display_df.columns:
            display_df[phone_field] = display_df[phone_field].apply(format_phone_number)

    # Format Last Verified Date with freshness indicator
    if "Last Verified Date" in display_df.columns:
        display_df["Last Verified Date"] = display_df["Last Verified Date"].apply(
            lambda x: format_last_verified_display(x, include_age=False)
        )

    # Round distance to 1 decimal place for cleaner display
    if "Distance (Miles)" in display_df.columns:
        display_df["Distance (Miles)"] = display_df["Distance (Miles)"].round(1)

    # Round score to 3 decimal places
    if "Score" in display_df.columns:
        display_df["Score"] = display_df["Score"].round(3)

    display_df.insert(0, "Rank", range(1, len(display_df) + 1))

    st.caption(f"Showing {len(display_df)} provider(s) matching your criteria")
    st.dataframe(display_df, hide_index=True, width="stretch", height=400)
else:
    st.error("❌ No displayable columns in results.")

st.divider()

# Map visualization
st.subheader("🗺️ Provider Locations")

# Prepare map data - filter to only providers with valid coordinates
map_data = scored_df[scored_df['Latitude'].notna() & scored_df['Longitude'].notna()].copy()

if not map_data.empty and PYDECK_AVAILABLE:
    # Prepare provider locations for the map
    map_data['lat'] = pd.to_numeric(map_data['Latitude'], errors='coerce')
    map_data['lon'] = pd.to_numeric(map_data['Longitude'], errors='coerce')
    
    # Remove any remaining invalid coordinates
    map_data = map_data.dropna(subset=['lat', 'lon'])
    
    if not map_data.empty:
        # Create tooltip-friendly column names (pydeck doesn't like spaces/parentheses)
        map_data['provider_name'] = map_data['Full Name'] if 'Full Name' in map_data.columns else 'Unknown'
        map_data['distance_miles'] = map_data['Distance (Miles)'].round(1) if 'Distance (Miles)' in map_data.columns else 0
        map_data['match_score'] = map_data['Score'].round(3) if 'Score' in map_data.columns else 0
        map_data['specialty'] = map_data['Specialty'] if 'Specialty' in map_data.columns else 'N/A'
        
        # Create user location data
        user_location = pd.DataFrame({
            'lat': [st.session_state['user_lat']],
            'lon': [st.session_state['user_lon']],
            'provider_name': ['Your Location'],
            'color': [[255, 0, 0, 200]]  # Red for user location
        })
        
        # Add color coding for providers based on rank/score
        # Top 3 providers get special colors, rest are blue
        colors = []
        for idx in range(len(map_data)):
            if idx == 0:
                colors.append([34, 139, 34, 200])  # Top: Green
            elif idx == 1:
                colors.append([255, 215, 0, 200])  # Second: Gold
            elif idx == 2:
                colors.append([255, 140, 0, 200])  # Third: Dark orange
            else:
                colors.append([100, 149, 237, 180])  # Others: Cornflower blue
        map_data['color'] = colors
        
        # Set up the view centered on user location
        view_state = pdk.ViewState(
            latitude=st.session_state['user_lat'],
            longitude=st.session_state['user_lon'],
            zoom=10,
            pitch=0,
        )
        
        # Create provider layer
        provider_layer = pdk.Layer(
            'ScatterplotLayer',
            data=map_data,
            get_position='[lon, lat]',
            get_color='color',
            get_radius=300,
            pickable=True,
            auto_highlight=True,
        )
        
        # Create user location layer
        user_layer = pdk.Layer(
            'ScatterplotLayer',
            data=user_location,
            get_position='[lon, lat]',
            get_color='color',
            get_radius=400,
            pickable=True,
        )
        
        # Create the deck
        deck = pdk.Deck(
            layers=[provider_layer, user_layer],
            initial_view_state=view_state,
            tooltip={
                'html': '<b>{provider_name}</b><br/>{specialty}<br/>Distance: {distance_miles} miles<br/>Score: {match_score}',
                'style': {
                    'backgroundColor': 'steelblue',
                    'color': 'white'
                }
            }
        )
        
        st.pydeck_chart(deck)
        
        # Legend
        st.caption("🔴 Your Location | 🟢 Best Match | 🟡 2nd Best | 🟠 3rd Best | 🔵 Other Providers")
    else:
        st.info("ℹ️ No providers with valid coordinates to display on map.")
elif not map_data.empty:
    # Fallback to simple st.map if pydeck not available
    st.info("💡 Install pydeck for an enhanced interactive map: `pip install pydeck`")
    simple_map_data = map_data[['Latitude', 'Longitude']].rename(columns={'Latitude': 'lat', 'Longitude': 'lon'})
    st.map(simple_map_data)
else:
    st.info("ℹ️ No providers with valid coordinates to display on map.")

st.divider()

# Scoring details in expander at the bottom
with st.expander("📊 How Scoring Works"):
    alpha = st.session_state.get("alpha", 0.5)
    beta = st.session_state.get("beta", 0.5)

    st.markdown(
        """
    **Scoring Formula:**

    Providers are scored using a weighted combination of factors. **Higher scores indicate better matches.**
    """
    )

    formula_parts = [f"**Distance** × {alpha:.2f}", f"**Client Count** × {beta:.2f}"]

    st.markdown("Score = " + " + ".join(formula_parts))

    st.markdown(
        """
    **What this means:**
    - Each factor is normalized to a 0-1 scale
    - Weights are automatically adjusted to total 100%
    - The provider with the highest score is your best match
    """
    )

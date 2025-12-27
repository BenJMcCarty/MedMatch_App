import streamlit as st

st.set_page_config(page_title="Quick Start Guide", page_icon="👟", layout="wide")

st.title("🚀 Quick Start Guide - Provider Recommendations")

st.success("### 🔎 Ready to find the right provider?")

st.markdown(
        """
### 1. Go to Search Page
   - Enter your client's full address
   - System will geocode the location

#### 2. Configure Preferences
   - Adjust importance sliders based on scenario
   - Set minimum referral threshold (experience level)
   - Set maximum search radius (miles)

### 3. Execute Search
   - Click "Find Providers" button
   - System filters and scores all providers
   - Results load in <1 second
"""
    )

st.markdown('---')

st.warning("### 📋 Interpreting Your Results")

st.markdown(
        """
### 1. Review Top Recommendation
- See best-match provider with full contact details
- Review distance, referral counts, score

### 2. Analyze Full Rankings
- Browse complete provider list sorted by score
- Use available export options to download results
- View providers on interactive map

### 3. Refine if Needed
- Adjust weights and re-search
- Try different scenarios
- Compare results side-by-side
"""
    )

st.markdown('---')

st.info("## 📚 Additional Resources")

st.markdown(
    """
- **📊 Data Dashboard**: Explore provider workload trends, referral patterns, and data quality metrics
- **🔄 Update Data**: Refresh provider database with latest Filevine exports
- **🏠 Home**: Project overview and navigation guide
- **💾 Export Options**: Download search results for record-keeping and sharing

**Questions or need help?** Contact the Data Operations team for support and training.
"""
)

st.success(
    """💡 **Pro Tip**: Start with the **Data Dashboard** to understand current provider capacity "
    and referral patterns before searching!"""
)

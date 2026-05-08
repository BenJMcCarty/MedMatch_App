---
name: Search Page Redesign for POC Demo
description: Streamline Search.py with progressive disclosure, preset addresses, and preview cards to create a clean demo experience for stakeholders
type: specification
date: 2026-05-08
---

# MedMatch Search Page Redesign

## Purpose
Redesign the provider search page to present functionality cleanly with minimal friction for a proof-of-concept demo to stakeholders. Goal: make the "happy path" obvious while keeping all power features accessible.

## Key Principles
- **Progressive Disclosure**: Show only essential inputs (address + specialty + distance + profile). Hide custom weights and gender by default.
- **Demo-Friendly**: Add quick preset addresses and stats to showcase data depth without requiring user input.
- **Validation Through Preview**: Show users what results look like before committing to a search.

---

## Layout & Component Organization

### 1. Hero Section
- Keep existing title and subheader unchanged
- Maintains welcoming tone: "🏥 MedMatch Provider Recommender" + "Find the right healthcare provider..."

### 2. Stats Banner (NEW)
- Positioned after hero, before address section
- Display: "📊 **X providers available** in your area" (total count from dataset)
- Calculate on page load; update if filters change
- Purpose: Shows data depth at a glance; reassures demo audience

### 3. Address Input Section
- Keep existing layout (responsive 2-column grid)
- Keep "Use test address as default" checkbox
- Add (NEW): Quick preset address buttons
  - 2-3 buttons like "📍 Use Baltimore Example" or "📍 Rural MD Example"
  - Pre-fills form with sample addresses for quick testing
  - Positioned right below address inputs
  - Clicking a preset immediately fills all address fields

### 4. Search Profile Selection (REDESIGNED)
- Replace radio buttons with styled button group (3 options always visible):
  - "🎯 Prioritize Proximity" (recommended)
  - "⚖️ Balanced"
  - "⭐ Prioritize Experience"
- Add small "⚙️ Customize" button that expands inline custom weights panel
- Custom weights section stays collapsed by default
- When custom preset selected, show normalized % display inline

### 5. Core Search Filters (Surfaced)
Two key filters users specify before search:
- **Specialty**: Multiselect dropdown (unchanged from current)
- **Distance Radius**: Number input, 0-200 miles (surfaced from Advanced)

### 6. Advanced Filters (Collapsed by Default)
Single collapsible "Advanced Filters" section containing:
- Gender filter (multiselect)
- Custom weights viewer (when custom preset active)
- Test address checkbox (moved from top)

### 7. Search Summary Card (NEW)
Before search button, show a compact confirmation card displaying:
```
📍 [Address] | 🏥 [Specialty Count] | 📏 [Distance]mi | 👥 [Profile Name]
```
Purpose: Users confirm their choices before commit; builds confidence.

### 8. Search Button
Prominent primary button: "🔍 Find Providers"

### 9. Results Preview Card (NEW)
Before or after help section, add a collapsible section:
**"📄 What You'll See"**
- Shows example result card with fields: provider name, distance, client count, specialty, gender
- Explains what each field means briefly
- Reassures users about output format before searching

### 10. Help Section
Keep existing "Need Help?" expander at bottom (unchanged)

---

## Data & Logic

### Stats Banner
- On page load: Query provider_df to get total count
- Display: `len(provider_df)` 
- Update dynamically if any filters change (specialty, gender, distance radius)
- Show real-time filtered count if Advanced Filters expanded

### Preset Addresses
Define 2-3 sample addresses in constants:
```python
PRESET_ADDRESSES = {
    "Baltimore": {"street": "100 N Charles St", "city": "Baltimore", "state": "MD", "zipcode": "21201"},
    "Rural Eastern Shore": {"street": "8222 Spadderdock Way", "city": "Russett", "state": "MD", "zipcode": "20724"},
    "Montgomery County": {"street": "12500 Parklawn Dr", "city": "Rockville", "state": "MD", "zipcode": "20852"},
}
```
- Clicking preset button sets session state and auto-fills form fields

### Results Preview
Mock example showing result structure (can be hardcoded or pull first real result from filtered data)

---

## Results Page Integration

### Results Summary Header
Add matching summary bar at top of Results page:
```
Search: 📍 [Address] | 🏥 [Specialty] | 📏 [Distance]mi | 👥 [Profile] | ✏️ Modify Search
```
Purpose: Reinforces user choices; "Modify Search" link goes back to Search page with state preserved.

---

## Removed Elements
- **Min Clients filter**: Removed entirely (not part of POC scope)
- **Radio button group**: Replaced with button group
- **Status quo normalize weights display**: Kept only if custom preset active

---

## Success Criteria
✅ Happy path (address → specialty → distance → search) takes ≤30 seconds without clicking advanced options  
✅ All original functionality remains accessible  
✅ Page feels uncluttered and demo-ready  
✅ Stats and presets showcase data depth without requiring user input  
✅ Results page clearly shows search parameters  
✅ No breaking changes to backend logic or data flow  

---

## Technical Notes
- Use existing session state patterns for preset form filling
- Reuse resp_columns utility for responsive layout
- Keep all validation logic unchanged
- No changes to geocoding or provider matching algorithm
- CSS/styling: leverage Streamlit's built-in components; minimal custom CSS needed

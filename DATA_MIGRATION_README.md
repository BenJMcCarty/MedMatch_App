# MedMatch Data Migration Guide

## Quick Start

### 1. Create Sample Data (for testing)
```bash
python create_sample_data.py
```

### 2. Verify Data Format
```bash
python verify_data_format.py
```

### 3. Run the Application
```bash
streamlit run app.py
```

## What Changed

### Data Source
- **Old**: Multiple S3 bucket files with auto-sync
- **New**: Single local parquet file: `data/processed/Combined_Contacts_and_Reviews.parquet`

### Column Names
| Old Name | New Name | Description |
|----------|----------|-------------|
| N/A | Provider First Name | Provider's first name |
| N/A | Provider Last Name | Provider's last name |
| N/A | gndr | Gender (M/F) |
| N/A | pri_spec | Primary specialty |
| N/A | Full Address | Complete address |
| N/A | Telephone Number | Phone number |
| N/A | latitude | Latitude coordinate |
| N/A | longitude | Longitude coordinate |
| N/A | patient_count | Number of patients (used as referral count) |
| N/A | star_value | Rating (1.0-5.0) |

### New Features
- **Gender Filter**: Filter providers by gender in search
- **Rating Display**: See provider ratings in results
- **Combined Filters**: Use gender + specialty filters together

## Data Requirements

Your parquet file must include these columns:
- `Provider First Name`, `Provider Last Name` (combined into Full Name)
- `gndr` (gender)
- `pri_spec` (specialty)
- `Full Address`
- `Telephone Number`
- `latitude`, `longitude` (numeric coordinates)
- `patient_count` (numeric, used as referral count)
- `star_value` (numeric rating)

## Migration Checklist

- [ ] Create/export data with new column names
- [ ] Save as `data/processed/Combined_Contacts_and_Reviews.parquet`
- [ ] Run `verify_data_format.py` to check format
- [ ] Clear app cache (Update Data page → Clear cache)
- [ ] Test search with gender filter
- [ ] Test search with specialty filter
- [ ] Verify ratings display correctly

## Troubleshooting

### "File not found" error
- Ensure file is at `data/processed/Combined_Contacts_and_Reviews.parquet`
- Check file permissions

### "Missing required columns" error
- Run `verify_data_format.py` to see which columns are missing
- Verify column names match exactly (case-sensitive)

### Gender/Specialty filters not working
- Check that `gndr` and `pri_spec` columns exist
- Verify data is not all null in these columns

### No results found
- Try expanding search radius
- Check that coordinates are valid (latitude: -90 to 90, longitude: -180 to 180)
- Verify `patient_count` values are >= minimum referrals filter

## Support

For detailed technical changes, see `MIGRATION_SUMMARY.md`.

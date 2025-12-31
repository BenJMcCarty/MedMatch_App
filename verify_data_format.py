"""
Test script to verify Combined_Contacts_and_Reviews.parquet has correct column names.

This script checks that the parquet file exists and contains all required columns.
Run this before starting the Streamlit app to verify data integrity.

Usage:
    python verify_data_format.py
"""

import sys
from pathlib import Path

try:
    import pandas as pd
except ImportError:
    print("ERROR: pandas not installed. Install with: pip install pandas pyarrow")
    sys.exit(1)

# Define expected columns
REQUIRED_COLUMNS = {
    'Provider First Name': 'string',
    'Provider Last Name': 'string',
    'gndr': 'string',
    'pri_spec': 'string',
    'Full Address': 'string',
    'Telephone Number': 'string',
    'latitude': 'numeric',
    'longitude': 'numeric',
    'patient_count': 'numeric',
    'star_value': 'numeric',
}

def verify_data_file():
    """Verify the parquet file exists and has correct structure."""
    
    data_file = Path("data/processed/Combined_Contacts_and_Reviews.parquet")
    
    # Check if file exists
    if not data_file.exists():
        print(f"❌ ERROR: File not found: {data_file}")
        print(f"   Please create the file at this location with the required columns.")
        return False
    
    print(f"✓ Found data file: {data_file}")
    
    # Load the file
    try:
        df = pd.read_parquet(data_file)
        print(f"✓ Successfully loaded parquet file ({len(df)} rows)")
    except Exception as e:
        print(f"❌ ERROR: Failed to load parquet file: {e}")
        return False
    
    # Check for required columns
    missing_columns = []
    for col in REQUIRED_COLUMNS.keys():
        if col not in df.columns:
            missing_columns.append(col)
    
    if missing_columns:
        print(f"\n❌ ERROR: Missing required columns:")
        for col in missing_columns:
            print(f"   - {col}")
        print(f"\nAvailable columns in file:")
        for col in df.columns:
            print(f"   - {col}")
        return False
    
    print(f"✓ All required columns present")
    
    # Verify data types
    print("\nColumn Data Type Verification:")
    type_errors = []
    
    for col, expected_type in REQUIRED_COLUMNS.items():
        actual_type = df[col].dtype
        
        if expected_type == 'numeric':
            if not pd.api.types.is_numeric_dtype(actual_type):
                type_errors.append(f"  ❌ {col}: Expected numeric, got {actual_type}")
            else:
                print(f"  ✓ {col}: {actual_type}")
        else:
            # For string columns, we're lenient (object dtype is acceptable)
            print(f"  ✓ {col}: {actual_type}")
    
    if type_errors:
        print("\nData type issues found:")
        for error in type_errors:
            print(error)
        print("\nNote: These might not prevent the app from working,")
        print("but data transformations may be needed.")
    
    # Show sample data
    print(f"\nSample Data (first 3 rows):")
    sample_cols = ['Provider First Name', 'Provider Last Name', 'gndr', 'pri_spec', 
                   'patient_count', 'star_value']
    available_sample_cols = [c for c in sample_cols if c in df.columns]
    print(df[available_sample_cols].head(3).to_string())
    
    # Check for null values in critical columns
    print(f"\nNull Value Check:")
    critical_cols = ['Provider First Name', 'Provider Last Name', 'latitude', 
                    'longitude', 'patient_count']
    null_counts = {}
    for col in critical_cols:
        if col in df.columns:
            null_count = df[col].isnull().sum()
            null_counts[col] = null_count
            status = "⚠️" if null_count > 0 else "✓"
            print(f"  {status} {col}: {null_count} nulls ({null_count/len(df)*100:.1f}%)")
    
    # Summary
    print("\n" + "="*60)
    if not missing_columns and not type_errors:
        print("✅ SUCCESS: Data file is correctly formatted!")
        print("   You can now run the Streamlit app.")
        return True
    else:
        print("⚠️  WARNING: Data file has some issues.")
        print("   The app may still work, but you should fix the issues above.")
        return False

if __name__ == "__main__":
    print("MedMatch Data Validation Script")
    print("="*60)
    success = verify_data_file()
    sys.exit(0 if success else 1)

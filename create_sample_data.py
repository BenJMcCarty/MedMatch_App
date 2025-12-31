"""
Create sample test data for MedMatch application.

This script creates a sample Combined_Contacts_and_Reviews.parquet file
with realistic test data for development and testing purposes.

Usage:
    python create_sample_data.py
"""

import pandas as pd
from pathlib import Path

def create_sample_data():
    """Create sample provider data with all required columns."""
    
    # Sample data with realistic values
    sample_data = {
        'Provider First Name': [
            'John', 'Jane', 'Robert', 'Maria', 'David',
            'Sarah', 'Michael', 'Lisa', 'James', 'Emily'
        ],
        'Provider Last Name': [
            'Smith', 'Johnson', 'Williams', 'Garcia', 'Rodriguez',
            'Martinez', 'Davis', 'Anderson', 'Wilson', 'Taylor'
        ],
        'gndr': [
            'M', 'F', 'M', 'F', 'M',
            'F', 'M', 'F', 'M', 'F'
        ],
        'pri_spec': [
            'Cardiology', 'Neurology', 'Orthopedics', 'Pediatrics', 'Cardiology',
            'Dermatology', 'Internal Medicine', 'Neurology', 'Orthopedics', 'Family Medicine'
        ],
        'Full Address': [
            '123 Main St, Baltimore, MD 21201',
            '456 Oak Ave, Baltimore, MD 21202',
            '789 Pine Rd, Baltimore, MD 21203',
            '321 Elm St, Baltimore, MD 21204',
            '654 Maple Dr, Baltimore, MD 21205',
            '987 Cedar Ln, Baltimore, MD 21206',
            '147 Birch Ct, Baltimore, MD 21207',
            '258 Spruce Way, Baltimore, MD 21208',
            '369 Willow Rd, Baltimore, MD 21209',
            '741 Ash Blvd, Baltimore, MD 21210'
        ],
        'Telephone Number': [
            '4105551234', '4105555678', '4105559012', '4105553456', '4105557890',
            '4105551111', '4105552222', '4105553333', '4105554444', '4105555555'
        ],
        'latitude': [
            39.290, 39.300, 39.310, 39.320, 39.330,
            39.340, 39.350, 39.360, 39.370, 39.380
        ],
        'longitude': [
            -76.610, -76.620, -76.630, -76.640, -76.650,
            -76.660, -76.670, -76.680, -76.690, -76.700
        ],
        'patient_count': [
            50, 75, 30, 60, 45,
            55, 80, 40, 65, 70
        ],
        'star_value': [
            4.5, 4.8, 4.2, 4.6, 4.4,
            4.7, 4.9, 4.3, 4.5, 4.6
        ]
    }
    
    # Create DataFrame
    df = pd.DataFrame(sample_data)
    
    # Ensure output directory exists
    output_dir = Path('data/processed')
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save to parquet
    output_file = output_dir / 'Combined_Contacts_and_Reviews.parquet'
    df.to_parquet(output_file, index=False, engine='pyarrow')
    
    print(f"✅ Created sample data file: {output_file}")
    print(f"   Records: {len(df)}")
    print(f"   Columns: {', '.join(df.columns)}")
    print(f"\nSample preview:")
    print(df.head(3)[['Provider First Name', 'Provider Last Name', 'gndr', 'pri_spec', 'patient_count', 'star_value']].to_string())
    print(f"\nYou can now run the Streamlit app with: streamlit run app.py")

if __name__ == "__main__":
    try:
        import pyarrow
        print("MedMatch Sample Data Generator")
        print("="*60)
        create_sample_data()
    except ImportError:
        print("ERROR: pyarrow not installed.")
        print("Install with: pip install pyarrow")
        import sys
        sys.exit(1)

"""Validation utilities for addresses, coordinates, and phone numbers.

Small, self-contained helpers used across the application and tests.
"""

import re
from typing import Tuple


def validate_address_input(street: str, city: str, state: str, zipcode: str) -> Tuple[bool, str]:
    """
    Validate address components for completeness and basic format.

    Args:
        street: Street address
        city: City name
        state: State abbreviation or name
        zipcode: ZIP code

    Returns:
        Tuple of (is_valid, error_message)
    """
    issues = []

    # Check required fields
    if not street or not street.strip():
        issues.append("Street address is required")
    if not city or not city.strip():
        issues.append("City is required")
    if not state or not state.strip():
        issues.append("State is required")
    if not zipcode or not zipcode.strip():
        issues.append("ZIP code is required")

    # Basic format validation
    if zipcode and not re.match(r"^\d{5}(-\d{4})?$", zipcode.strip()):
        issues.append("ZIP code must be in format 12345 or 12345-6789")

    if issues:
        return False, "; ".join(issues)
    return True, "Valid address"


def validate_coordinates(lat: float, lon: float) -> Tuple[bool, str]:
    """
    Validate latitude and longitude coordinates.

    Args:
        lat: Latitude value
        lon: Longitude value

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        return False, "Coordinates must be numeric"

    if not (-90 <= lat <= 90):
        return False, "Latitude must be between -90 and 90"

    if not (-180 <= lon <= 180):
        return False, "Longitude must be between -180 and 180"

    return True, "Valid coordinates"


def validate_phone_number(phone: str) -> Tuple[bool, str]:
    """
    Validate phone number format.

    Args:
        phone: Phone number string

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not phone or not phone.strip():
        return True, "Phone number is optional"

    # Remove common formatting
    cleaned = re.sub(r"[^\d]", "", phone)

    if len(cleaned) == 10:
        return True, "Valid phone number"
    elif len(cleaned) == 11 and cleaned.startswith("1"):
        return True, "Valid phone number"
    else:
        return False, "Phone number must be 10 digits or 11 digits starting with 1"

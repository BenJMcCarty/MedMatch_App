"""Address and coordinate validation helpers."""
import re
from typing import Tuple


def validate_address(address: str) -> Tuple[bool, str]:
    if not address or not address.strip():
        return False, "Address cannot be empty"

    addr = address.strip()
    if len(addr) < 10:
        return False, "Address appears too short. Please provide a complete address."

    if not any(ch.isdigit() for ch in addr):
        return False, "Address should include a street number"

    state_patterns = ["\\b[A-Z]{2}\\b", "\\d{5}(-\\d{4})?\\b"]
    has_state_or_zip = any(re.search(p, addr) for p in state_patterns)
    if not has_state_or_zip:
        return True, "Consider adding state and ZIP code for better accuracy"

    return True, ""


def validate_address_input(street: str, city: str, state: str, zipcode: str) -> Tuple[bool, str]:
    errors = []
    warnings = []

    if not street or not street.strip():
        errors.append("Street address is required")
    if not city or not city.strip():
        warnings.append("City is recommended for better geocoding accuracy")
    if not state or not state.strip():
        warnings.append("State is recommended for better geocoding accuracy")

    if state and state.strip():
        state_clean = state.strip().upper()
        valid_states = {
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
            "MD",
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
        }
        if len(state_clean) == 2 and state_clean not in valid_states:
            warnings.append(f"'{state}' may not be a valid US state abbreviation")
        elif len(state_clean) > 2:
            warnings.append("Consider using 2-letter state abbreviation (e.g., 'MD' instead of 'Maryland')")

    if zipcode and zipcode.strip():
        z = zipcode.strip()
        if not (z.isdigit() and len(z) == 5) and not (
            len(z) == 10 and z[5] == "-" and z[:5].isdigit() and z[6:].isdigit()
        ):
            warnings.append("ZIP code should be 5 digits (e.g., '20746') or ZIP+4 format (e.g., '20746-1234')")

    if street and street.strip().lower() in ["test", "example", "123 test st", "123 main st"]:
        warnings.append("Address appears to be a test value - please enter a real address")

    message_parts = []
    if errors:
        message_parts.append("❌ **Errors**: " + "; ".join(errors))
    if warnings:
        message_parts.append("⚠️ **Suggestions**: " + "; ".join(warnings))

    is_valid = len(errors) == 0
    message = "\n\n".join(message_parts) if message_parts else ""
    return is_valid, message


def validate_coordinates(lat: float, lon: float) -> Tuple[bool, str]:
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        return False, "Coordinates must be numeric"
    if not (-90 <= lat <= 90):
        return False, "Latitude must be between -90 and 90"
    if not (-180 <= lon <= 180):
        return False, "Longitude must be between -180 and 180"
    return True, "Valid coordinates"


def validate_phone_number(phone: str) -> Tuple[bool, str]:
    if not phone or not phone.strip():
        return True, "Phone number is optional"
    cleaned = re.sub(r"[^\d]", "", phone)
    if len(cleaned) == 10:
        return True, "Valid phone number"
    if len(cleaned) == 11 and cleaned.startswith("1"):
        return True, "Valid phone number"
    return False, "Phone number must be 10 digits or 11 digits starting with 1"

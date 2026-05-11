import pytest
from src.components.search_assistant import (
    _apply_filters, _build_confirmation,
    _is_city_state_only, _profile_to_weights,
)

SPECIALTIES = ["Cardiology", "Internal Medicine", "Psychiatry"]
GENDERS = ["M", "F"]


def test_apply_filters_sets_specialty():
    state = {}
    _apply_filters(
        {"specialty": "Cardiology", "gender": None, "radius": None, "profile_choice": None},
        SPECIALTIES, GENDERS, state,
    )
    assert state["selected_specialties"] == ["Cardiology"]


def test_apply_filters_ignores_unknown_specialty():
    state = {}
    _apply_filters(
        {"specialty": "Unknown Specialty", "gender": None, "radius": None, "profile_choice": None},
        SPECIALTIES, GENDERS, state,
    )
    assert "selected_specialties" not in state


def test_apply_filters_sets_gender():
    state = {}
    _apply_filters(
        {"specialty": None, "gender": "F", "radius": None, "profile_choice": None},
        SPECIALTIES, GENDERS, state,
    )
    assert state["selected_genders"] == ["F"]


def test_apply_filters_ignores_unknown_gender():
    state = {}
    _apply_filters(
        {"specialty": None, "gender": "X", "radius": None, "profile_choice": None},
        SPECIALTIES, GENDERS, state,
    )
    assert "selected_genders" not in state


def test_apply_filters_sets_radius():
    state = {}
    _apply_filters(
        {"specialty": None, "gender": None, "radius": 50, "profile_choice": None},
        SPECIALTIES, GENDERS, state,
    )
    assert state["max_radius_miles"] == 50


def test_apply_filters_ignores_out_of_range_radius():
    state = {}
    _apply_filters(
        {"specialty": None, "gender": None, "radius": 500, "profile_choice": None},
        SPECIALTIES, GENDERS, state,
    )
    assert "max_radius_miles" not in state


def test_apply_filters_sets_profile_choice():
    state = {}
    _apply_filters(
        {"specialty": None, "gender": None, "radius": None, "profile_choice": "Balanced"},
        SPECIALTIES, GENDERS, state,
    )
    assert state["profile_choice"] == "Balanced"


def test_apply_filters_ignores_invalid_profile_choice():
    state = {}
    _apply_filters(
        {"specialty": None, "gender": None, "radius": None, "profile_choice": "Made Up"},
        SPECIALTIES, GENDERS, state,
    )
    assert "profile_choice" not in state


def test_apply_filters_sets_multiple_fields():
    state = {}
    _apply_filters(
        {"specialty": "Psychiatry", "gender": "M", "radius": 10, "profile_choice": "Prioritize Proximity (Recommended)"},
        SPECIALTIES, GENDERS, state,
    )
    assert state["selected_specialties"] == ["Psychiatry"]
    assert state["selected_genders"] == ["M"]
    assert state["max_radius_miles"] == 10
    assert state["profile_choice"] == "Prioritize Proximity (Recommended)"


def test_apply_filters_does_not_touch_unspecified_keys():
    state = {"selected_specialties": ["Internal Medicine"]}
    _apply_filters(
        {"specialty": None, "gender": "F", "radius": None, "profile_choice": None},
        SPECIALTIES, GENDERS, state,
    )
    assert state["selected_specialties"] == ["Internal Medicine"]


def test_build_confirmation_all_fields():
    result = _build_confirmation(
        {"specialty": "Cardiology", "gender": "F", "radius": 25, "profile_choice": "Balanced"}
    )
    assert result == "Searching for: Cardiology · Female · 25 mi · Balanced"


def test_build_confirmation_specialty_only():
    result = _build_confirmation(
        {"specialty": "Psychiatry", "gender": None, "radius": None, "profile_choice": None}
    )
    assert result == "Searching for: Psychiatry"


def test_build_confirmation_no_fields():
    result = _build_confirmation(
        {"specialty": None, "gender": None, "radius": None, "profile_choice": None}
    )
    assert result == "Searching for: your criteria"


def test_build_confirmation_male_gender_label():
    result = _build_confirmation(
        {"specialty": None, "gender": "M", "radius": None, "profile_choice": None}
    )
    assert result == "Searching for: Male"


def test_build_confirmation_unknown_gender_passthrough():
    result = _build_confirmation(
        {"specialty": None, "gender": "NB", "radius": None, "profile_choice": None}
    )
    assert result == "Searching for: NB"


def test_apply_filters_writes_lat_lon_when_provided():
    state = {}
    _apply_filters(
        {"specialty": None, "gender": None, "radius": None, "profile_choice": None},
        SPECIALTIES, GENDERS, state,
        user_lat=39.2904, user_lon=-76.6122,
    )
    assert state["user_lat"] == pytest.approx(39.2904)
    assert state["user_lon"] == pytest.approx(-76.6122)


def test_apply_filters_does_not_write_lat_lon_when_absent():
    state = {}
    _apply_filters(
        {"specialty": None, "gender": None, "radius": None, "profile_choice": None},
        SPECIALTIES, GENDERS, state,
    )
    assert "user_lat" not in state
    assert "user_lon" not in state


def test_apply_filters_ignores_partial_lat_lon():
    state = {}
    _apply_filters(
        {"specialty": None, "gender": None, "radius": None, "profile_choice": None},
        SPECIALTIES, GENDERS, state,
        user_lat=39.2904, user_lon=None,
    )
    assert "user_lat" not in state
    assert "user_lon" not in state


def test_is_city_state_only_returns_true_for_city_state():
    assert _is_city_state_only("Baltimore, MD") is True


def test_is_city_state_only_returns_true_for_state_only():
    assert _is_city_state_only("Maryland") is True


def test_is_city_state_only_returns_false_for_street_address():
    assert _is_city_state_only("100 N Charles St, Baltimore, MD") is False


def test_is_city_state_only_returns_false_for_zip_code():
    assert _is_city_state_only("21201") is False


def test_profile_to_weights_proximity():
    alpha, beta = _profile_to_weights("Prioritize Proximity (Recommended)")
    assert alpha == pytest.approx(1.0)
    assert beta == pytest.approx(0.0)


def test_profile_to_weights_balanced():
    alpha, beta = _profile_to_weights("Balanced")
    assert alpha == pytest.approx(0.5)
    assert beta == pytest.approx(0.5)


def test_profile_to_weights_experience():
    alpha, beta = _profile_to_weights("Prioritize Experience")
    assert alpha == pytest.approx(0.3)
    assert beta == pytest.approx(0.7)


def test_profile_to_weights_unknown_defaults_to_balanced():
    alpha, beta = _profile_to_weights(None)
    assert alpha == pytest.approx(0.5)
    assert beta == pytest.approx(0.5)


def test_profile_to_weights_custom_defaults_to_balanced():
    alpha, beta = _profile_to_weights("Custom Settings")
    assert alpha == pytest.approx(0.5)
    assert beta == pytest.approx(0.5)

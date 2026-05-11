import numpy as np
import pandas as pd
import pytest

from src.utils.scoring import _rank_normalize


def test_rank_normalize_distance_lower_is_better():
    """Closest provider (lowest distance) gets score 1.0."""
    values = np.array([1.0, 5.0, 10.0])
    result = _rank_normalize(values, higher_is_better=False)
    assert result[0] == pytest.approx(1.0)
    assert result[1] == pytest.approx(0.5)
    assert result[2] == pytest.approx(0.0)


def test_rank_normalize_clients_higher_is_better():
    """Provider with most clients gets score 1.0."""
    values = np.array([0.0, 5.0, 20.0])
    result = _rank_normalize(values, higher_is_better=True)
    assert result[0] == pytest.approx(0.0)
    assert result[1] == pytest.approx(0.5)
    assert result[2] == pytest.approx(1.0)


def test_rank_normalize_single_provider_scores_one():
    result = _rank_normalize(np.array([42.0]), higher_is_better=True)
    assert result[0] == pytest.approx(1.0)


def test_rank_normalize_outlier_does_not_compress_others():
    """An outlier 1000 miles away should not compress nearby providers' scores."""
    values = np.array([1.0, 2.0, 3.0, 1000.0])
    result = _rank_normalize(values, higher_is_better=False)
    # Scores should be distinct and well-spread, not all near 1.0
    assert result[0] == pytest.approx(1.0)
    assert result[1] == pytest.approx(2 / 3)
    assert result[2] == pytest.approx(1 / 3)
    assert result[3] == pytest.approx(0.0)


def test_rank_normalize_ties_get_average_rank():
    """Tied values receive the average of the ranks they span."""
    values = np.array([1.0, 1.0, 3.0])
    result = _rank_normalize(values, higher_is_better=True)
    # ranks from scipy: [1.5, 1.5, 3] → normalized (higher=better): [(1.5-1)/2, (1.5-1)/2, (3-1)/2]
    assert result[0] == pytest.approx(0.25)
    assert result[1] == pytest.approx(0.25)
    assert result[2] == pytest.approx(1.0)


from src.utils.scoring import recommend_provider


@pytest.fixture
def three_providers():
    return pd.DataFrame({
        "Full Name": ["Alice", "Bob", "Carol"],
        "Distance (Miles)": [1.0, 5.0, 10.0],
        "Client Count": [0, 5, 20],
    })


def test_closest_provider_wins_with_distance_only(three_providers):
    _, df = recommend_provider(
        three_providers, distance_weight=1.0, client_weight=0.0, specialty_weight=0.0
    )
    assert df.iloc[0]["Full Name"] == "Alice"


def test_most_experienced_wins_with_client_only(three_providers):
    _, df = recommend_provider(
        three_providers, distance_weight=0.0, client_weight=1.0, specialty_weight=0.0
    )
    assert df.iloc[0]["Full Name"] == "Carol"


def test_experience_floor_zero_client_provider(three_providers):
    """Zero-client provider should receive at least the experience_floor score."""
    _, df = recommend_provider(
        three_providers,
        distance_weight=0.0,
        client_weight=1.0,
        specialty_weight=0.0,
        experience_floor=0.25,
    )
    alice_score = df.loc[df["Full Name"] == "Alice", "Score"].iloc[0]
    assert alice_score >= 0.25


def test_rank_normalization_outlier_does_not_flatten_nearby_scores():
    """An outlier far provider should not collapse nearby providers to the same score."""
    df = pd.DataFrame({
        "Full Name": ["Alice", "Bob", "Carol", "Outlier"],
        "Distance (Miles)": [1.0, 2.0, 3.0, 500.0],
        "Client Count": [10, 10, 10, 10],
    })
    _, scored = recommend_provider(
        df, distance_weight=1.0, client_weight=0.0, specialty_weight=0.0
    )
    scores = scored.set_index("Full Name")["Score"]
    assert scores["Alice"] > scores["Bob"] > scores["Carol"]


def test_recommend_provider_returns_none_when_empty():
    empty = pd.DataFrame({"Full Name": [], "Distance (Miles)": [], "Client Count": []})
    best, scored = recommend_provider(empty)
    assert best is None
    assert scored is None


def test_best_is_first_row_of_scored_df(three_providers):
    best, scored = recommend_provider(
        three_providers, distance_weight=1.0, client_weight=0.0, specialty_weight=0.0
    )
    assert best["Full Name"] == scored.iloc[0]["Full Name"]

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

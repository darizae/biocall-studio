from __future__ import annotations

import numpy as np
import pytest

from alpaca_desktop.domain.rf_training import (
    evaluate_binary_probabilities,
    rf_feature_names,
    validate_rf_estimator_structure,
)
from alpaca_desktop.domain.run import MAX_MEASUREMENTS


def test_rf_feature_schema_is_exact_ordered_and_configuration_dependent():
    """Case: UT-TRAIN-002."""
    names = rf_feature_names(n_mfcc=2, include_deltas=True)

    assert names == (
        "Dur 90% (s)",
        "Dur 50% (s)",
        "Center Freq (Hz)",
        "Freq 5% (Hz)",
        "Freq 25% (Hz)",
        "Freq 75% (Hz)",
        "Freq 95% (Hz)",
        "BW 50% (Hz)",
        "BW 90% (Hz)",
        "Avg Entropy (bits)",
        "Agg Entropy (bits)",
        "mfcc1_mean",
        "mfcc1_std",
        "mfcc2_mean",
        "mfcc2_std",
        "d_mfcc1_mean",
        "d_mfcc1_std",
        "d_mfcc2_mean",
        "d_mfcc2_std",
        "dd_mfcc1_mean",
        "dd_mfcc1_std",
        "dd_mfcc2_mean",
        "dd_mfcc2_std",
    )
    assert rf_feature_names(n_mfcc=2, include_deltas=False) == names[:15]
    assert MAX_MEASUREMENTS >= len(rf_feature_names(n_mfcc=1000, include_deltas=True))


def test_rf_metrics_map_target_probability_column_and_keep_threshold_out_of_fit():
    """Case: UT-TRAIN-003."""
    labels = np.asarray([0, 1, 0, 1], dtype=np.int64)
    # Deliberately reversed class columns: target=1 is column zero.
    probabilities = np.asarray(
        [[0.20, 0.80], [0.90, 0.10], [0.40, 0.60], [0.70, 0.30]],
        dtype=np.float64,
    )

    result = evaluate_binary_probabilities(
        labels,
        probabilities,
        classes=np.asarray([1, 0], dtype=np.int64),
        threshold=0.60,
    )

    assert result.target_probability_column == 0
    assert result.predictions.tolist() == [0, 1, 0, 1]
    assert result.metrics["accuracy"] == {"value": 1.0, "reason": None}
    assert result.metrics["f1"] == {"value": 1.0, "reason": None}
    assert result.metrics["roc_auc"] == {"value": 1.0, "reason": None}

    no_positive_predictions = evaluate_binary_probabilities(
        labels,
        probabilities,
        classes=np.asarray([1, 0], dtype=np.int64),
        threshold=0.95,
    )
    assert no_positive_predictions.metrics["precision"]["value"] is None
    assert "No target predictions" in no_positive_predictions.metrics["precision"]["reason"]
    assert no_positive_predictions.metrics["roc_auc"] == {"value": 1.0, "reason": None}


class _Estimator:
    n_features_in_ = 3
    classes_ = np.asarray([0, 1], dtype=np.int64)
    feature_importances_ = np.asarray([0.2, 0.3, 0.5], dtype=np.float64)


def test_rf_estimator_structure_rejects_class_and_feature_mismatches():
    """Case: UT-TRAIN-006."""
    validate_rf_estimator_structure(
        _Estimator(),
        feature_names=("first", "second", "third"),
        probability_class_order=(0, 1),
    )

    bad_classes = _Estimator()
    bad_classes.classes_ = [np.asarray([0, 1]), np.asarray([0, 1])]
    with pytest.raises(ValueError, match="single-output"):
        validate_rf_estimator_structure(
            bad_classes,
            feature_names=("first", "second", "third"),
            probability_class_order=(0, 1),
        )

    bad_width = _Estimator()
    bad_width.n_features_in_ = 2
    with pytest.raises(ValueError, match="feature count"):
        validate_rf_estimator_structure(
            bad_width,
            feature_names=("first", "second", "third"),
            probability_class_order=(0, 1),
        )

    with pytest.raises(ValueError, match="probability class order"):
        validate_rf_estimator_structure(
            _Estimator(),
            feature_names=("first", "second", "third"),
            probability_class_order=(1, 0),
        )

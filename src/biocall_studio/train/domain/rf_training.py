"""Pure Random Forest feature, class-column, and validation metric rules."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

ROBUST_FEATURE_NAMES = (
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
)


def rf_feature_names(n_mfcc: int, include_deltas: bool) -> tuple[str, ...]:
    """Return the pipeline-compatible robust+MFCC schema in exact execution order."""
    if type(n_mfcc) is not int or n_mfcc < 1:
        raise ValueError("RF MFCC count must be a positive integer.")
    names = list(ROBUST_FEATURE_NAMES)
    for prefix in ("mfcc", "d_mfcc", "dd_mfcc"):
        if prefix != "mfcc" and not include_deltas:
            continue
        for coefficient in range(1, n_mfcc + 1):
            names.extend((f"{prefix}{coefficient}_mean", f"{prefix}{coefficient}_std"))
    return tuple(names)


def _binary_classes(classes: object) -> NDArray[np.int64]:
    if isinstance(classes, (str, bytes)):
        raise ValueError("RF estimator classes must be numeric binary classes.")
    try:
        array = np.asarray(classes)
    except (TypeError, ValueError) as exc:
        raise ValueError("RF estimator classes must be a single-output array.") from exc
    if array.ndim != 1:
        raise ValueError("RF estimator must be single-output binary classification.")
    if array.shape != (2,) or any(type(value.item()) is not int for value in array):
        raise ValueError("RF estimator must contain exactly the integer noise/target classes.")
    converted = array.astype(np.int64, copy=False)
    if set(converted.tolist()) != {0, 1}:
        raise ValueError("RF estimator must contain exactly the integer noise/target classes.")
    return converted


def validate_rf_estimator_structure(
    estimator: Any,
    *,
    feature_names: tuple[str, ...],
    probability_class_order: tuple[int, ...],
) -> None:
    """Validate fitted estimator width, classes, schema order, and importances."""
    if (
        not feature_names
        or len(feature_names) != len(set(feature_names))
        or any(not isinstance(name, str) or not name for name in feature_names)
    ):
        raise ValueError("RF ordered feature names are invalid.")
    classes = _binary_classes(getattr(estimator, "classes_", None))
    if tuple(classes.tolist()) != tuple(probability_class_order):
        raise ValueError("RF estimator probability class order disagrees with model metadata.")
    n_features = getattr(estimator, "n_features_in_", None)
    if type(n_features) is not int or n_features != len(feature_names):
        raise ValueError("RF estimator feature count disagrees with ordered feature metadata.")
    importances = np.asarray(getattr(estimator, "feature_importances_", None))
    if (
        importances.ndim != 1
        or importances.shape[0] != len(feature_names)
        or not np.isfinite(importances).all()
        or (importances < 0).any()
    ):
        raise ValueError("RF feature importances disagree with ordered feature metadata.")
    estimator_names = getattr(estimator, "feature_names_in_", None)
    if estimator_names is not None and tuple(map(str, estimator_names)) != feature_names:
        raise ValueError("RF estimator feature name order disagrees with model metadata.")


def _defined(value: float | None, reason: str | None = None) -> dict[str, float | str | None]:
    return {"value": value, "reason": reason}


def _roc_auc(labels: NDArray[np.int64], scores: NDArray[np.float64]) -> float | None:
    positive = scores[labels == 1]
    negative = scores[labels == 0]
    if not positive.size or not negative.size:
        return None
    greater = (positive[:, None] > negative[None, :]).sum()
    tied = (positive[:, None] == negative[None, :]).sum()
    return float((greater + 0.5 * tied) / (positive.size * negative.size))


@dataclass(frozen=True)
class RfEvaluation:
    target_probability_column: int
    predictions: NDArray[np.int64]
    metrics: dict[str, dict[str, float | str | None]]


def evaluate_binary_probabilities(
    labels: object,
    probabilities: object,
    *,
    classes: object,
    threshold: float,
) -> RfEvaluation:
    """Evaluate held-out RF probabilities using the explicit target-class column."""
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
        raise ValueError("RF decision threshold must be numeric.")
    threshold = float(threshold)
    if not math.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError("RF decision threshold must be from 0 to 1.")
    ordered_classes = _binary_classes(classes)
    target_column = int(np.flatnonzero(ordered_classes == 1)[0])
    actual = np.asarray(labels)
    scores = np.asarray(probabilities, dtype=np.float64)
    if (
        actual.ndim != 1
        or actual.size == 0
        or any(type(value.item()) is not int for value in actual)
        or not set(actual.astype(np.int64).tolist()).issubset({0, 1})
    ):
        raise ValueError("RF validation labels must be a one-dimensional binary target array.")
    if scores.shape != (actual.shape[0], 2) or not np.isfinite(scores).all():
        raise ValueError("RF validation probabilities must be finite two-column data.")
    actual = actual.astype(np.int64, copy=False)
    target_scores = scores[:, target_column]
    predicted = (target_scores >= threshold).astype(np.int64)
    true_positive = int(((actual == 1) & (predicted == 1)).sum())
    false_positive = int(((actual == 0) & (predicted == 1)).sum())
    false_negative = int(((actual == 1) & (predicted == 0)).sum())
    precision = (
        None
        if true_positive + false_positive == 0
        else true_positive / (true_positive + false_positive)
    )
    recall = (
        None
        if true_positive + false_negative == 0
        else true_positive / (true_positive + false_negative)
    )
    f1 = (
        None
        if precision is None or recall is None or precision + recall == 0
        else 2 * precision * recall / (precision + recall)
    )
    auc = _roc_auc(actual, target_scores)
    metrics = {
        "accuracy": _defined(float((actual == predicted).mean())),
        "precision": _defined(
            None if precision is None else float(precision),
            None if precision is not None else "No target predictions were produced.",
        ),
        "recall": _defined(
            None if recall is None else float(recall),
            None if recall is not None else "Validation contains no target examples.",
        ),
        "f1": _defined(
            None if f1 is None else float(f1),
            None if f1 is not None else "F1 is undefined without target true positives.",
        ),
        "roc_auc": _defined(
            auc,
            None if auc is not None else "Validation Split does not contain both classes.",
        ),
    }
    return RfEvaluation(target_column, predicted, metrics)

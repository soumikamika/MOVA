"""Shared feature-matrix hygiene for every trainer in this project (recommendation,
travel_time, travel_cost, ...).

Small or homogeneous training batches routinely produce feature columns with a
single distinct value (e.g. every example sharing one transport mode, or one
trip's context fields being literally constant). Some scikit-learn/numpy
version combinations raise
`ValueError: window shape cannot be larger than input array shape` deep inside
histogram-bin-threshold computation when a numeric column has fewer than two
distinct values (see Phase C's post-mortem). A column with fewer than two
distinct values also carries no information a tree-based splitter can use
regardless of library version, so dropping it is a correct simplification, not
a version-specific workaround.
"""
import numpy as np

# Below this many distinct (non-NaN) values, a column is dropped before fitting.
MIN_DISTINCT_VALUES = 2


def split_constant_columns(
    x: np.ndarray, feature_names: list[str],
) -> tuple[np.ndarray, list[str], list[str]]:
    """Drop columns with fewer than MIN_DISTINCT_VALUES distinct non-NaN values.

    Returns (x_reduced, kept_names, dropped_names), preserving column order.
    An all-NaN column has zero distinct values and is dropped the same way.
    """
    keep_mask = []
    for j in range(x.shape[1]):
        col = x[:, j]
        distinct = np.unique(col[~np.isnan(col)])
        keep_mask.append(len(distinct) >= MIN_DISTINCT_VALUES)
    kept = [n for n, k in zip(feature_names, keep_mask) if k]
    dropped = [n for n, k in zip(feature_names, keep_mask) if not k]
    return x[:, keep_mask], kept, dropped

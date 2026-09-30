"""Elementwise replica of Python's builtin ``sum()`` over floats (performance layer).

Since Python 3.12, ``sum()`` of floats is compensated (Neumaier's improved Kahan-Babuska
algorithm), so it is generally *not* bit-identical to a running ``+=`` or to numpy's
pairwise reductions. Batched kernels that replace ``sum(generator)`` must reproduce it
exactly to keep seeded output unchanged; :func:`python_sum_columns` does so elementwise
for a fixed, small number of terms (checked against the builtin in the test suite).
"""

from collections.abc import Sequence

import numpy as np

from madexplorer.core.types import FloatArray


def python_sum_columns(terms: Sequence[FloatArray]) -> FloatArray:
    """``[sum(t[i] for t in terms) for i]`` with CPython's float semantics, vectorized.

    ``sum()`` starts from the integer 0: the first float term is added to it (so -0.0
    becomes 0.0), then each further term is accumulated with Neumaier compensation, and
    the compensation is added at the end when it is nonzero and finite.
    """
    if not terms:
        raise ValueError("at least one term is required")
    with np.errstate(over="ignore", invalid="ignore"):  # IEEE results, as in C
        total = 0.0 + np.asarray(terms[0], dtype=np.float64)
        compensation = np.zeros_like(total)
        for term in terms[1:]:
            x = np.asarray(term, dtype=np.float64)
            t = total + x
            compensation = compensation + np.where(
                np.abs(total) >= np.abs(x), (total - t) + x, (x - t) + total
            )
            total = t
        apply = (compensation != 0.0) & np.isfinite(compensation)
        result: FloatArray = np.where(apply, total + compensation, total)
    return result

"""Fusion-born knowledge heterogeneity (MVP 3 Stage 5F). NOT ACTIVE.

Design: ``objective/MVP3_SOCIOECONOMIC_STRATA_DESIGN.md`` §Y. Counterfactual only: no
simulator path calls this module, it registers no model rule, and its parameters are not
scenario settings. Authoritative knowledge, crop output and strata are unchanged.

The authoritative fusion replaces two knowledge vectors by their population-weighted mean
(``lifecycle.merge_units``). The shadow keeps, instead, a distribution of one domain's level
over *knowledge components*: ``(w, k)`` with mixture weights ``w`` (population shares,
summing to 1) and levels ``k``. A component is an inherited historical knowledge position,
not a stratum, an occupation or a person; it carries no stratum id.

- **Common environment (primary).** Every component sees the unit's own year: learning
  ``k <- (1 - lam) k + g`` with the unit's gain ``g`` (the authoritative gain does not depend
  on ``k``), then additive diffusion and innovation increments. Because the update is
  affine with a common slope, the weighted mean follows the authoritative level exactly
  and deviations from it shrink by ``(1 - lam)`` a year whatever the practice.
- **Fusion:** concatenate, reweight by pre-fusion populations (:func:`fuse`).
- **Fission:** representative; the daughter copies the distribution (expected value).
- **Pooling sensitivities:** pooled teaching of new workers (:func:`turnover_pool`, new
  workers learn the unit mean), full pooling (:func:`pool`).
- **Resolution:** exact compaction and greedy capacity coalescence with a K, slope-weighted
  or exact-efficiency distance (:func:`coalesce`); a merge keeps the weighted mean.

``E(k) = k / (k + h)`` is concave for ``k >= 0``, so ``E(mean k) >= mean E(k)``
(:func:`jensen_gap`). The gap is a static aggregation diagnostic, not a production error:
it equals lost output only if output is the participation-weighted sum of each
participant's own efficiency.
"""

from typing import Literal

import numpy as np

Metric = Literal["k", "slope", "e"]


def efficiency(k: np.ndarray | float, half: float) -> np.ndarray | float:
    """Practical efficiency ``k / (k + half)`` (``KnowledgeModel.efficiency``)."""
    return k / (k + half)


def slope(k: np.ndarray | float, half: float) -> np.ndarray | float:
    """``dE/dk = half / (k + half)^2``."""
    return half / (k + half) ** 2


def _check(w: np.ndarray, k: np.ndarray) -> None:
    if w.shape != k.shape or w.ndim != 1 or w.size == 0:
        raise ValueError("weights and levels must be equal-length nonempty vectors")
    if (w <= 0).any() or (k < 0).any():
        raise ValueError("weights must be positive and levels nonnegative")
    if abs(float(w.sum()) - 1.0) > 1e-9:
        raise ValueError(f"weights must sum to 1, got {float(w.sum())!r}")


def mean(w: np.ndarray, k: np.ndarray) -> float:
    """Weighted mean level (what the authoritative unit holds)."""
    return float(np.dot(w, k))


def variance(w: np.ndarray, k: np.ndarray) -> float:
    """Weighted variance of levels: the information averaging removes (beyond the mean)."""
    m = mean(w, k)
    return float(np.dot(w, (k - m) ** 2))


def jensen_gap(w: np.ndarray, k: np.ndarray, half: float) -> float:
    """``E(mean k) - mean E(k) >= 0`` (concavity of ``E`` on ``k >= 0``)."""
    _check(w, k)
    return float(efficiency(mean(w, k), half)) - float(np.dot(w, efficiency(k, half)))


def fuse(parts: list[tuple[np.ndarray, np.ndarray, float]]) -> tuple[np.ndarray, np.ndarray]:
    """Concatenate ``(w, k, population)`` parts; weights by pre-fusion population. The
    weighted mean is the authoritative ``(N_A K_A + N_B K_B) / (N_A + N_B)``."""
    total = sum(n for _, _, n in parts)
    if not total > 0:
        raise ValueError("fusion needs a positive total population")
    w = np.concatenate([wp * (n / total) for wp, _, n in parts])
    k = np.concatenate([kp for _, kp, _ in parts])
    keep = w > 0
    return w[keep] / w[keep].sum(), k[keep]


def learn(k: np.ndarray, decay: float, gain: float) -> np.ndarray:
    """One year of practice learning in the unit's common environment: ``(1 - decay) k + gain``
    (``learning.learn`` with ``decay = delta / retention`` and the unit's K-free gain)."""
    if not 0.0 <= decay <= 1.0 or gain < 0.0:
        raise ValueError("decay must be in [0, 1] and gain nonnegative")
    return np.asarray((1.0 - decay) * k + gain)


def turnover_pool(w: np.ndarray, k: np.ndarray, entering: float) -> np.ndarray:
    """New workers (a share ``entering`` of every component) learn the unit mean: each
    component's level moves that share of the way to the mean. The mean is unchanged."""
    if not 0.0 <= entering <= 1.0:
        raise ValueError("entering must be in [0, 1]")
    return np.asarray((1.0 - entering) * k + entering * mean(w, k))


def pool(w: np.ndarray, k: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Immediate pooling: one component at the mean (the authoritative representation)."""
    return np.ones(1), np.array([mean(w, k)])


def compact_exact(w: np.ndarray, k: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Merge components at bit-identical levels (lossless); canonical order by level."""
    levels, inverse = np.unique(k, return_inverse=True)
    weights = np.zeros(levels.size)
    np.add.at(weights, inverse, w)
    return weights, levels


def distance(k1: float, k2: float, w1: float, w2: float, half: float, metric: Metric) -> float:
    """Distance between two components: plain ``|dk|``, slope-weighted
    ``|dk| E'(pair mean)``, or the exact ``|dE|``."""
    if metric == "k":
        return abs(k1 - k2)
    if metric == "slope":
        centre = (w1 * k1 + w2 * k2) / (w1 + w2)
        return abs(k1 - k2) * float(slope(centre, half))
    return abs(float(efficiency(k1, half)) - float(efficiency(k2, half)))


def coalesce(
    w: np.ndarray, k: np.ndarray, capacity: int, half: float, metric: Metric
) -> tuple[np.ndarray, np.ndarray]:
    """Greedy capacity coalescence (the production cost form, ``strata.py``): while above
    ``capacity``, merge the pair minimizing ``w_i w_j / (w_i + w_j) d^2`` into its weighted
    mean; ties keep the first pair in level order."""
    if capacity < 1:
        raise ValueError("capacity must be at least 1")
    wc, kc = compact_exact(w, k)
    ws: list[float] = wc.tolist()
    ks: list[float] = kc.tolist()
    while len(ks) > capacity:
        best, pair = np.inf, (0, 1)
        for i in range(len(ks) - 1):
            for j in range(i + 1, len(ks)):
                d = distance(ks[i], ks[j], ws[i], ws[j], half, metric)
                cost = ws[i] * ws[j] / (ws[i] + ws[j]) * d * d
                if cost < best:
                    best, pair = cost, (i, j)
        i, j = pair
        total = ws[i] + ws[j]
        ks[i] = (ws[i] * ks[i] + ws[j] * ks[j]) / total
        ws[i] = total
        del ws[j], ks[j]
        order = np.argsort(ks, kind="stable").tolist()
        ws, ks = [ws[o] for o in order], [ks[o] for o in order]
    return np.array(ws), np.array(ks)


def summary(w: np.ndarray, k: np.ndarray, half: float) -> dict[str, float]:
    """Mean, dispersion and the pooled / separate efficiencies of a distribution."""
    _check(w, k)
    m = mean(w, k)
    e_sep = float(np.dot(w, efficiency(k, half)))
    e_pool = float(efficiency(m, half))
    e = efficiency(k, half)
    return {
        "mean": m,
        "sd": variance(w, k) ** 0.5,
        "range": float(k.max() - k.min()),
        "e_pooled": e_pool,
        "e_separate": e_sep,
        "jensen": e_pool - e_sep,
        "e_range": float(np.max(e) - np.min(e)),
        "e_sd": float(np.dot(w, (e - e_sep) ** 2)) ** 0.5,
    }

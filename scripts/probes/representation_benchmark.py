# The report tables keep one entry per line.
# ruff: noqa: E501
"""Statistical population representation (MVP 3 Stage 5G).

METHODOLOGICAL BENCHMARK — NOT A SOCIOLOGICAL MECHANISM.

The finite-population event is the production simulator's representative fission: every
member leaves independently with probability ``f`` (``groups.split_cohorts`` draws a
binomial per age/sex cohort). The attributes are hypothetical: each person may know an
activity (``K``) and have access to a resource (``A``); a group *can* perform the activity
when at least ``m`` members have both. Nothing in the simulator models ``K``, ``A`` or this
threshold. The benchmark asks only which statistical representations reproduce the outcome
of an explicit individual reference, and at what cost.

Representations of one unit:

- **R5 individual reference:** explicit people, one Bernoulli draw each.
- **R2 finite-count compartments:** integer counts ``n[k, a]``; fission draws a binomial
  per compartment. Same probability law as R5 (exact enumeration available).
- **R3 weighted mixture:** joint shares ``w[k, a]`` plus a head count; fission draws the head
  count binomially and copies the shares (the ``StrataTable`` expected-value convention).
- **R1/marginals:** head count plus independent marginals ``p_K, p_A``; capable count taken
  as ``N p_K p_A``.
- **R4 moments:** means and the second moment ``E[KA]``; the daughter's capable count
  approximated by a normal with the binomial mean and variance.

Usage:
    uv run python scripts/probes/representation_benchmark.py
"""

import math
import time
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

# ---------------------------------------------------------------- populations


def population(n: int, k: int, a: int, both: int) -> np.ndarray:
    """``(n, 2)`` boolean people: ``k`` know, ``a`` have access, ``both`` have both."""
    if not 0 <= both <= min(k, a) or k + a - both > n:
        raise ValueError("infeasible configuration")
    people = np.zeros((n, 2), dtype=bool)
    people[:both] = True
    people[both:k, 0] = True
    people[k : k + a - both, 1] = True
    return people


def compartments(people: np.ndarray) -> np.ndarray:
    """``n[k, a]`` counts (``(2, 2)`` int) of a boolean ``(n, 2)`` population."""
    counts = np.zeros((2, 2), dtype=np.int64)
    np.add.at(counts, (people[:, 0].astype(int), people[:, 1].astype(int)), 1)
    return counts


def marginals(counts: np.ndarray) -> tuple[int, float, float]:
    n = int(counts.sum())
    return n, counts[1].sum() / n, counts[:, 1].sum() / n


# ---------------------------------------------------------------- fission (one event)


def binom_pmf(n: int, p: float) -> np.ndarray:
    return np.array([math.comb(n, x) * p**x * (1 - p) ** (n - x) for x in range(n + 1)])


def exact_capable(counts: np.ndarray, f: float, m: int) -> dict[str, float]:
    """R2 exact enumeration: the daughter's capable count is Binomial(n11, f) and the
    parent keeps the rest; integers are conserved by construction."""
    c = int(counts[1, 1])
    pmf = binom_pmf(c, f)
    x = np.arange(c + 1)
    return {
        "mean": float((pmf * x).sum()),
        "var": float((pmf * x**2).sum() - (pmf * x).sum() ** 2),
        "p_daughter": float(pmf[x >= m].sum()),
        "p_both": float(pmf[(x >= m) & (c - x >= m)].sum()),
    }


def individual_capable(
    people: np.ndarray, f: float, m: int, reps: int, rng: np.random.Generator
) -> dict[str, float]:
    """R5 Monte Carlo: one Bernoulli per person per repetition."""
    capable = people[:, 0] & people[:, 1]
    leave = rng.random((reps, people.shape[0])) < f
    d = (leave & capable).sum(axis=1)
    p = capable.sum() - d
    return {
        "mean": float(d.mean()), "var": float(d.var()),
        "p_daughter": float((d >= m).mean()), "p_both": float(((d >= m) & (p >= m)).mean()),
    }  # fmt: skip


def compartment_capable(
    counts: np.ndarray, f: float, m: int, reps: int, rng: np.random.Generator
) -> dict[str, float]:
    """R2 Monte Carlo: one binomial per compartment (checks integer conservation)."""
    flat = counts.ravel()
    leave = rng.binomial(flat, f, size=(reps, flat.size))
    stay = flat - leave
    assert (stay >= 0).all() and (leave + stay == flat).all()
    d, p = leave[:, 3], stay[:, 3]
    return {
        "mean": float(d.mean()), "var": float(d.var()),
        "p_daughter": float((d >= m).mean()), "p_both": float(((d >= m) & (p >= m)).mean()),
    }  # fmt: skip


def mixture_capable(
    counts: np.ndarray, f: float, m: int, reps: int, rng: np.random.Generator
) -> dict[str, float]:
    """R3 expected-value fission: head count binomial, shares copied to both sides."""
    n = int(counts.sum())
    share = counts[1, 1] / n
    nd = rng.binomial(n, f, size=reps)
    d, p = nd * share, (n - nd) * share
    return {
        "mean": float(d.mean()), "var": float(d.var()),
        "p_daughter": float((d >= m).mean()), "p_both": float(((d >= m) & (p >= m)).mean()),
    }  # fmt: skip


def marginal_capable(
    counts: np.ndarray, f: float, m: int, reps: int, rng: np.random.Generator
) -> dict[str, float]:
    """Independent marginals: capable share ``p_K p_A``, otherwise as R3."""
    n, pk, pa = marginals(counts)
    nd = rng.binomial(n, f, size=reps)
    d, p = nd * pk * pa, (n - nd) * pk * pa
    return {
        "mean": float(d.mean()), "var": float(d.var()),
        "p_daughter": float((d >= m).mean()), "p_both": float(((d >= m) & (p >= m)).mean()),
    }  # fmt: skip


def moment_capable(counts: np.ndarray, f: float, m: int) -> dict[str, float]:
    """R4: mean and ``E[KA]`` give the capable count ``c = N E[KA]`` exactly; the split is
    approximated by Normal(f c, f (1 - f) c) with a continuity correction."""
    c = float(counts[1, 1])  # N * E[KA]
    mu, var = f * c, f * (1 - f) * c

    def cdf(x: float) -> float:
        if var == 0:
            return float(mu <= x)
        return 0.5 * (1 + math.erf((x - mu) / math.sqrt(2 * var)))

    # daughter >= m; both sides >= m  <=>  m <= x <= c - m (continuity-corrected)
    p_both = max(cdf(c - m + 0.5) - cdf(m - 0.5), 0.0) if c - m >= m else 0.0
    return {"mean": mu, "var": var, "p_daughter": 1 - cdf(m - 0.5), "p_both": p_both}


# ---------------------------------------------------------------- fusion (marginals lose correlation)


def fuse_counts(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return a + b


def marginal_fusion_capable(a: np.ndarray, b: np.ndarray) -> float:
    """Capable count a marginal representation predicts after fusing ``a`` and ``b``."""
    n, pk, pa = marginals(fuse_counts(a, b))
    return n * pk * pa


# ---------------------------------------------------------------- moments: three attributes


def triple_populations(m: int) -> tuple[np.ndarray, np.ndarray]:
    """Two ``(4m, 3)`` populations with identical marginals (1/2) and pairwise moments (1/4)
    but triple overlap 0 versus ``m``."""
    even = np.array([[0, 0, 0], [0, 1, 1], [1, 0, 1], [1, 1, 0]], dtype=bool)
    odd = np.array([[1, 1, 1], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=bool)
    return np.repeat(even, m, axis=0), np.repeat(odd, m, axis=0)


def moments(people: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    x = people.astype(float)
    return x.mean(axis=0), (x.T @ x) / x.shape[0]


# ---------------------------------------------------------------- approximate merging


@dataclass(frozen=True)
class Mixture:
    weight: np.ndarray  # people
    experience: np.ndarray  # years
    access: np.ndarray  # share with access in the component


def coalesce(mix: Mixture, size: int, distance: Callable[[Mixture, int, int], float]) -> Mixture:
    """Greedy merging (production cost form ``w_i w_j/(w_i+w_j) d^2``) into weighted means."""
    w, e, a = list(mix.weight), list(mix.experience), list(mix.access)
    while len(w) > size:
        best, pair = math.inf, (0, 1)
        cur = Mixture(np.array(w), np.array(e), np.array(a))
        for i in range(len(w) - 1):
            for j in range(i + 1, len(w)):
                d = distance(cur, i, j)
                cost = w[i] * w[j] / (w[i] + w[j]) * d * d
                if cost < best:
                    best, pair = cost, (i, j)
        i, j = pair
        t = w[i] + w[j]
        e[i] = (w[i] * e[i] + w[j] * e[j]) / t
        a[i] = (w[i] * a[i] + w[j] * a[j]) / t
        w[i] = t
        del w[j], e[j], a[j]
    return Mixture(np.array(w), np.array(e), np.array(a))


def equal_weight_distance(scale: float) -> Callable[[Mixture, int, int], float]:
    """Mechanism-agnostic: Euclidean over (experience / scale, access), like the production
    equal-weight metric over unrelated attributes."""
    return lambda x, i, j: math.hypot(
        (x.experience[i] - x.experience[j]) / scale, x.access[i] - x.access[j]
    )


def consequence_distance(threshold: float, scale: float) -> Callable[[Mixture, int, int], float]:
    """Consequence-aware: components on different sides of the capability boundary
    (experience >= threshold and access) are far apart; otherwise experience distance."""

    def d(x: Mixture, i: int, j: int) -> float:
        ci = float(x.experience[i] >= threshold) * x.access[i]
        cj = float(x.experience[j] >= threshold) * x.access[j]
        return 1e3 * abs(ci - cj) + abs(x.experience[i] - x.experience[j]) / scale

    return d


def partition_distance(threshold: float, scale: float) -> Callable[[Mixture, int, int], float]:
    """Merge only within one cell of the mechanism's decision partition (experience on the
    same side of the threshold, identical access); experience distance inside a cell. A
    weighted mean of members of one cell stays in that cell, so merging is exact for the
    capable count whenever the capacity covers the occupied cells."""

    def d(x: Mixture, i: int, j: int) -> float:
        same = (x.experience[i] >= threshold) == (x.experience[j] >= threshold) and x.access[
            i
        ] == x.access[j]
        return abs(x.experience[i] - x.experience[j]) / scale + (0.0 if same else 1e6)

    return d


def capable(mix: Mixture, threshold: float) -> float:
    """People able to perform the activity: experience at least ``threshold`` and access."""
    return float((mix.weight * (mix.experience >= threshold) * mix.access).sum())


# ---------------------------------------------------------------- report


def main() -> None:
    rng = np.random.default_rng(20261014)  # isolated stream; the simulator's RNG is untouched
    reps, f, m = 200_000, 0.4, 2
    print("METHODOLOGICAL BENCHMARK — NOT A SOCIOLOGICAL MECHANISM")
    print(
        f"event: representative fission (each member leaves with p = {f}); activity needs >= {m} members with K and A on a side\n"
    )
    print(
        "1. one fission event; quarter know K, quarter have A; configurations differ only in their overlap"
    )
    print("   N   overlap        rep            E[cap_d]  Var      P(daughter can)  P(both can)")
    for n in (20, 40, 80):
        k = a = n // 4
        for label, both in (("aligned", k), ("independent", round(k * a / n)), ("disjoint", 0)):
            counts = compartments(population(n, k, a, both))
            exact = exact_capable(counts, f, m)
            rows = {
                "R2 exact": exact,
                "R5 individuals": individual_capable(population(n, k, a, both), f, m, reps, rng),
                "R2 compartments": compartment_capable(counts, f, m, reps, rng),
                "R3 mixture (EV)": mixture_capable(counts, f, m, reps, rng),
                "marginals": marginal_capable(counts, f, m, reps, rng),
                "R4 moments": moment_capable(counts, f, m),
            }
            for rep, r in rows.items():
                print(
                    f"   {n:<3} {label:<11}({both:>2}) {rep:<15} {r['mean']:<9.3f} {r['var']:<8.3f} {r['p_daughter']:<16.4f} {r['p_both']:.4f}"
                )
        print()
    se = math.sqrt(0.25 / reps)
    print(f"   Monte Carlo standard error of a probability <= {se:.4f}\n")

    print(
        "2. fusion: unit 1 has 10 K-only people of 20, unit 2 has 10 A-only people of 20 (nobody has both)"
    )
    u1 = compartments(population(20, 10, 0, 0))
    u2 = compartments(population(20, 0, 10, 0))
    print(
        f"   capable after fusion: compartments {int(fuse_counts(u1, u2)[1, 1])}; mixture shares {int(fuse_counts(u1, u2)[1, 1])}; marginals {marginal_fusion_capable(u1, u2):.2f}\n"
    )

    print("3. moments beyond second order: activity needing three attributes")
    for mm in (5, 10, 20):
        p0, p1 = triple_populations(mm)
        m0, s0 = moments(p0)
        m1, s1 = moments(p1)
        print(f"   N = {4 * mm}: identical means {np.array_equal(m0, m1)} and second moments {np.array_equal(s0, s1)}; "
              f"capable (all three) {int(p0.all(axis=1).sum())} vs {int(p1.all(axis=1).sum())}")  # fmt: skip
    print()

    print(
        "4. approximate merging: N = 80 people, experience (years) and access; capable = experience >= 10 and access"
    )
    errs: dict[tuple[str, int], list[float]] = {}
    occupied: list[int] = []
    for trial in range(100):
        g = np.random.default_rng(1000 + trial)
        exp_ = np.concatenate([g.gamma(2.0, 3.0, 50), g.gamma(6.0, 2.5, 30)])
        acc = (g.random(80) < np.where(exp_ > 8, 0.6, 0.3)).astype(float)
        people = Mixture(np.ones(80), exp_, acc)
        truth = capable(people, 10.0)
        occupied.append(
            len({(bool(e >= 10.0), a) for e, a in zip(exp_.tolist(), acc.tolist(), strict=True)})
        )
        for size in (1, 2, 4, 8, 16, 32):
            for name, dist in (
                ("equal-weight", equal_weight_distance(10.0)),
                ("consequence", consequence_distance(10.0, 10.0)),
                ("partition", partition_distance(10.0, 10.0)),
            ):
                errs.setdefault((name, size), []).append(
                    abs(capable(coalesce(people, size, dist), 10.0) - truth)
                )
    print(
        f"   occupied decision cells (experience side x access) per population: {sorted(set(occupied))}"
    )
    print("   components  |capable error| p50 / p90 (people of 80):")
    print(
        "               equal-weight (exp, access) | capability-class only | decision-partition cells"
    )
    for size in (1, 2, 4, 8, 16, 32):
        cells = [errs[(name, size)] for name in ("equal-weight", "consequence", "partition")]
        print(
            f"   {size:<11} "
            + " | ".join(
                f"{np.quantile(v, 0.5):5.2f} / {np.quantile(v, 0.9):5.2f}           " for v in cells
            )
        )
    print()

    print("5. cost per fission event (N = 80, two binary attributes; 100,000 events)")
    counts = compartments(population(80, 20, 20, 5))
    people = population(80, 20, 20, 5)
    cost = {}
    t = time.perf_counter()
    for _ in range(100_000 // 1000):
        _ = rng.random((1000, 80)) < f
    cost["R5 individuals"] = (time.perf_counter() - t) / 1e5
    t = time.perf_counter()
    for _ in range(100_000 // 1000):
        _ = rng.binomial(counts.ravel(), f, size=(1000, 4))
    cost["R2 compartments"] = (time.perf_counter() - t) / 1e5
    t = time.perf_counter()
    for _ in range(100_000 // 1000):
        _ = rng.binomial(80, f, size=1000)
    cost["R3 mixture / marginals"] = (time.perf_counter() - t) / 1e5
    state = {
        "R5 individuals": people.nbytes,
        "R2 compartments": counts.nbytes,
        "R3 mixture / marginals": 4 * 8 + 8,
    }
    for key, sec in cost.items():
        print(
            f"   {key:<24} {sec * 1e9:7.1f} ns/event (vectorized); state {state[key]} B/unit for 2 attributes"
        )
    print(
        "   scaling with d binary attributes: individuals N*d B; compartments 2^d counts; mixture <= M*(d+1) floats; moments d + d(d+1)/2 floats; marginals d floats"
    )


if __name__ == "__main__":
    main()

# The report tables keep one entry per line.
# ruff: noqa: E501
"""Provisioning supply, demand and simultaneous feasibility (MVP 3 Stage 6B-P3).
Observation and analyst counterfactuals only. READ-ONLY / NOT ACTIVE.

Reads the provenance-verified ``donor_offer_audit`` recordings (MVP 2.2; the trade's
pre-trade inputs, the reachable offering donors of every deficit unit with path costs, and
the authoritative transfers) and, for every trade year:

- replays the production matching (``provisioning_counterfactual.match``) from the raw
  inputs; it must reproduce the authoritative transfers exactly (benchmark A);
- solves the simultaneous feasibility LP (``economy/provisioning_feasibility.py``) on the
  same recorded graph, under offers {production ``phi b``, full surplus ``b``} x transport
  {actual, lossless} (B, C, D, G); the global lossless ceilings with every same-species
  pair allowed are analytic, ``min(total budget, total deficit)`` (H, E);
- measures competition for shared donors, the distribution of relief under the matching
  and under two labelled tie-breaks among optimal allocations, and the matching's
  sensitivity to recipient order, donor order and ids.

``--opportunity DIR`` also checks the join with the ``opportunity_audit`` recordings of the
same runs: identical configuration, source and environment, the same units every year, and
the same authoritative transfers.

Every comparison is conditional on the others' settings; none is an independent causal
share, and an allocation that is physically feasible is not one any actor knows of, can
communicate, or would choose.

Usage:
    uv run python scripts/probes/donor_offer_audit.py record --jobs 2 --out DIR
    uv run python scripts/probes/provisioning_feasibility.py analyse --load DIR [--opportunity DIR] [--jobs 2] [--seeds ...]
"""

import argparse
import importlib.util
import random
import sys
import time
from collections import Counter, defaultdict
from multiprocessing import Pool
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

from _common import SEEDS
from _integrity import (
    ENVIRONMENT_KEYS,
    EXECUTION_KEYS,
    SCIENTIFIC_KEYS,
    RecordingError,
    load_data,
    read_container,
    select_runs,
)

from madexplorer.economy.donor_offer import offers_at
from madexplorer.economy.provisioning_counterfactual import match
from madexplorer.economy.provisioning_feasibility import components, edges_from, solve, usable

REL = 1e-9  # a recipient counts as fully relieved within this fraction of its deficit


def _module(name: str) -> Any:
    path = Path(__file__).with_name(f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"p3_{name}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


DONOR = _module("donor_offer_audit")


# ---------------------------------------------------------------- one year


def _relabel(
    deficits: list[Any],
    offers: dict[str, float],
    donors_of: dict[str, Any],
    decay: float,
    rng: random.Random,
) -> dict[str, float]:
    """The matching with every unit id replaced by a random label (physics unchanged): only
    tie-breaks can change. Received kcal under the original ids."""
    ids = sorted({r for _, r, _, _ in deficits} | set(offers))
    new = dict(zip(ids, rng.sample([f"x{k:06d}" for k in range(len(ids))], len(ids)), strict=True))
    back = {v: k for k, v in new.items()}
    m = match([(s, new[r], x, n) for s, r, x, n in deficits], {new[d]: o for d, o in offers.items()},
              {new[r]: [(c, new[d]) for c, d in v] for r, v in donors_of.items()}, decay)  # fmt: skip
    return {back[r]: g for r, g in m.received().items()}


def analyse_year(y: dict[str, Any], seed: int) -> dict[str, Any]:
    """Every benchmark and measure for one trade year (pure; the recording is not modified)."""
    info, donors_of, decay = y["info"], y["donors_of"], y["decay"]
    b, share, deficits = DONOR.inputs(y)
    offers = offers_at(b, share)
    full = {u: x for u, x in b.items() if x > 0}
    deficit = {r: x for _, r, x, _ in deficits}
    need = {r: n for _, r, _, n in deficits}
    a = match(deficits, offers, donors_of, decay)
    edges = edges_from(donors_of, decay)
    lossless = edges_from(donors_of, decay, lossless=True)
    sev = {r: deficit[r] / need[r] for r in deficit}  # relative severity, as production ranks
    opt = solve(offers, deficit, edges)
    out: dict[str, Any] = {
        "year": y["year"], "exact": a.transfers == y["actual"],
        "deficit": sum(deficit.values()), "surplus": sum(full.values()), "offered": sum(offers.values()),
        "shipped": a.totals()[0], "A": a.totals()[1], "B": opt.delivered,
        "C": solve(offers, deficit, lossless).delivered,
        "D": solve(full, deficit, edges).delivered, "G": solve(full, deficit, lossless).delivered,
        "H": min(sum(offers.values()), sum(deficit.values())), "E": min(sum(full.values()), sum(deficit.values())),
        "A_full": match(deficits, full, donors_of, decay).totals()[1],
        "n_rec": len(deficit), "gap": opt.gap,
    }  # fmt: skip
    hi = solve(offers, deficit, edges, priority=sev)
    lo = solve(offers, deficit, edges, priority={r: -s for r, s in sev.items()})
    got = {"A": a.received(), "B": opt.received(), "Bsev": hi.received(), "Banti": lo.received()}
    # --- competition for shared donors (production offers, recorded graph)
    live = usable(offers, deficit, edges)
    reach: dict[str, list[tuple[str, float]]] = defaultdict(list)
    claims: dict[str, int] = Counter()
    for d, r, f in live:
        reach[r].append((d, f))
        claims[d] += 1
    out["claimed"] = sum(f * offers[d] for d, _, f in live)  # every recipient counts each donor
    out["distinct"] = sum(offers[d] for d in claims)  # each claimed donor's offer once
    out["claimed_full"] = sum(f * full[d] for d, _, f in usable(full, deficit, edges))
    comp_rows = []
    for donors, recs in components(live):
        alone = all(sum(f * offers[d] for d, f in reach[r]) >= deficit[r] * (1 - REL) for r in recs)
        joint = all(got["B"].get(r, 0.0) >= deficit[r] * (1 - REL) for r in recs)
        comp_rows.append((len(donors), len(recs), alone, joint))
    out["components"] = comp_rows
    out["no_donor"] = sum(1 for r in deficit if r not in reach)
    # --- recipients
    rows = []
    for r in deficit:
        rows.append({
            "year": y["year"], "id": r, "need": need[r], "deficit": deficit[r], "people": info[r]["people"],
            "donors": len(reach.get(r, ())), "shared": any(claims[d] >= 2 for d, _ in reach.get(r, ())),
            "alone": sum(f * offers[d] for d, f in reach.get(r, ())) / deficit[r],
            "alone_full_6b": sum(np.exp(-c / decay) * b[d] for c, d in donors_of.get(r, ())) / deficit[r],
            **{k: v.get(r, 0.0) for k, v in got.items()},
        })  # fmt: skip
    out["recipients"] = rows
    out["unused_A"] = sum(offers.values()) - a.totals()[0]
    out["unused_B"] = sum(offers.values()) - sum(opt.sent().values())
    # --- ordering and identity sensitivity of the matching (production rule untouched)
    rng = random.Random(seed * 100_003 + y["year"])
    base = got["A"]

    def moved(variant: dict[str, float]) -> float:
        return sum(abs(variant.get(r, 0.0) - base.get(r, 0.0)) for r in deficit) / 2

    orders = {
        "recipients random": match([(rng.random(), r, x, n) for _, r, x, n in deficits], offers, donors_of, decay).received(),
        "donors random": match(deficits, offers, donors_of, decay, ties={r: {d: rng.random() for _, d in v} for r, v in donors_of.items()}, weight=1.0).received(),
        "donors farthest first": match(deficits, offers, donors_of, decay, ties={r: {d: c for c, d in v} for r, v in donors_of.items()}, weight=1.0).received(),
        "ids relabelled": _relabel(deficits, offers, donors_of, decay, rng),
    }  # fmt: skip
    out["orders"] = {k: (sum(v.values()), moved(v)) for k, v in orders.items()}
    severity = Counter(s for s, _, _, _ in deficits)
    out["severity_ties"] = sum(n for n in severity.values() if n > 1)
    out["cost_ties"] = sum(1 for v in donors_of.values() if len({c for c, _ in v}) < len(v))
    return out


def analyse_run(run: dict[str, Any]) -> dict[str, Any]:
    return {"name": run["name"], "seed": run["seed"],
            "years": [analyse_year(y, run["seed"]) for y in run["trade"]]}  # fmt: skip


def _analyse_path(path: Path) -> dict[str, Any]:
    return analyse_run(load_data(path))


# ---------------------------------------------------------------- join with the opportunity probe


def check_join(donor_dir: Path, opp_dir: Path, paths: list[Path]) -> None:
    """Raise unless each analysed donor recording joins its opportunity recording: same
    scientific identity except the probe, same source and environment, same units every
    year, same authoritative transfers."""
    keys = [k for k in SCIENTIFIC_KEYS if k not in ("probe", "recording_schema_version")]
    problems = []
    for path in paths:
        prov_d, _ = read_container(path)
        other = opp_dir / path.name
        try:
            prov_o, _ = read_container(other)
        except (OSError, RecordingError) as error:
            problems.append(f"{path.name}: no joinable opportunity recording ({error})")
            continue
        for k in (*keys, "source_tree_sha256", "git_commit", *ENVIRONMENT_KEYS):
            if prov_d.get(k) != prov_o.get(k):
                problems.append(
                    f"{path.name}: {k} differs ({prov_d.get(k)!r} vs {prov_o.get(k)!r})"
                )
        for k in EXECUTION_KEYS:
            if prov_d["execution"].get(k) != prov_o["execution"].get(k):
                problems.append(f"{path.name}: execution.{k} differs")
        donor, opp = load_data(path), load_data(other)
        units = {y["year"]: set(y["units"]) for y in opp["years"]}
        for y in donor["trade"]:
            if set(y["order"]) != units.get(y["year"]):
                problems.append(f"{path.name}: units differ in year {y['year']}")
                break
            if [tuple(t) for t in y["actual"]] != [t[:4] for t in opp["transfers"][y["year"]]]:
                problems.append(f"{path.name}: transfers differ in year {y['year']}")
                break
        print(f"  join {path.name}: {len(donor['trade'])} trade years, units and transfers identical"
              if not any(p.startswith(path.name) for p in problems) else f"  join {path.name}: FAILED")  # fmt: skip
    if problems:
        raise RecordingError(
            "join with the opportunity recordings failed:\n  " + "\n  ".join(problems)
        )


# ---------------------------------------------------------------- report


def _pct(x: float, n: float) -> str:
    return f"{100 * x / n:.2f} %" if n else "-"


def _q(values: Any, qs: tuple[float, ...] = (0.1, 0.5, 0.9)) -> str:
    a = np.asarray(values, dtype=float)
    return "/".join(f"{np.quantile(a, x):.3g}" for x in qs) if a.size else "-"


def report(name: str, outs: list[dict[str, Any]]) -> None:
    years = [y for o in outs for y in o["years"]]
    T = {
        k: sum(y[k] for y in years)
        for k in (
            "deficit",
            "surplus",
            "offered",
            "shipped",
            "A",
            "B",
            "C",
            "D",
            "G",
            "H",
            "E",
            "A_full",
            "unused_A",
            "unused_B",
            "claimed",
            "distinct",
            "claimed_full",
        )
    }
    dfc = T["deficit"]
    print(
        f"\n=== {name}: {len(outs)} seeds, {len(years)} trade years; greedy replay = authoritative transfers in {sum(y['exact'] for y in years)}/{len(years)} years; max relative duality gap {max(y['gap'] for y in years):.2g}"
    )
    print("\n-- central table (kcal summed over seeds and years; % of the total pre-trade deficit)")
    rows = [
        ("total pre-trade deficit (recipients: b < 0, need > 0)", T["deficit"]),
        ("total positive surplus b (all units with b > 0)", T["surplus"]),
        ("total offered phi*b", T["offered"]),
        ("A actual shipped", T["shipped"]),
        ("A actual delivered", T["A"]),
        ("B optimum: offers, recorded reach, transport", T["B"]),
        ("C optimum: offers, recorded reach, no transport loss", T["C"]),
        ("H ceiling: offers, all same-species pairs, no loss (analytic)", T["H"]),
        ("D optimum: full surplus, recorded reach, transport", T["D"]),
        ("G optimum: full surplus, recorded reach, no transport loss", T["G"]),
        (
            "E ceiling: full surplus, all same-species pairs, no loss (analytic; not realizable)",
            T["E"],
        ),
        ("matching at full surplus (greedy, recorded reach, transport)", T["A_full"]),
    ]
    for label, v in rows:
        print(f"   {label:<88} {v:14.4g}  {_pct(v, dfc):>9}")
    print(
        f"   {'unavoidable shortage under offers and recorded reach (deficit - B)':<88} {dfc - T['B']:14.4g}  {_pct(dfc - T['B'], dfc):>9}"
    )
    print(
        f"   {'additional delivery feasible beyond the matching (B - A)':<88} {T['B'] - T['A']:14.4g}  {_pct(T['B'] - T['A'], dfc):>9}  ({_pct(T['B'] - T['A'], T['A'])} of A)"
    )
    print(
        f"   {'unused offers: matching / optimum B (kcal shipped)':<88} {T['unused_A']:14.4g}  {T['unused_B']:.4g} ({_pct(T['unused_A'], T['offered'])} / {_pct(T['unused_B'], T['offered'])} of offered)"
    )
    print(
        f"   shipped / offered (matching) {_pct(T['shipped'], T['offered'])}; transport loss of matching shipments {_pct(T['shipped'] - T['A'], T['shipped'])}"
    )
    print("\n-- conditional comparisons (each holds the other settings fixed; not additive shares)")
    print(
        f"   matching -> optimum (offers, reach, transport): +{_pct(T['B'] - T['A'], dfc)} of deficit;  at full surplus: +{_pct(T['D'] - T['A_full'], dfc)}"
    )
    print(
        f"   transport loss -> none: at offers +{_pct(T['C'] - T['B'], dfc)};  at full surplus +{_pct(T['G'] - T['D'], dfc)}"
    )
    print(
        f"   recorded reach -> all pairs (lossless): at offers +{_pct(T['H'] - T['C'], dfc)};  at full surplus +{_pct(T['E'] - T['G'], dfc)}"
    )
    print(
        f"   offers -> full surplus: with transport +{_pct(T['D'] - T['B'], dfc)};  lossless reach +{_pct(T['G'] - T['C'], dfc)};  global lossless +{_pct(T['E'] - T['H'], dfc)}"
    )
    yr = lambda k: np.array([y[k] for y in years], dtype=float)  # noqa: E731
    d = yr("deficit")
    print("\n-- per trade year (unit: years; a year is one simultaneous allocation problem)")
    print(
        f"   years with a deficit {int((d > 0).sum())}/{len(years)}; aggregate shortage unavoidable even globally (E < deficit) in {_pct(((yr('E') < d * (1 - REL)) & (d > 0)).sum(), (d > 0).sum())} of them"
    )
    print(
        f"   all deficits met: matching {_pct(((yr('A') >= d * (1 - REL)) & (d > 0)).sum(), (d > 0).sum())}; optimum B {_pct(((yr('B') >= d * (1 - REL)) & (d > 0)).sum(), (d > 0).sum())}; offers in total >= deficits {_pct(((yr('offered') >= d) & (d > 0)).sum(), (d > 0).sum())}"
    )
    print(
        f"   matching below optimum B by > 1e-6 of the deficit: {_pct(((yr('B') - yr('A')) > 1e-6 * d).sum(), (d > 0).sum())}; (B - A) / deficit per year p50/p90/max {_q(((yr('B') - yr('A')) / np.maximum(d, 1e-300))[d > 0], (0.5, 0.9, 1.0))}"
    )
    comps = [c for y in years for c in y["components"]]
    if comps:
        alone = np.array([c[2] for c in comps])
        joint = np.array([c[3] for c in comps])
        multi = np.array([c[1] >= 2 for c in comps])
        print(
            "\n-- provisioning networks (connected donor-recipient components, offers, recorded reach)"
        )
        print(
            f"   components {len(comps)} (multi-recipient {_pct(multi.sum(), len(comps))}); all deficits satisfiable simultaneously (optimum) {_pct(joint.sum(), len(comps))}; multi-recipient {_pct((joint & multi).sum(), multi.sum())}"
        )
        print(
            f"   every recipient individually covered by the offers it reaches {_pct(alone.sum(), len(comps))}; of those, not jointly satisfiable {_pct((alone & ~joint).sum(), alone.sum())}"
        )
        print(
            f"   recipients with no reachable offering donor {sum(y['no_donor'] for y in years)}/{sum(y['n_rec'] for y in years)} recipient-years"
        )
    print("\n-- apparent versus distinct supply (double counting)")
    print(
        f"   delivered-equivalent offers claimed by recipients (each counts every reachable donor) / distinct offers of the claimed donors: {T['claimed'] / max(T['distinct'], 1e-300):.2f}"
    )
    print(
        f"   claimed / total deficit: offers {T['claimed'] / dfc:.2f}; full surplus (the 6B measure, summed) {T['claimed_full'] / dfc:.2f}"
    )
    recs = [r for y in years for r in y["recipients"]]
    R = {
        k: np.array([r[k] for r in recs], dtype=float)
        for k in (
            "need",
            "deficit",
            "people",
            "donors",
            "alone",
            "alone_full_6b",
            "A",
            "B",
            "Bsev",
            "Banti",
        )
    }
    shared = np.array([r["shared"] for r in recs])
    w = R["people"] / R["people"].sum()
    print("\n-- recipients (recipient-years; pop = population-weighted)")
    print(
        f"   recipient-years {len(recs)}; reachable offering donors p10/p50/p90 {_q(R['donors'])}; >= 2 donors {_pct((R['donors'] >= 2).sum(), len(recs))}; sharing a donor with another recipient {_pct(shared.sum(), len(recs))}"
    )
    print(
        f"   reachable delivered-equivalent full surplus / own deficit (6B measure) p10/p50/p90 {_q(R['alone_full_6b'])}; reachable offers / deficit {_q(R['alone'])}; offers alone >= deficit {_pct((R['alone'] >= 1 - REL).sum(), len(recs))}"
    )
    for key, label in (
        ("A", "matching"),
        ("B", "optimum (solver's choice)"),
        ("Bsev", "optimum, severe first"),
        ("Banti", "optimum, least severe first"),
    ):
        got = R[key]
        full_ = got >= R["deficit"] * (1 - REL)
        none = got <= 1e-9 * R["deficit"]
        short = R["deficit"] - got
        intake = (
            1 - np.maximum(short, 0) / R["need"]
        )  # dietary intake (dietary_intake_ratio) after trade
        print(
            f"   {label:<28} full relief {_pct(full_.sum(), len(recs))} (pop {100 * w[full_].sum():.2f} %); partial {_pct((~full_ & ~none).sum(), len(recs))}; nothing {_pct(none.sum(), len(recs))} (pop {100 * w[none].sum():.2f} %); "
            f"still short {_pct((~full_).sum(), len(recs))}; unmet / need p50/p90/p99 {_q(short / R['need'], (0.5, 0.9, 0.99))}; intake p1/p10 {_q(intake, (0.01, 0.1))}"
        )
    for key, label in (
        ("B", "solver's choice"),
        ("Bsev", "severe first"),
        ("Banti", "least severe first"),
    ):
        diff = R[key] - R["A"]
        scale = R["deficit"]
        print(
            f"   optimum ({label}) vs matching: recipients gaining > 1e-6 of deficit {_pct((diff > 1e-6 * scale).sum(), len(recs))}, losing {_pct((diff < -1e-6 * scale).sum(), len(recs))}; "
            f"gain among single-donor recipients {_pct(diff[R['donors'] <= 1].clip(0).sum(), diff.clip(0).sum())} of all gains"
        )
    spread = np.abs(R["Bsev"] - R["Banti"]) / R["deficit"]
    print(
        f"   nonuniqueness: |severe-first - least-severe-first| / deficit > 1e-6 for {_pct((spread > 1e-6).sum(), len(recs))} of recipient-years (p99 {_q(spread, (0.99,))})"
    )
    print(
        "\n-- matching sensitivity (same physics; delivered total vs actual, food moved between recipients)"
    )
    for k in years[0]["orders"]:
        tot = sum(y["orders"][k][0] for y in years)
        mov = sum(y["orders"][k][1] for y in years)
        diff_years = sum(
            abs(y["orders"][k][0] - y["A"]) > 1e-6 * max(y["deficit"], 1.0) for y in years
        )
        print(
            f"   {k:<24} delivered {_pct(tot - T['A'], T['A'])} vs actual; years with a different total {diff_years}/{len(years)}; food reassigned {_pct(mov, T['A'])} of actual delivery"
        )
    print(
        f"   exact ties: recipient-years with equal severity {sum(y['severity_ties'] for y in years)}; recipients with equal-cost donors {sum(y['cost_ties'] for y in years)}"
    )
    print("\n-- per seed (each seed one independent run; ratios to that seed's total deficit)")
    for o in outs:
        t = {
            k: sum(y[k] for y in o["years"])
            for k in ("deficit", "A", "B", "C", "D", "E", "offered")
        }
        print(
            f"   seed {o['seed']}: A {_pct(t['A'], t['deficit'])}  B {_pct(t['B'], t['deficit'])}  C {_pct(t['C'], t['deficit'])}  D {_pct(t['D'], t['deficit'])}  E {_pct(t['E'], t['deficit'])}  offered {_pct(t['offered'], t['deficit'])}  (B-A)/A {_pct(t['B'] - t['A'], t['A'])}"
        )


def analyse(
    load: Path, jobs: int, seeds: list[int], explicit: bool, mixed: bool, opportunity: Path | None
) -> None:
    started = time.perf_counter()
    try:
        paths = select_runs(load, list(DONOR.MVP2_2), seeds, explicit, DONOR.ident_of, False, mixed)
        if opportunity is not None:
            check_join(load, opportunity, paths)
    except RecordingError as error:
        raise SystemExit(str(error)) from None
    with Pool(jobs, maxtasksperchild=1) as pool:
        outs = pool.map(_analyse_path, paths, chunksize=1)
    for name in DONOR.MVP2_2:
        mine = [o for o in outs if o["name"] == name]
        if mine:
            report(name, mine)
    print(f"\n(analysis {time.perf_counter() - started:.0f} s)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("analyse",))
    parser.add_argument("--load", type=Path, required=True, help="donor_offer_audit recordings")
    parser.add_argument("--opportunity", type=Path, help="opportunity_audit recordings to join")
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument(
        "--seeds", type=int, nargs="*", help=f"explicit subset (default {list(SEEDS)})"
    )
    parser.add_argument("--mixed-environments", action="store_true")
    args = parser.parse_args()
    seeds = list(SEEDS) if args.seeds is None else args.seeds
    analyse(
        args.load,
        args.jobs,
        seeds,
        args.seeds is not None,
        args.mixed_environments,
        args.opportunity,
    )


if __name__ == "__main__":
    main()

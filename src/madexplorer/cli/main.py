"""``madexplorer`` command-line interface (spec §36).

madexplorer validate scenario.yaml
madexplorer run scenario.yaml [--seed 42 | --seeds 1:10] [--years N] [--out DIR]
madexplorer inspect runs/<scenario>/seed_0 [--map]
madexplorer rules
"""

import argparse
import logging
import sys
from pathlib import Path

import numpy as np

from madexplorer.config.loader import Scenario
from madexplorer.core.governance import RULES
from madexplorer.core.simulation import Simulator
from madexplorer.persistence.output import read_manifest, read_metrics
from madexplorer.world.generation import generate_world

logger = logging.getLogger("madexplorer")


def _parse_seeds(text: str) -> list[int]:
    """Parse ``"7"``, ``"1:10"`` (inclusive), or ``"1,5,9"``."""
    if ":" in text:
        start, end = (int(part) for part in text.split(":", 1))
        return list(range(start, end + 1))
    return [int(part) for part in text.split(",")]


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate configuration and check initial populations land on land cells."""
    scenario = Scenario.from_yaml(args.scenario)
    world = generate_world(scenario.config.world, scenario.config.ecology)
    for seed in scenario.config.initial_populations:
        if world.is_water[world.cell_id(*seed.cell)]:
            print(f"error: initial population at {seed.cell} is on water", file=sys.stderr)
            return 1
    land = int((~world.is_water).sum())
    print(
        f"ok: {scenario.config.name} | species={sorted(scenario.species)} | "
        f"grid={world.width}x{world.height} ({land} land cells) | "
        f"config_hash={scenario.config_hash()[:12]}"
    )
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """Run one or more seeds and write outputs."""
    base = Scenario.from_yaml(args.scenario)
    seeds = (
        _parse_seeds(args.seeds)
        if args.seeds
        else [args.seed if args.seed is not None else base.config.simulation.seed]
    )
    out_root = Path(args.out) if args.out else Path("runs") / base.config.name
    for seed in seeds:
        scenario = base.with_overrides(seed=seed, n_years=args.years)
        simulator = Simulator(scenario, trace_units=args.trace or ())
        interval = max(scenario.config.simulation.n_years // 10, 1)

        def progress(row: dict[str, float | int], interval: int = interval) -> None:
            if int(row["year"]) % interval == 0:
                logger.info(
                    "year=%d population=%d units=%d occupied_cells=%d food_ratio=%.2f",
                    row["year"],
                    row["population"],
                    row["units"],
                    row["occupied_cells"],
                    row["mean_food_ratio"],
                )

        result = simulator.run(progress=None if args.quiet else progress)
        directory = result.save(out_root / f"seed_{seed}")
        final = result.metrics[-1] if result.metrics else {}
        print(
            f"seed={seed} final_year={final.get('year')} population={final.get('population')} "
            f"units={final.get('units')} occupied_cells={final.get('occupied_cells')} "
            f"runtime={result.manifest['runtime_seconds']:.1f}s -> {directory}"
        )
    return 0


def _ascii_map(population: np.ndarray, is_water: np.ndarray) -> str:
    """Render population per cell: ``~`` water, ``.`` empty land, ``1-9`` log-scaled density."""
    top = max(int(population.max()), 1)
    lines = []
    for pop_row, water_row in zip(population, is_water, strict=True):
        chars = []
        for pop, water in zip(pop_row, water_row, strict=True):
            if water:
                chars.append("~")
            elif pop == 0:
                chars.append(".")
            else:
                chars.append(str(1 + min(8, int(8 * np.log1p(pop) / np.log1p(top)))))
        lines.append("".join(chars))
    return "\n".join(lines)


def cmd_inspect(args: argparse.Namespace) -> int:
    """Summarize a completed run."""
    directory = Path(args.run_dir)
    manifest = read_manifest(directory)
    metrics = read_metrics(directory)
    for key in (
        "scenario_name",
        "seed",
        "world_seed",
        "final_year",
        "config_hash",
        "git_commit",
        "runtime_seconds",
    ):
        print(f"{key:>16}: {manifest.get(key)}")
    if metrics:
        checkpoints = sorted(
            {0, len(metrics) // 4, len(metrics) // 2, 3 * len(metrics) // 4, len(metrics) - 1}
        )
        cols = (
            "year",
            "population",
            "units",
            "occupied_cells",
            "mean_group_size",
            "mean_food_ratio",
            "plant_stock_fraction",
        )
        print("\n" + " ".join(f"{c:>20}" for c in cols))
        for i in checkpoints:
            print(" ".join(f"{metrics[i][c]:>20.2f}" for c in cols))
    if args.map:
        spatial = np.load(directory / "spatial.npz")
        world = np.load(directory / "world.npz")
        print(f"\npopulation in year {int(spatial['years'][-1])} (north up):")
        print(_ascii_map(spatial["population"][-1], world["is_water"]))
    return 0


def cmd_rules(args: argparse.Namespace) -> int:
    """List registered model rules and their provenance."""
    import madexplorer.core.simulation  # noqa: F401  (imports every subsystem, registering rules)

    for rule in sorted(RULES.values(), key=lambda r: r.name):
        print(f"{rule.name} v{rule.version} [{rule.source_type}]  ({rule.qualname})")
        if args.verbose:
            print(f"    rationale:   {rule.rationale}")
            if rule.parameters:
                print(f"    parameters:  {', '.join(rule.parameters)}")
            print(f"    domain:      {rule.expected_domain}")
            print(f"    limitations: {rule.known_limitations}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Argument parser for all subcommands."""
    parser = argparse.ArgumentParser(
        prog="madexplorer", description="Social-ecological civilization simulator"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("validate", help="validate a scenario file")
    p.add_argument("scenario")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("run", help="run a scenario")
    p.add_argument("scenario")
    p.add_argument("--seed", type=int, help="run seed (overrides the scenario)")
    p.add_argument("--seeds", help="several seeds: '1:10' (inclusive) or '1,4,7'")
    p.add_argument("--years", type=int, help="override simulation.n_years")
    p.add_argument("--out", help="output root (default runs/<scenario name>)")
    p.add_argument(
        "--trace", nargs="*", help="unit ids whose decisions are traced in the event log"
    )
    p.add_argument("--quiet", action="store_true", help="suppress progress logging")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("inspect", help="summarize a run directory")
    p.add_argument("run_dir")
    p.add_argument("--map", action="store_true", help="print an ASCII population map")
    p.set_defaults(func=cmd_inspect)

    p = sub.add_parser("rules", help="list model rules and their provenance")
    p.add_argument("-v", "--verbose", action="store_true")
    p.set_defaults(func=cmd_rules)
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    args = build_parser().parse_args(argv)
    code: int = args.func(args)
    return code


if __name__ == "__main__":
    sys.exit(main())

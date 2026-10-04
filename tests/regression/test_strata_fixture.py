"""Versioned MVP 3 Stage 3B fixture: neutral socioeconomic accounting of strata claims.

Protects the Stage 3B semantics (field- and store-claim accretion, proportional depletion,
the zero-stock rule, exact compaction, pooling transfers) against drift. It is not a
scientific baseline and does not replace the MVP 2.1 golden fixtures and oracles, which
cover the unit-level simulation (unchanged by strata).

Scenario: 30 synthetic farming units (mvp2_neolithic, seed 11), three of them with
deliberately unequal claims over existing fields and stores (deterministic fixtures, no
random strata); 40 steps. It exercises field expansion, store additions and withdrawals,
fusion inheritance and nonzero pooling transfers. Hashes are numeric-platform specific, as
for the golden fixtures; re-record only for an intended Stage 3B semantic change with
``UPDATE_STRATA_FIXTURE=1``.

Stage 3C keeps this fixture authoritative at its neutral default
``strata.field_output_claim_weight = 0``: flow rows are digested on their Stage 3B columns
(Stage 3C appends columns, a schema change only), and the appended columns are checked to be
neutral (no harvest pooling, store component = the whole transfer).

Both fixtures pin ``strata.max_strata = 8``, the capacity their semantics were recorded at:
they are historical targeted regressions, not statements about the current default (16
since Stage 4B.1; covered by tests/test_strata_resolution.py).
"""

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from madexplorer.config.loader import Scenario
from madexplorer.core.provenance import numeric_platform
from madexplorer.experiments.benchmark import synthetic_simulator
from madexplorer.metrics.strata import strata_rows
from madexplorer.population.strata import StrataBlock
from madexplorer.population.strata_accounting import STAGE3B_FLOW_COLUMNS
from tests.conftest import ROOT

FIXTURE = Path(__file__).parent / "golden_strata" / "stage3b_seed11_30u_40y.json"
FIXTURE_3C = Path(__file__).parent / "golden_strata" / "stage3c_w0.5_seed11_30u_40y.json"
FIXTURE_CAPACITY = 8  # historical Stage 3B/3C capacity; explicit, never the project default


def _block(share: list[float], field: list[float], store: list[float]) -> StrataBlock:
    return StrataBlock(
        {
            "share": np.array(share),
            "field_claim": np.array(field),
            "store_claim": np.array(store),
        },
        np.zeros(len(share), dtype=np.int64),
    )


FIXTURES = (
    _block([0.8, 0.2], [0.5, 0.5], [0.8, 0.2]),  # minority with 4x field position
    _block([0.5, 0.5], [0.7, 0.3], [0.2, 0.8]),  # cross-cutting field and store positions
    _block([0.6, 0.4], [0.6, 0.4], [0.3, 0.7]),  # unequal stores only
)


def _simulate(weight: float) -> tuple[list[dict[str, Any]], Any]:
    scenario = Scenario.from_yaml(ROOT / "scenarios" / "mvp2_neolithic.yaml")
    scenario = scenario.with_overrides(seed=11)
    scenario = scenario.with_settings({"strata.max_strata": FIXTURE_CAPACITY})
    if weight != 0.0:
        scenario = scenario.with_settings({"strata.field_output_claim_weight": weight})
    assert scenario.config.strata.field_output_claim_weight == weight
    sim = synthetic_simulator(scenario, 30, farming=True)
    population = sim.state.population
    assert population.strata is not None and population.strata.max_strata == FIXTURE_CAPACITY
    population.strata_log, population.strata_flows = [], []
    for unit, block in zip(list(sim.state.units.values())[:3], FIXTURES, strict=True):
        unit.fields_ha, unit.stores_kcal = 4.0, 3e5
        population.replace_strata(unit, block)
    rows: list[dict[str, Any]] = []
    for _ in range(40):
        sim.step()
        rows.extend(strata_rows(sim.state))
    return rows, sim


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, default=repr).encode()).hexdigest()


def _summary(rows: list[dict[str, Any]], sim: Any, flows: list[dict[str, Any]]) -> dict[str, Any]:
    log = sim.state.population.strata_log
    kinds = sorted({e["event"] for e in log})
    return {
        "final_units": len(sim.state.units),
        "differentiated_units": sum(len(u.strata) > 1 for u in sim.state.units.values()),
        "strata_rows": len(rows),
        "flow_rows": len(flows),
        "pool_transfer_volume_kcal": sum(max(r["pool_transfer_kcal"], 0.0) for r in flows),
        "events": {k: sum(e["event"] == k for e in log) for k in kinds},
        "strata_rows_sha256": _digest(rows),
        "flows_sha256": _digest(flows),
        "events_sha256": _digest(log),
    }


def _run() -> dict[str, Any]:
    """The Stage 3B fixture run, at the neutral default w = 0."""
    rows, sim = _simulate(0.0)
    flows = sim.state.population.strata_flows
    for row in flows:  # Stage 3C columns at w = 0: no crop-control attribution
        assert row["crop_attribution_correction_kcal"] == 0.0
        assert row["harvest_pool_transfer_kcal"] == 0.0
        assert row["store_pool_transfer_kcal"] == row["pool_transfer_kcal"]
    return _summary(rows, sim, [{key: row[key] for key in STAGE3B_FLOW_COLUMNS} for row in flows])


def _check(result: dict[str, Any], fixture: Path, flag: str) -> None:
    if os.environ.get(flag):
        fixture.parent.mkdir(exist_ok=True)
        payload = {"numeric_platform": numeric_platform(), **result}
        fixture.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n")
        pytest.skip("fixture re-recorded")
    expected = json.loads(fixture.read_text())
    if expected.pop("numeric_platform") != numeric_platform():
        pytest.skip("fixture recorded on a different numeric platform")
    assert result == expected


def test_stage3b_strata_accounting_matches_the_recorded_fixture() -> None:
    result = _run()
    assert result["flow_rows"] > 0 and result["differentiated_units"] > 0
    _check(result, FIXTURE, "UPDATE_STRATA_FIXTURE")


def test_stage3c_crop_output_attribution_matches_the_recorded_fixture() -> None:
    """Stage 3C sensitivity case w = 0.5 (a documented sensitivity case, not a canonical
    value): crop-output attribution, both pooling components and the store claims they
    drive. Re-record only for an intended Stage 3C change with ``UPDATE_STRATA_3C_FIXTURE=1``
    (never together with the Stage 3B fixture)."""
    rows, sim = _simulate(0.5)
    flows = sim.state.population.strata_flows
    result = _summary(rows, sim, flows)
    assert any(r["harvest_pool_transfer_kcal"] != 0.0 for r in flows)
    _check(result, FIXTURE_3C, "UPDATE_STRATA_3C_FIXTURE")

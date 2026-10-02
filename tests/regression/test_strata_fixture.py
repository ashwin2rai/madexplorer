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
from tests.conftest import ROOT

FIXTURE = Path(__file__).parent / "golden_strata" / "stage3b_seed11_30u_40y.json"


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


def _run() -> dict[str, Any]:
    scenario = Scenario.from_yaml(ROOT / "scenarios" / "mvp2_neolithic.yaml")
    sim = synthetic_simulator(scenario.with_overrides(seed=11), 30, farming=True)
    population = sim.state.population
    population.strata_log, population.strata_flows = [], []
    for unit, block in zip(list(sim.state.units.values())[:3], FIXTURES, strict=True):
        unit.fields_ha, unit.stores_kcal = 4.0, 3e5
        population.replace_strata(unit, block)
    rows: list[dict[str, Any]] = []
    for _ in range(40):
        sim.step()
        rows.extend(strata_rows(sim.state))

    def digest(value: Any) -> str:
        return hashlib.sha256(json.dumps(value, default=repr).encode()).hexdigest()

    flows = population.strata_flows
    log = population.strata_log
    kinds = sorted({e["event"] for e in log})
    return {
        "final_units": len(sim.state.units),
        "differentiated_units": sum(len(u.strata) > 1 for u in sim.state.units.values()),
        "strata_rows": len(rows),
        "flow_rows": len(flows),
        "pool_transfer_volume_kcal": sum(max(r["pool_transfer_kcal"], 0.0) for r in flows),
        "events": {k: sum(e["event"] == k for e in log) for k in kinds},
        "strata_rows_sha256": digest(rows),
        "flows_sha256": digest(flows),
        "events_sha256": digest(log),
    }


def test_stage3b_strata_accounting_matches_the_recorded_fixture() -> None:
    result = _run()
    assert result["flow_rows"] > 0 and result["differentiated_units"] > 0
    if os.environ.get("UPDATE_STRATA_FIXTURE"):
        FIXTURE.parent.mkdir(exist_ok=True)
        payload = {"numeric_platform": numeric_platform(), **result}
        FIXTURE.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n")
        pytest.skip("fixture re-recorded")
    expected = json.loads(FIXTURE.read_text())
    if expected.pop("numeric_platform") != numeric_platform():
        pytest.skip("fixture recorded on a different numeric platform")
    assert result == expected

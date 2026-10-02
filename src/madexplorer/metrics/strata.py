"""Strata sidecar observations (MVP 3): one row per stratum per year, outside the frozen
MVP 2.1 metrics stream.

Rows are keyed by ``(year, unit_id, stratum_id)`` and carry the stratum's ``share``, claims
and relative positions (``claim / share``; 1 = proportional). Observation only: the
simulation never reads them. Recording is opt-in (``Simulator(record_strata=True)``).
"""

from typing import Any

from madexplorer.core.state import SimulationState
from madexplorer.population.strata import CLAIMS, STRATUM_COLUMNS, positions

POSITION_COLUMNS = {
    "field_claim": "relative_field_position",
    "store_claim": "relative_store_position",
}


def strata_rows(state: SimulationState) -> list[dict[str, Any]]:
    """This year's strata of every unit, in unit (then storage) order."""
    rows: list[dict[str, Any]] = []
    for unit in state.units.values():
        block = unit.strata
        relative = positions(block)
        for k, stratum_id in enumerate(block.stratum_id.tolist()):
            row: dict[str, Any] = {
                "year": state.year,
                "unit_id": unit.id,
                "stratum_id": stratum_id,
            }
            for name in STRATUM_COLUMNS:
                row[name] = float(block.columns[name][k])
            for c, name in enumerate(CLAIMS):
                row[POSITION_COLUMNS[name]] = float(relative[k, c])
            rows.append(row)
    return rows

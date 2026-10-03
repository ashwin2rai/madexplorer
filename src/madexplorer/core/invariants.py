"""Conservation and integrity checks (spec §28.8, §38)."""

from collections.abc import Iterable
from typing import TYPE_CHECKING

import numpy as np

from madexplorer.core.types import FloatArray
from madexplorer.population.unit import PopulationUnit

if TYPE_CHECKING:
    from madexplorer.core.state import SimulationState


class InvariantViolation(RuntimeError):
    """Raised when a conservation or integrity rule is broken."""


def check_population_accounting(
    before: int, births: int, deaths: int, after: int, year: int
) -> None:
    """Population changes only through births and deaths (movement is internal)."""
    expected = before + births - deaths
    if after != expected:
        raise InvariantViolation(
            f"year {year}: population {after} != {before} + {births} births - {deaths} deaths"
        )


def check_units(units: Iterable[PopulationUnit], n_cells: int, year: int) -> None:
    """Counts and reserves are nonnegative and every unit sits on a real cell."""
    for unit in units:
        if (unit.females < 0).any() or (unit.males < 0).any():
            raise InvariantViolation(f"year {year}: negative cohort count in {unit.id}")
        if unit.reserve_kcal_per_capita < 0:
            raise InvariantViolation(f"year {year}: negative reserve in {unit.id}")
        if not 0 <= unit.cell < n_cells:
            raise InvariantViolation(f"year {year}: {unit.id} on invalid cell {unit.cell}")


def check_nonnegative(name: str, values: FloatArray, year: int) -> None:
    """Resource stocks and similar fields never go negative or NaN."""
    if not np.isfinite(values).all() or (values < 0).any():
        raise InvariantViolation(f"year {year}: {name} contains negative or non-finite values")


def check_state_units(state: "SimulationState", year: int) -> None:
    """:func:`check_units` for a state; vectorized over the unit table in table mode, where
    it also checks that cached population counts equal the cohort sums."""
    table = state.table
    units = state.units
    if table is None:
        check_units(units.values(), state.world.n_cells, year)
        for unit in units.values():
            if not unit.strata.is_valid(state.population.max_strata):
                raise InvariantViolation(f"year {year}: invalid strata in {unit.id}")
        return
    slots = units.slots()
    if slots.size == 0:
        return
    order = list(units)
    bad_cohort = (table.females[slots] < 0).any(axis=1) | (table.males[slots] < 0).any(axis=1)
    if bad_cohort.any():
        raise InvariantViolation(
            f"year {year}: negative cohort count in {order[int(np.argmax(bad_cohort))]}"
        )
    reserve = table.reserve_kcal_per_capita[slots]
    if (reserve < 0).any():
        raise InvariantViolation(
            f"year {year}: negative reserve in {order[int(np.argmax(reserve < 0))]}"
        )
    cell = table.cell[slots]
    invalid = (cell < 0) | (cell >= state.world.n_cells)
    if invalid.any():
        k = int(np.argmax(invalid))
        raise InvariantViolation(f"year {year}: {order[k]} on invalid cell {int(cell[k])}")
    strata = state.population.strata
    assert strata is not None
    bad_strata = ~strata.check(slots)
    if bad_strata.any():
        raise InvariantViolation(
            f"year {year}: invalid strata in {order[int(np.argmax(bad_strata))]}"
        )
    stale = ~table.check_population(slots)
    if stale.any():
        raise InvariantViolation(
            f"year {year}: cached population of {order[int(np.argmax(stale))]} != cohort sums"
        )

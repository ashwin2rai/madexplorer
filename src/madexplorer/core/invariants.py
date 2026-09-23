"""Conservation and integrity checks (spec §28.8, §38)."""

from collections.abc import Iterable

import numpy as np

from madexplorer.core.types import FloatArray
from madexplorer.population.unit import PopulationUnit


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

"""Settlement health: a minimal crowding mortality hazard (spec §8.2, §8.4, §17).

This is a deliberate precursor to the MVP 3 health system and a later pathogen
model, not a disease model. Settled people living in contact with many other
settled people die more often (sanitation, water contamination, crowd
infections); mobile groups mostly escape the penalty because they do not stay
long among their own waste and neighbors.

Contact is measured on people, not on cell density, so that the pressure does
not depend on grid resolution:

* each unit's *sedentism* ``s = 1 - exp(-residence_years / tau)`` rises with time
  in place and resets when the group moves;
* its *contact population* is its own settlement (people per social group, so a
  coarsened multi-group unit is not treated as one large village) plus the other
  settled people in the cell weighted by the chance of contact
  ``w = min(1, contact_area / cell_area)``;
* pressure ``C = log(1 + N_contact / N0)`` and the additive, cause-specific hazard
  ``h_crowding = k * s * C``, scaled up for children and elders.

The total annual hazard is ``h_baseline + h_starvation + h_crowding``.
"""

import math
from collections.abc import Iterable, Mapping

from madexplorer.core.governance import model_rule
from madexplorer.population.unit import PopulationUnit
from madexplorer.species.profile import Health


@model_rule(
    name="sedentism",
    version="1.0",
    rationale=(
        "Exposure to settlement health costs builds up with continuous residence in one place "
        "(waste, contaminated water, commensal pests) and is shed by moving."
    ),
    source_type="heuristic",
    parameters=("sedentism_timescale_years",),
    expected_domain="[0, 1): 0 for a group that just moved, near 1 after several timescales",
    known_limitations="Residence is per cell; seasonal mobility within a cell is not modeled.",
)
def sedentism(residence_years: int, timescale_years: float) -> float:
    """Degree of sedentism from years of continuous residence."""
    return 1.0 - math.exp(-max(residence_years, 0) / timescale_years)


def contact_weight(contact_radius_km: float, cell_area_km2: float) -> float:
    """Chance that two groups in the same cell share a settlement-scale contact area."""
    return min(1.0, math.pi * contact_radius_km**2 / cell_area_km2)


@model_rule(
    name="settlement_crowding_pressure",
    version="1.0",
    rationale=(
        "Crowding pressure grows with the settled population a group is in contact with, with "
        "diminishing increments (log): the first hundreds of neighbors matter more per head "
        "than the next thousands."
    ),
    source_type="heuristic",
    parameters=("crowding_reference_population", "contact_radius_km"),
    expected_domain=">= 0; 0 without settled contacts",
    known_limitations=(
        "No explicit settlement geometry, sanitation technology, water quality, or pathogen "
        "ecology; contacts beyond the cell are ignored."
    ),
)
def settlement_crowding_pressure(contact_population: float, reference_population: float) -> float:
    """Pressure ``log(1 + N_contact / N0)``."""
    return math.log1p(max(contact_population, 0.0) / reference_population)


@model_rule(
    name="crowding_mortality_hazard",
    version="1.0",
    rationale=(
        "An additive, cause-specific annual hazard proportional to the group's own sedentism "
        "and the crowding pressure of its settlement, so crowding adds deaths without "
        "rescaling baseline or starvation mortality."
    ),
    source_type="placeholder",
    parameters=("crowding_mortality_per_log_contact", "crowding_vulnerable_multiplier"),
    expected_domain="hazard per year >= 0 (before the age multiplier)",
    known_limitations=(
        "Magnitudes are placeholders; no immunity, epidemics, or zoonotic reservoirs yet."
    ),
)
def crowding_mortality_hazard(pressure: float, sedentism_level: float, health: Health) -> float:
    """Adult annual crowding hazard (age multipliers are applied by the life tables)."""
    return health.crowding_mortality_per_log_contact * sedentism_level * pressure


def crowding_hazards(
    units: Iterable[PopulationUnit],
    species: Mapping[str, Health],
    cell_area_km2: float,
) -> dict[str, float]:
    """Adult crowding hazard for every unit, from co-located same-species settled people."""
    by_cell: dict[tuple[int, str], list[tuple[PopulationUnit, float]]] = {}
    for unit in units:
        health = species[unit.species_id]
        s = sedentism(unit.residence_years, health.sedentism_timescale_years)
        by_cell.setdefault((unit.cell, unit.species_id), []).append((unit, s))
    hazards: dict[str, float] = {}
    for (_, species_id), members in by_cell.items():
        health = species[species_id]
        w = contact_weight(health.contact_radius_km, cell_area_km2)
        settled_total = sum(u.population * s for u, s in members)
        for unit, s in members:
            village = unit.population / max(unit.groups, 1)
            others = settled_total - unit.population * s + (unit.population - village) * s
            contact = village * s + w * others
            pressure = settlement_crowding_pressure(contact, health.crowding_reference_population)
            hazards[unit.id] = crowding_mortality_hazard(pressure, s, health)
    return hazards

import pytest

from madexplorer.config.loader import Scenario
from madexplorer.core.ids import IdAllocator
from madexplorer.core.rng import RngManager, Streams
from madexplorer.core.simulation import Simulator
from tests.conftest import ROOT, small_scenario_dict


def test_streams_are_reproducible() -> None:
    a, b = RngManager(42), RngManager(42)
    assert (a.stream("demography").random(5) == b.stream("demography").random(5)).all()


def test_streams_are_independent_of_each_other() -> None:
    a, b = RngManager(42), RngManager(42)
    b.stream("migration").random(1000)  # drawing from another stream must not perturb this one
    assert (a.stream("demography").random(5) == b.stream("demography").random(5)).all()


def test_different_seeds_differ() -> None:
    assert RngManager(1).stream("x").random() != RngManager(2).stream("x").random()


def test_ids_are_stable_per_prefix() -> None:
    ids = IdAllocator()
    assert [ids.next("u"), ids.next("u"), ids.next("f"), ids.next("u")] == ["u1", "u2", "f1", "u3"]


def test_keyed_streams_depend_only_on_their_keys() -> None:
    a, b = RngManager(7), RngManager(7)
    b.stream("migration").random(100)
    b.keyed("migration", 3, "u1").random(10)
    assert a.keyed("migration", 4, "u2").random() == b.keyed("migration", 4, "u2").random()
    assert a.keyed("migration", 4, "u2").random() != a.keyed("migration", 4, "u3").random()
    assert a.keyed("migration", 4, "u2").random() != a.keyed("fission", 4, "u2").random()


def _next_draw_after_one_year(stream: str, mechanisms: dict[str, bool]) -> float:
    data = small_scenario_dict(n_years=1)
    data["initial_populations"] = [
        {"species": "human", "cell": [8, 8], "population": 120},
        {"species": "human", "cell": [8, 8], "population": 6},
    ]
    data["mechanisms"] = mechanisms
    sim = Simulator(Scenario.from_dict(data, base_dir=ROOT))
    sim.step()
    return float(sim.rng.stream(stream).random())


@pytest.mark.parametrize(
    ("stream", "switch"),
    [
        (Streams.PERCEPTION, "knowledge_sharing"),  # sharing draws come after perception
        (Streams.FISSION, "fusion"),
        (Streams.FISSION, "migration"),
        (Streams.DEMOGRAPHY, "fission"),
    ],
)
def test_mechanisms_do_not_share_streams(stream: str, switch: str) -> None:
    on = _next_draw_after_one_year(stream, {switch: True})
    off = _next_draw_after_one_year(stream, {switch: False})
    assert on == off

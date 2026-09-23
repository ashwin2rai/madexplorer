from madexplorer.core.ids import IdAllocator
from madexplorer.core.rng import RngManager


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

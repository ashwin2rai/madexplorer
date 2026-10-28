"""MVP 3 Stage 6B-P2: recording provenance, safe reuse and observer neutrality of the probes.

``scripts/probes/_integrity.py`` is exercised through the opportunity probe on short runs:
recordings are accepted only when intact and matching, analysis loads exactly the requested
runs, the state fingerprint detects every deliberate change, and hooks leave classes,
module functions and other simulators untouched.
"""

import importlib.util
import os
import pickle
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

import madexplorer.economy.agriculture_kernel as agriculture_kernel
import madexplorer.mobility.migration as migration
from madexplorer.config.loader import Scenario
from madexplorer.core.simulation import Simulator
from madexplorer.economy.foraging import ForagingSubsystem
from madexplorer.economy.trade import TradeSubsystem
from madexplorer.population.unit import belief_slot
from tests.conftest import ROOT

sys.path.insert(0, str(ROOT / "scripts/probes"))

_integrity: Any = importlib.import_module("_integrity")  # scripts/probes (not a package)
physical_digest = importlib.import_module("_common").physical_digest
LegacyRecording, RecordingError = _integrity.LegacyRecording, _integrity.RecordingError
compare, fingerprint, hook = _integrity.compare, _integrity.fingerprint, _integrity.hook
load_data, problems, read_container = (
    _integrity.load_data,
    _integrity.problems,
    _integrity.read_container,
)
run_observed, select_runs, swapped = (
    _integrity.run_observed,
    _integrity.select_runs,
    _integrity.swapped,
)
to_record, write_recording = _integrity.to_record, _integrity.write_recording

YEARS = 30
PRESSURE = "pressure+cult"


def _probe() -> Any:
    path = ROOT / "scripts/probes/opportunity_audit.py"
    spec = importlib.util.spec_from_file_location("opportunity_probe_p2", path)
    assert spec and spec.loader
    module: Any = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.MVP2_2 = {
        "neolithic": ("scenarios/mvp2_2_neolithic.yaml", YEARS, {}),
        PRESSURE: ("scenarios/mvp2_2_pressure.yaml", YEARS, {"mechanisms.cultivation": True}),
    }
    return module


@pytest.fixture(scope="module")
def probe() -> Any:
    return _probe()


@pytest.fixture(scope="module")
def runs(probe: Any) -> dict[int, dict[str, Any]]:
    """Two short pressure recordings (seeds 1 and 2), provenance attached."""
    return {seed: probe.record_job((PRESSURE, seed)) for seed in (1, 2)}


def _write(directory: Path, run: dict[str, Any], name: str | None = None) -> Path:
    data = dict(run)
    prov = data.pop("provenance")
    path = directory / (name or f"{run['name']}_{run['seed']}.pkl")
    write_recording(path, prov, data)
    return path


def _sim(years: int = 20, **kwargs: Any) -> Simulator:
    sc = Scenario.from_yaml(ROOT / "scenarios/mvp2_2_pressure.yaml").with_overrides(
        seed=1, n_years=years
    )
    sim = Simulator(sc.with_settings({"mechanisms.cultivation": True}), **kwargs)
    for _ in range(years):
        sim.step()
    return sim


# --- provenance and reuse


def test_provenance_identifies_the_run(probe: Any, runs: dict[int, dict[str, Any]]) -> None:
    prov = runs[1]["provenance"]
    assert problems(prov, probe.ident_of(PRESSURE, 1)) == []
    assert prov["run"] == PRESSURE and prov["seed"] == 1 and prov["n_years"] == YEARS
    assert prov["settings"] == {"mechanisms.cultivation": True}
    assert prov["recording_schema_version"] == probe.SCHEMA and prov["years_completed"] == YEARS
    assert prov["neutrality"]["neutral"] and prov["neutrality"]["checkpoint_years"]
    for key in ("config_hash", "source_tree_sha256", "probe_sha256", "git_commit", "git_dirty",
                "dependency_lock_hash", "python_version", "numpy_version", "timestamp_utc",
                "world_seed", "belief_backend", "execution"):  # fmt: skip
        assert key in prov
    assert set(prov["execution"]) == {"numeric_platform", "jit", "start_method", "thread_limits"}


def test_matching_recording_is_kept_and_loaded(
    probe: Any, runs: dict[int, dict[str, Any]], tmp_path: Path
) -> None:
    path = _write(tmp_path, runs[1])
    assert to_record(tmp_path, [(PRESSURE, 1), (PRESSURE, 2)], probe.ident_of, False) == [
        (PRESSURE, 2)
    ]
    loaded = load_data(path)
    assert loaded["provenance"] == runs[1]["provenance"]

    data = {k: v for k, v in runs[1].items() if k != "provenance"}
    assert read_container(path)[1] == pickle.dumps(data, protocol=5)  # stored as recorded
    assert loaded.keys() == runs[1].keys() and len(loaded["years"]) == YEARS


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"settings": {"mechanisms.cultivation": False}}, "config_hash"),
        ({"horizon": YEARS + 1}, "n_years"),
        ({"schema": 99}, "recording_schema_version"),
    ],
)
def test_mismatched_recording_is_refused_unless_replaced(
    runs: dict[int, dict[str, Any]], tmp_path: Path, change: dict[str, Any], reason: str
) -> None:
    _write(tmp_path, runs[1])
    other = _probe()
    path, horizon, settings = other.MVP2_2[PRESSURE]
    other.MVP2_2[PRESSURE] = (
        path,
        change.get("horizon", horizon),
        change.get("settings", settings),
    )
    other.SCHEMA = change.get("schema", other.SCHEMA)
    with pytest.raises(SystemExit, match=reason):
        to_record(tmp_path, [(PRESSURE, 1)], other.ident_of, False)
    assert to_record(tmp_path, [(PRESSURE, 1)], other.ident_of, True) == [(PRESSURE, 1)]


def test_a_correct_looking_filename_is_not_enough(
    probe: Any, runs: dict[int, dict[str, Any]], tmp_path: Path
) -> None:
    _write(tmp_path, runs[1], f"{PRESSURE}_2.pkl")  # seed 1 under seed 2's name
    with pytest.raises(SystemExit, match="seed: recorded 1, expected 2"):
        to_record(tmp_path, [(PRESSURE, 2)], probe.ident_of, False)
    _write(tmp_path, runs[1], "neolithic_1.pkl")  # another scenario's name
    with pytest.raises(SystemExit, match="run: recorded 'pressure"):
        to_record(tmp_path, [("neolithic", 1)], probe.ident_of, False)


def test_changed_source_or_probe_is_detected(
    probe: Any, runs: dict[int, dict[str, Any]], tmp_path: Path, capsys: Any
) -> None:
    data = {k: v for k, v in runs[1].items() if k != "provenance"}
    for key in ("source_tree_sha256", "probe_sha256"):
        write_recording(
            tmp_path / f"{PRESSURE}_1.pkl", {**runs[1]["provenance"], key: "0" * 64}, data
        )
        with pytest.raises(SystemExit, match=key):  # never reused for recording
            to_record(tmp_path, [(PRESSURE, 1)], probe.ident_of, False)
        select_runs(tmp_path, [PRESSURE], [1], True, probe.ident_of)  # analysable, but flagged
        assert "DIFFERS FROM CHECKED-OUT CODE" in capsys.readouterr().out
    _write(tmp_path, runs[2])  # seed 2 from the current source, seed 1 from another
    with pytest.raises(RecordingError, match="different sources"):
        select_runs(tmp_path, [PRESSURE], [1, 2], True, probe.ident_of)


def test_missing_or_malformed_provenance_is_refused(
    probe: Any, runs: dict[int, dict[str, Any]], tmp_path: Path
) -> None:
    path = tmp_path / f"{PRESSURE}_1.pkl"
    prov = {k: v for k, v in runs[1]["provenance"].items() if k != "config_hash"}
    write_recording(path, prov, {"name": PRESSURE, "seed": 1})
    with pytest.raises(SystemExit, match="config_hash: recorded None"):
        to_record(tmp_path, [(PRESSURE, 1)], probe.ident_of, False)
    with path.open("wb") as f:
        pickle.dump({"format": "madexplorer-probe-recording/1", "data": b""}, f)
    with pytest.raises(RecordingError, match="malformed"):
        read_container(path)
    bad = {**runs[1]["provenance"], "neutrality": {"neutral": False}}
    write_recording(path, bad, {"name": PRESSURE, "seed": 1})
    assert "observer neutrality not established" in problems(bad, probe.ident_of(PRESSURE, 1))


def test_corrupt_or_truncated_recording_is_refused(
    probe: Any, runs: dict[int, dict[str, Any]], tmp_path: Path
) -> None:
    path = _write(tmp_path, runs[1])
    raw = path.read_bytes()
    path.write_bytes(raw[: len(raw) // 2])  # truncated copy
    with pytest.raises(RecordingError, match="unreadable"):
        read_container(path)
    with pytest.raises(SystemExit, match="unreadable"):
        to_record(tmp_path, [(PRESSURE, 1)], probe.ident_of, False)
    path.write_bytes(raw)
    middle = raw.index(read_container(path)[1]) + len(raw) // 4  # inside the data blob
    path.write_bytes(raw[:middle] + bytes([raw[middle] ^ 1]) + raw[middle + 1 :])
    with pytest.raises(RecordingError, match="checksum mismatch"):
        read_container(path)


def test_interrupted_write_leaves_no_recording(
    runs: dict[int, dict[str, Any]], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def crash(*_: Any) -> None:
        raise KeyboardInterrupt  # killed before the rename

    monkeypatch.setattr(os, "replace", crash)
    with pytest.raises(KeyboardInterrupt):
        _write(tmp_path, runs[1])
    assert list(tmp_path.iterdir()) == []  # neither a final file nor a temporary one
    (tmp_path / f".{PRESSURE}_1.pkl.123.tmp").write_bytes(b"partial")  # a killed process
    assert list(tmp_path.glob("*.pkl")) == []  # never mistaken for a recording


def test_legacy_recordings_only_under_the_declared_policy(
    probe: Any, runs: dict[int, dict[str, Any]], tmp_path: Path, capsys: Any
) -> None:
    legacy = {k: v for k, v in runs[1].items() if k != "provenance"}
    with (tmp_path / f"{PRESSURE}_1.pkl").open("wb") as f:
        pickle.dump(legacy, f)  # the pre-6B-P2 format
    with pytest.raises(LegacyRecording):
        read_container(tmp_path / f"{PRESSURE}_1.pkl")
    with pytest.raises(RecordingError, match="legacy-unverified"):
        select_runs(tmp_path, [PRESSURE], [1], True, probe.ident_of)
    with pytest.raises(SystemExit, match="no provenance"):  # never reused for recording
        to_record(tmp_path, [(PRESSURE, 1)], probe.ident_of, False)
    paths = select_runs(tmp_path, [PRESSURE], [1], True, probe.ident_of, legacy=True)
    assert "PROVENANCE UNVERIFIED" in capsys.readouterr().out
    assert load_data(paths[0], legacy=True)["provenance"] is None
    _write(tmp_path, runs[2])
    with pytest.raises(RecordingError, match="mixed"):
        select_runs(tmp_path, [PRESSURE], [1, 2], True, probe.ident_of, legacy=True)


def test_analysis_selects_exactly_the_requested_runs(
    probe: Any, runs: dict[int, dict[str, Any]], tmp_path: Path, capsys: Any
) -> None:
    for run in runs.values():
        _write(tmp_path, run)
    assert [p.name for p in select_runs(tmp_path, [PRESSURE], [1], True, probe.ident_of)] == [
        f"{PRESSURE}_1.pkl"
    ]
    assert "ignored (not requested)" in capsys.readouterr().out
    with pytest.raises(RecordingError, match=r"missing run \('pressure\+cult', 3\)"):
        select_runs(tmp_path, [PRESSURE], [1, 2, 3], False, probe.ident_of)
    with pytest.raises(RecordingError, match="unexpected run"):  # not requested, no subset
        select_runs(tmp_path, [PRESSURE], [1], False, probe.ident_of)
    _write(tmp_path, runs[1], "copy_of_seed_1.pkl")
    with pytest.raises(RecordingError, match="duplicate run"):
        select_runs(tmp_path, [PRESSURE], [1, 2], True, probe.ident_of)


def test_equivalent_recordings_have_identical_scientific_data(
    probe: Any, runs: dict[int, dict[str, Any]], tmp_path: Path
) -> None:
    again = probe.record_job((PRESSURE, 1))
    a, b = _write(tmp_path, runs[1]), _write(tmp_path / ".." / tmp_path.name, again, "again.pkl")
    pa, pb = read_container(a), read_container(b)
    assert pa[1] == pb[1]  # data bytes identical; only metadata such as timestamps may differ
    assert {k for k in pa[0] if pa[0][k] != pb[0][k]} <= {"timestamp_utc"}


# --- state fingerprint


def test_fingerprint_is_equal_for_equivalent_states_and_backends() -> None:
    a, b, dense = _sim(), _sim(), _sim(belief_backend="dense")
    assert compare(fingerprint(a), fingerprint(b)) == []
    assert compare(fingerprint(a), fingerprint(dense)) == []  # beliefs in logical form


def test_fingerprint_does_not_mutate() -> None:
    a, b = _sim(10), _sim(10)
    streams = list(a.rng._streams)
    for _ in range(10):
        fingerprint(a)  # every year on one twin only
        assert list(a.rng._streams) == streams  # no stream created
        a.step()
        b.step()
    assert compare(fingerprint(a), fingerprint(b)) == []


def test_fingerprint_detects_each_deliberate_change() -> None:
    def changed(edit: Any) -> list[str]:
        sim = _sim()
        before = fingerprint(sim)
        edit(sim)
        result: list[str] = compare(before, fingerprint(sim))
        return result

    def stock(sim: Simulator) -> None:
        sim.state.ecology.plant_stock_kcal[0] += 1.0

    def tie(sim: Simulator) -> None:
        unit = next(u for u in sim.state.units.values() if u.trade_ties)
        partner = next(iter(unit.trade_ties))
        unit.trade_ties[partner] += 1e-9

    def belief(sim: Simulator) -> None:
        unit = next(iter(sim.state.units.values()))
        store, slot = sim.state.belief_store, belief_slot(unit)
        cells, year, food, population, hops = store.entries(slot)
        k = int(np.argmax(year))  # a current entry
        store.scatter(np.array([slot]), cells[k : k + 1], year[k : k + 1],
                      food[k : k + 1] * 2, population[k : k + 1], hops[k : k + 1])  # fmt: skip

    def cohort(sim: Simulator) -> None:
        unit = next(iter(sim.state.units.values()))
        females = unit.females
        females[0] += 1
        unit.females = females

    def stores(sim: Simulator) -> None:
        next(iter(sim.state.units.values())).stores_kcal += 1.0

    def identity(sim: Simulator) -> None:
        sim.ids.next("u")  # an id allocated without a unit

    def lifecycle(sim: Simulator) -> None:
        sim.events.emit(sim.state.year, "unit_extinct", unit_id="u1")

    assert changed(stock) == ["ecology"]
    assert changed(tie) == ["unit.trade_ties"]
    assert changed(belief) == ["unit.beliefs"]
    assert changed(cohort) == ["unit.females"]
    assert changed(stores) == ["unit.stores_kcal"]
    assert changed(identity) == ["control"]
    assert changed(lifecycle) == ["control"]


def test_the_old_digest_misses_ecology_and_ties() -> None:
    sim = _sim()
    old, new = physical_digest(sim), fingerprint(sim)
    sim.state.ecology.game_stock_kcal[3] *= 0.5
    unit = next(u for u in sim.state.units.values() if u.trade_ties)
    unit.trade_ties = {}
    assert physical_digest(sim) == old  # the reason for the stronger fingerprint
    assert compare(new, fingerprint(sim)) == ["ecology", "unit.trade_ties"]


# --- observer installation and isolation


def test_hooks_touch_one_simulator_only() -> None:
    class_evaluate = ForagingSubsystem.evaluate
    sc = Scenario.from_yaml(ROOT / "scenarios/mvp2_2_pressure.yaml").with_overrides(n_years=5)
    observed, other = Simulator(sc), Simulator(sc)
    calls: list[int] = []

    def spy(sub: Any, state: Any, ctx: Any) -> Any:
        calls.append(state.year)
        return ForagingSubsystem.evaluate(sub, state, ctx)

    assert hook(observed, ForagingSubsystem, spy)
    assert not hook(observed, type("Absent", (), {}), spy)
    observed.step()
    other.step()
    assert calls == [observed.state.year]  # the other simulator was not observed
    assert ForagingSubsystem.evaluate is class_evaluate
    assert all("evaluate" not in vars(s) for s in other.pipeline)


def test_swapped_restores_on_error() -> None:
    original = agriculture_kernel.plan_fields
    with pytest.raises(RuntimeError), swapped(agriculture_kernel, "plan_fields", None):
        assert agriculture_kernel.plan_fields is None
        raise RuntimeError
    assert agriculture_kernel.plan_fields is original


def test_failing_observer_leaks_nothing(probe: Any) -> None:
    originals = (agriculture_kernel.plan_fields, migration.gather_candidates,
                 TradeSubsystem.evaluate, ForagingSubsystem.evaluate)  # fmt: skip
    sc = probe.scenario(PRESSURE, 1)
    recorder = probe.Recorder()

    def failing(sim: Simulator) -> None:
        recorder.install(sim)
        plan = next(s for s in sim.pipeline if type(s).__name__ == "FieldPlanningSubsystem")
        inner = plan.evaluate

        def broken(state: Any, ctx: Any) -> Any:
            if state.year > 3:

                def kernel(*_: Any) -> Any:
                    raise RuntimeError("observer failure")

                with swapped(agriculture_kernel, "plan_fields", kernel):
                    return inner(state, ctx)
            return inner(state, ctx)

        plan.evaluate = broken  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="observer failure"):
        run_observed(sc, failing)
    assert (agriculture_kernel.plan_fields, migration.gather_candidates,
            TradeSubsystem.evaluate, ForagingSubsystem.evaluate) == originals  # fmt: skip


def test_instrumented_then_ordinary_runs_agree(probe: Any) -> None:
    sc = probe.scenario(PRESSURE, 1)
    recorder = probe.Recorder()
    snapshots: list[bytes] = []

    def snapshot(sim: Simulator, _ctx: Any) -> None:
        if sim.state.year % 10 == 0:  # point-in-time copy of what was recorded so far
            snapshots.append(pickle.dumps(recorder.years[: len(recorder.years)]))

    observed, years, neutrality = run_observed(sc, recorder.install, snapshot, every=5)
    assert neutrality["neutral"] and neutrality["mismatches"] == []
    assert neutrality["checkpoint_years"][:2] == [
        observed.state.year - years + 5,
        observed.state.year - years + 10,
    ]
    ordinary = Simulator(sc)  # same process, after the instrumented run
    for _ in range(years):
        ordinary.step()
    assert compare(fingerprint(observed), fingerprint(ordinary)) == []
    for blob in snapshots:  # later years did not change values captured earlier
        earlier = pickle.loads(blob)
        assert pickle.dumps(recorder.years[: len(earlier)]) == blob


ENVIRONMENT_CHANGES = [
    ("python_version", "3.12.0"),
    ("numpy_version", "1.26.4"),
    ("dependency_lock_hash", "0" * 64),
    ("belief_backend", "dense"),
    ("execution.numeric_platform", "numpy=1.26.4 machine=arm64 simd=unknown"),
    ("execution.jit", False),
    ("execution.thread_limits", {"OMP_NUM_THREADS": "4"}),
]


def _with(prov: dict[str, Any], key: str, value: Any) -> dict[str, Any]:
    if key.startswith("execution."):
        return {**prov, "execution": {**prov["execution"], key.split(".")[1]: value}}
    return {**prov, key: value}


@pytest.mark.parametrize(("key", "value"), ENVIRONMENT_CHANGES)
def test_mixed_execution_environments_need_an_explicit_comparison(
    probe: Any, runs: dict[int, dict[str, Any]], tmp_path: Path, capsys: Any, key: str, value: Any
) -> None:
    _write(tmp_path, runs[1])
    data = {k: v for k, v in runs[2].items() if k != "provenance"}
    write_recording(tmp_path / f"{PRESSURE}_2.pkl", _with(runs[2]["provenance"], key, value), data)
    field = key.split(".")[-1]
    with pytest.raises(RecordingError, match=f"different execution environments \\({field}\\)"):
        select_runs(tmp_path, [PRESSURE], [1, 2], True, probe.ident_of)
    capsys.readouterr()
    select_runs(tmp_path, [PRESSURE], [1, 2], True, probe.ident_of, mixed_environments=True)
    out = capsys.readouterr().out
    assert (
        f"MIXED EXECUTION ENVIRONMENTS (explicit comparison, not one reference set): ['{field}']"
        in out
    )
    assert f"pressure+cult seed 2: {field}=" in out


def test_harmless_metadata_differences_are_permitted(
    probe: Any, runs: dict[int, dict[str, Any]], tmp_path: Path, capsys: Any
) -> None:
    _write(tmp_path, runs[1])
    prov = _with(runs[2]["provenance"], "execution.start_method", "spawn")
    prov = {**prov, "timestamp_utc": "2030-01-01T00:00:00+00:00"}
    data = {k: v for k, v in runs[2].items() if k != "provenance"}
    write_recording(tmp_path / f"{PRESSURE}_2.pkl", prov, data)
    assert len(select_runs(tmp_path, [PRESSURE], [1, 2], True, probe.ident_of)) == 2
    out = capsys.readouterr().out
    assert "one execution environment" in out and "MIXED" not in out

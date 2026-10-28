"""Recording integrity for the Stage 6B probes (MVP 3 Stage 6B-P2). Observation only.

Three things a scientific recording needs and the probes did not have:

- **Provenance.** Each recording is one pickle container, written atomically, that embeds
  its provenance and a SHA-256 of its scientific data. The provenance is
  ``core.provenance.run_manifest`` (configuration hash, source-tree hash, git state,
  dependency lock, Python and numpy) plus the probe's identity: the run key, scenario path
  and settings, requested horizon, the probe's own code hash (``probe_sha256``: the probe
  script and these two helper modules; helpers under ``src`` are in the source-tree hash),
  the recording schema version, the completed years and the neutrality check.
- **Safe reuse.** A recording is reused only if its container is intact and its identity
  matches what the checked-out code would record (:func:`problems`); analysis loads exactly
  the expected runs, once each (:func:`select_runs`). Recordings without provenance
  (before 6B-P2) load only in an explicit legacy mode and are reported as unverified.
- **Observer neutrality.** Hooks are installed on one simulator's own subsystem instances
  (:func:`hook`), never on classes; a module function a hook must replace is swapped only
  for the duration of the instrumented call (:func:`swapped`). :func:`run_observed` steps
  an uninstrumented twin in lockstep and compares :func:`fingerprint` at checkpoints.

``fingerprint`` is an audit-only reading of the state that can affect later years, one hash
per component so a mismatch names what changed. It reads authoritative storage through the
unit descriptors (table, belief store, strata table), declared field by field in
``population.fields.UNIT_FIELDS``, so no unit field can be missed. Beliefs are compared in
logical form (current entries by cell), which is backend-independent; raw storage rows are
the raw exactness oracle's business. Excluded, because no later year reads them: caches
(capability maps, reachability, step-context transients), belief-store capacity and expired
rows, unit-object caches, timings and metrics recorders (probes do not record metrics).
"""

import dataclasses
import hashlib
import json
import multiprocessing
import os
import pickle
import types
from collections import deque
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import numpy as np

from madexplorer.config.loader import Scenario
from madexplorer.core import jit
from madexplorer.core.provenance import numeric_platform, run_manifest, source_tree_hash
from madexplorer.core.simulation import Simulator
from madexplorer.experiments.ensemble import THREAD_VARIABLES
from madexplorer.population.familiarity import FamiliarityMap
from madexplorer.population.fields import UNIT_FIELDS, Storage
from madexplorer.population.strata import StrataBlock
from madexplorer.population.unit import belief_slot

FORMAT = "madexplorer-probe-recording/1"  # the container (this module); schemas are per probe
FINGERPRINT_VERSION = 1
CHECKPOINT_YEARS = 25  # lockstep comparison interval (plus the final year)
HELPERS = (Path(__file__).with_name("_common.py"), Path(__file__))
# Identity keys that must equal what the checked-out code would record.
SCIENTIFIC_KEYS = (
    "probe",
    "recording_schema_version",
    "run",
    "scenario_path",
    "settings",
    "seed",
    "world_seed",
    "n_years",
    "config_hash",
)
SOURCE_KEYS = ("source_tree_sha256", "probe_sha256")
# Execution context that can change numerical results or their raw representation: runs of
# one analysis must agree on all of it unless a mixed comparison is requested explicitly.
# Not compared: timestamp_utc, durations, start_method (serial and parallel recordings are
# bit-identical, review §16), git_dirty (the source hashes identify the code).
ENVIRONMENT_KEYS = ("python_version", "numpy_version", "dependency_lock_hash", "belief_backend")
EXECUTION_KEYS = ("numeric_platform", "jit", "thread_limits")


class RecordingError(Exception):
    """A recording is unreadable, malformed or does not belong where it is used."""


class LegacyRecording(RecordingError):
    """A recording written before 6B-P2: no provenance, nothing can be verified."""


# ---------------------------------------------------------------- provenance


def probe_sha256(script: str | Path) -> str:
    """SHA-256 over the probe script and the probe helper modules (name and content)."""
    digest = hashlib.sha256()
    for path in (Path(script), *HELPERS):
        digest.update(path.name.encode() + b"\0" + path.read_bytes())
    return digest.hexdigest()


def identity(
    probe: str,
    schema: int,
    run: str,
    scenario: Scenario,
    path: str,
    settings: dict[str, Any],
    script: str | Path,
) -> dict[str, Any]:
    """What a recording of ``run`` made now by this code would declare."""
    config = scenario.config
    return {
        "probe": probe,
        "recording_schema_version": schema,
        "run": run,
        "scenario_path": path,
        "settings": json.loads(json.dumps(settings, sort_keys=True)),
        "seed": config.simulation.seed,
        "world_seed": config.world.topology.seed,
        "n_years": config.simulation.n_years,
        "config_hash": scenario.config_hash(),
        "source_tree_sha256": source_tree_hash(),
        "probe_sha256": probe_sha256(script),
    }


def provenance(
    ident: dict[str, Any], scenario: Scenario, years_completed: int, neutrality: dict[str, Any]
) -> dict[str, Any]:
    """Full provenance of a finished recording (``run_manifest`` + identity + outcome)."""
    execution = {
        "numeric_platform": numeric_platform(),
        "jit": jit.ENABLED,
        "start_method": multiprocessing.get_start_method(allow_none=True),
        "thread_limits": {name: os.environ.get(name) for name in THREAD_VARIABLES},
    }
    return {
        **run_manifest(scenario, execution=execution),
        **ident,
        "years_completed": years_completed,
        "neutrality": neutrality,
    }


def problems(prov: dict[str, Any], ident: dict[str, Any], *, source: bool = True) -> list[str]:
    """Why a recording's provenance does not match ``ident`` (empty: it matches).

    ``source=False`` skips the source and probe hashes (analysis of an older, consistent
    recording set; reported separately by :func:`select_runs`).
    """
    keys = SCIENTIFIC_KEYS + (SOURCE_KEYS if source else ())
    found = [
        f"{k}: recorded {prov.get(k)!r}, expected {ident[k]!r}"
        for k in keys
        if prov.get(k) != ident[k]
    ]
    years = prov.get("years_completed")
    if not isinstance(years, int) or not 0 < years <= ident["n_years"]:
        found.append(f"years_completed {years!r} outside 1..{ident['n_years']}")
    if not (prov.get("neutrality") or {}).get("neutral"):
        found.append("observer neutrality not established")
    return found


# ---------------------------------------------------------------- the container


def write_recording(path: Path, prov: dict[str, Any], data: dict[str, Any]) -> None:
    """Write atomically: a temporary file in the same directory, fsync, then rename. An
    interrupted write leaves at most a ``.*.tmp`` file, never a file under ``path``."""
    blob = pickle.dumps(data, protocol=5)
    outer = {
        "format": FORMAT,
        "provenance": prov,
        "data_sha256": hashlib.sha256(blob).hexdigest(),
        "data": blob,
    }
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with tmp.open("wb") as f:
            pickle.dump(outer, f, protocol=5)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def read_container(path: Path) -> tuple[dict[str, Any], bytes]:
    """``(provenance, data bytes)`` of an intact recording; the data is not unpickled.

    Only open recordings you made: unpickling runs code from the file.
    """
    try:
        with path.open("rb") as f:
            outer = pickle.load(f)
    except Exception as error:  # truncated, garbage, missing classes, ...
        raise RecordingError(
            f"{path.name}: unreadable, corrupt or incomplete ({error!r})"
        ) from None
    if not isinstance(outer, dict) or "format" not in outer:
        raise LegacyRecording(f"{path.name}: no provenance (recorded before 6B-P2)")
    if outer["format"] != FORMAT:
        raise RecordingError(
            f"{path.name}: container format {outer['format']!r}, expected {FORMAT!r}"
        )
    prov, blob, digest = outer.get("provenance"), outer.get("data"), outer.get("data_sha256")
    if not isinstance(prov, dict) or not isinstance(blob, bytes) or not isinstance(digest, str):
        raise RecordingError(
            f"{path.name}: malformed container (provenance, data or checksum missing)"
        )
    if hashlib.sha256(blob).hexdigest() != digest:
        raise RecordingError(f"{path.name}: data checksum mismatch (corrupt)")
    return prov, blob


def load_data(path: Path, legacy: bool = False) -> dict[str, Any]:
    """The scientific data of a recording (checksum verified), with ``provenance`` attached
    (``None`` for a legacy recording, which loads only when ``legacy`` is set)."""
    try:
        prov, blob = read_container(path)
    except LegacyRecording:
        if not legacy:
            raise
        with path.open("rb") as f:
            run: dict[str, Any] = pickle.load(f)
        run["provenance"] = None
        return run
    run = pickle.loads(blob)
    run["provenance"] = prov
    return run


# ---------------------------------------------------------------- reuse and selection


def to_record(
    out: Path,
    specs: Sequence[tuple[str, int]],
    ident_of: Callable[[str, int], dict[str, Any]],
    replace: bool,
) -> list[tuple[str, int]]:
    """The runs still to record into ``out``. An existing recording is skipped only if it
    is intact and matches; anything else stops the command unless ``replace`` is set."""
    todo, refused = [], []
    for name, seed in specs:
        path = out / f"{name}_{seed}.pkl"
        if not path.exists():
            todo.append((name, seed))
            continue
        try:
            found = problems(read_container(path)[0], ident_of(name, seed))
        except RecordingError as error:
            found = [str(error)]
        if not found:
            print(f"valid recording kept: {path}")
        elif replace:
            print(f"replacing {path}: {'; '.join(found)}")
            todo.append((name, seed))
        else:
            refused.append(f"{path}: {'; '.join(found)}")
    if refused:
        raise SystemExit(
            "existing recordings do not match (use --replace to overwrite them):\n  "
            + "\n  ".join(refused)
        )
    return todo


def select_runs(
    load: Path,
    names: Sequence[str],
    seeds: Sequence[int],
    explicit: bool,
    ident_of: Callable[[str, int], dict[str, Any]],
    legacy: bool = False,
    mixed_environments: bool = False,
) -> list[Path]:
    """The recordings to analyse: exactly one per requested ``(name, seed)``, validated.

    Raises :class:`RecordingError` listing every problem: unreadable or malformed files,
    legacy files without ``legacy``, duplicates, unexpected runs, missing runs, identities
    that differ from what this code records, or runs from different sources. Runs outside an
    ``explicit`` seed subset are ignored (and listed). Runs from different execution
    environments (:func:`environment`) are an error unless ``mixed_environments`` asks for an
    explicit comparison, which is then labelled. Prints the exact set analysed.
    """
    wanted = {(n, s) for n in names for s in seeds}
    errors, found, ignored = [], {}, []
    for path in sorted(load.glob("*.pkl")):
        try:
            prov: dict[str, Any] | None = read_container(path)[0]
            key = (prov["run"], prov["seed"])
        except LegacyRecording as error:
            if not legacy:
                errors.append(f"{error}; pass --legacy-unverified to analyse it unverified")
                continue
            run = load_data(path, legacy=True)
            prov, key = None, (run["name"], run["seed"])
        except (RecordingError, KeyError) as error:
            errors.append(str(error))
            continue
        if key in found:
            errors.append(f"duplicate run {key}: {found[key][0].name} and {path.name}")
        elif key not in wanted:
            if explicit and key[0] in names:
                ignored.append(path.name)
            else:
                errors.append(f"unexpected run {key} in {path.name}")
        else:
            found[key] = (path, prov)
    errors += [
        f"missing run {k} (use --seeds to analyse an explicit subset)"
        for k in sorted(wanted - set(found))
    ]
    provs = {k: p for k, (_, p) in found.items()}
    verified = [k for k, p in provs.items() if p is not None]
    if verified and len(verified) != len(provs):
        errors.append("legacy and verified recordings mixed in one analysis")
    for k in verified:
        errors += [f"{k}: {x}" for x in problems(provs[k], ident_of(*k), source=False)]
    sources = {tuple(provs[k][x] for x in (*SOURCE_KEYS, "git_commit")) for k in verified}
    if len(sources) > 1:
        errors.append(f"runs come from {len(sources)} different sources or probe versions")
    envs = {k: environment(provs[k]) for k in verified}
    differing = sorted(
        {x for e in envs.values() for x in e if len({str(v[x]) for v in envs.values()}) > 1}
    )
    if differing and not mixed_environments:
        errors.append(
            f"runs come from different execution environments ({', '.join(differing)}); "
            "pass --mixed-environments to compare them explicitly"
        )
    if errors:
        raise RecordingError("cannot analyse these recordings:\n  " + "\n  ".join(errors))
    current = ident_of(*sorted(found)[0]) if found else {}
    print(
        f"analysing {len(found)} runs from {load}"
        + (f"; ignored (not requested) {ignored}" if ignored else "")
    )
    for key in sorted(found):
        path, prov = found[key]
        if prov is None:
            print(
                f"  {key[0]} seed {key[1]}: {path.name}  PROVENANCE UNVERIFIED (legacy recording)"
            )
            continue
        same = all(prov[x] == current[x] for x in SOURCE_KEYS)
        print(
            f"  {key[0]} seed {key[1]}: {path.name}  "
            f"{prov['years_completed']}/{prov['n_years']} y, "
            f"commit {str(prov['git_commit'])[:10]}{' (dirty)' if prov['git_dirty'] else ''}, "
            f"source {'= checked out' if same else 'DIFFERS FROM CHECKED-OUT CODE'}, "
            f"recorded {prov['timestamp_utc']}"
        )
    if verified:
        method = provs[verified[0]]["neutrality"]["method"]
        print(f"  identities and config hashes verified; observers neutral ({method})")
    if differing:
        print(
            "  MIXED EXECUTION ENVIRONMENTS (explicit comparison, not one reference set): "
            f"{differing}"
        )
        for k in sorted(envs):
            print(f"    {k[0]} seed {k[1]}: " + ", ".join(f"{x}={envs[k][x]}" for x in differing))
    elif verified:
        e = envs[verified[0]]
        print(
            f"  one execution environment: python {e['python_version']}, "
            f"numpy {e['numpy_version']}, "
            f"beliefs {e['belief_backend']}, jit {e['jit']}, {e['numeric_platform']}"
        )
    return [found[k][0] for k in sorted(found)]


def environment(prov: dict[str, Any]) -> dict[str, Any]:
    """The execution context of a recording that runs in one analysis must share."""
    execution = prov.get("execution") or {}
    return {
        **{k: prov.get(k) for k in ENVIRONMENT_KEYS},
        **{k: execution.get(k) for k in EXECUTION_KEYS},
    }


# ---------------------------------------------------------------- observers


def hook(sim: Simulator, kind: type, wrapper: Callable[..., Any]) -> bool:
    """Replace ``evaluate`` on ``sim``'s own ``kind`` subsystem instance (the class and other
    simulators are untouched). ``wrapper(sub, state, ctx)``; False if not in the pipeline."""
    subs = [s for s in sim.pipeline if type(s) is kind]
    if not subs:
        return False
    (sub,) = subs
    sub.evaluate = types.MethodType(wrapper, sub)  # type: ignore[method-assign]
    return True


@contextmanager
def swapped(owner: Any, name: str, replacement: Any) -> Iterator[Any]:
    """``owner.name = replacement`` for the duration of the block, restored on any exit.

    For module functions a hook must observe (single-threaded: nothing else runs meanwhile).
    """
    original = getattr(owner, name)
    setattr(owner, name, replacement)
    try:
        yield original
    finally:
        setattr(owner, name, original)


def run_observed(
    scenario: Scenario,
    observe: Callable[[Simulator], None],
    after_step: Callable[[Simulator, Any], None] | None = None,
    every: int = CHECKPOINT_YEARS,
) -> tuple[Simulator, int, dict[str, Any]]:
    """Run ``scenario`` with ``observe(sim)``'s hooks and an uninstrumented twin in lockstep.

    The twin is compared with :func:`fingerprint` every ``every`` years and at the last
    year (and with the older ``_common.physical_digest`` at the end). Returns the instrumented
    simulator, the years completed and the neutrality record.
    """
    from _common import physical_digest

    sim, plain = Simulator(scenario), Simulator(scenario)
    observe(sim)
    checked, mismatches = [], []
    years, horizon = 0, scenario.config.simulation.n_years
    for years in range(1, horizon + 1):
        ctx = sim.step()
        plain.step()
        if after_step is not None:
            after_step(sim, ctx)
        last = years == horizon or not sim.state.units or not plain.state.units
        if years % every == 0 or last:
            checked.append(sim.state.year)
            differ = compare(fingerprint(sim), fingerprint(plain))
            if differ:
                mismatches.append((sim.state.year, differ))
        if last:
            break
    legacy = physical_digest(sim) == physical_digest(plain)
    neutral = not mismatches and legacy
    return (
        sim,
        years,
        {
            "neutral": neutral,
            "method": f"state_fingerprint/{FINGERPRINT_VERSION}",
            "checkpoint_years": checked,
            "mismatches": mismatches,
            "physical_digest_equal": legacy,
        },
    )


# ---------------------------------------------------------------- state fingerprint


def _update(h: Any, value: Any) -> None:
    """Feed one value into ``h`` canonically (type-tagged; mappings by sorted key)."""
    if isinstance(value, np.ndarray):
        h.update(f"a{value.dtype.str}{value.shape}".encode())
        h.update(np.ascontiguousarray(value).tobytes())
    elif isinstance(value, dict):
        h.update(f"d{len(value)}".encode())
        for key in sorted(value, key=repr):
            _update(h, key)
            _update(h, value[key])
    elif isinstance(value, (list, tuple, deque)):
        h.update(f"l{len(value)}".encode())
        for item in value:
            _update(h, item)
    elif isinstance(value, (set, frozenset)):
        _update(h, sorted(value, key=repr))
    elif isinstance(value, FamiliarityMap):
        _update(h, (value._value, value._year))
    elif isinstance(value, StrataBlock):
        _update(h, (value.columns, value.stratum_id))
    elif dataclasses.is_dataclass(value) and not isinstance(value, type):
        _update(h, {f.name: getattr(value, f.name) for f in dataclasses.fields(value)})
    elif value is None or isinstance(value, (bool, int, float, str, np.generic)):
        h.update(f"{type(value).__name__}:{value!r};".encode())
    else:
        raise TypeError(f"fingerprint: no canonical form for {type(value).__name__}")


def _logical_beliefs(sim: Simulator, unit: Any) -> tuple[np.ndarray, ...]:
    """A unit's current belief entries by ascending cell (any backend)."""
    memory = sim.scenario.species[unit.species_id].cognition.memory_years
    cells, year, food, population, hops = sim.state.belief_store.entries(belief_slot(unit))
    keep = year > sim.state.year - memory
    order = np.argsort(cells[keep], kind="stable")
    return tuple(a[keep][order] for a in (cells.astype(np.int64), year, food, population, hops))


def fingerprint(sim: Simulator) -> dict[str, str]:
    """Component hashes of everything a later year can read (see the module docstring).

    Read-only: reads RNG states without creating streams, beliefs through the store's
    entries, unit fields through their descriptors (copies).
    """
    state, population = sim.state, sim.state.population
    parts: dict[str, Any] = {
        "control": {
            "year": state.year,
            "ids": sim.ids._counters,
            "rng": {n: g.bit_generator.state for n, g in sim.rng._streams.items()},
            "events": [
                (e.year, e.kind, json.dumps(e.data, sort_keys=True, default=repr))
                for e in sim.events
            ],
            "events_enabled": sim.events.enabled,
        },
        "world": state.world,
        "climate": state.climate,
        "ecology": state.ecology,
        "strata_store": {
            "next_id": population._next_stratum_id,
            "log": json.dumps(population.strata_log, default=repr),
            "flows": json.dumps(population.strata_flows, default=repr),
        },
        "storage": {"free": population._free, "next": population._next_slot},
    }
    units = list(state.units.values())
    out = {name: _digest(value) for name, value in parts.items()}
    out["unit.order"] = _digest([u.id for u in units])
    for spec in UNIT_FIELDS:
        if spec.name == "id":
            continue
        if spec.storage is Storage.BELIEFS:
            values = [_logical_beliefs(sim, u) for u in units]
        else:
            values = [getattr(u, spec.name) for u in units]
        out[f"unit.{spec.name}"] = _digest(values)
    return out


def _digest(value: Any) -> str:
    h = hashlib.sha256()
    _update(h, value)
    return h.hexdigest()


def compare(a: dict[str, str], b: dict[str, str]) -> list[str]:
    """Components whose hashes differ (or exist on one side only)."""
    return sorted(k for k in a.keys() | b.keys() if a.get(k) != b.get(k))

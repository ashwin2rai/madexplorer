"""PH5 equal-age steady-state timing at fixed density.

usage: ph5_steady.py <units> <width> <warm ticks> <timed ticks> (MADEXPLORER_BELIEFS=sparse)
"""

import sys
import time

sys.path.insert(0, ".")
import numpy as np

from madexplorer.config.loader import Scenario
from madexplorer.experiments.benchmark import synthetic_simulator, warm_kernels, warm_up_beliefs

n, w, warm, timed = map(int, sys.argv[1:5])
sc = Scenario.from_yaml("scenarios/mvp2_neolithic.yaml").with_settings(
    {"world.topology.width": w, "world.topology.height": w}
)
sim = synthetic_simulator(sc, n)
warm_up_beliefs(sim, 20)
warm_kernels(sim)


def origins():
    return sum(len(m._reachable) for m in sim.static.movement.values())


for _ in range(warm):
    sim.step()
o0 = origins()
sim.timings = {}
cpu = []
counts = []
for _ in range(timed):
    counts.append(len(sim.state.units))
    c = time.process_time()
    sim.step()
    cpu.append(time.process_time() - c)
sub = sim.timings
t = sum(sub.values())
mean_cpu = float(np.mean(cpu))
print(
    f"{n} on {w}x{w}, {warm} warm ticks: cpu {1000 * mean_cpu:.0f} ms/tick, "
    f"{1e6 * mean_cpu / np.mean(counts):.1f} us/unit/tick; "
    f"new origins during timed ticks {origins() - o0} (cached {origins()})"
)
print(
    "   ms/tick:",
    {k: round(1000 * v / timed) for k, v in sorted(sub.items(), key=lambda kv: -kv[1])[:12]},
    "units",
    int(np.mean(counts)),
    "trade edges",
    sum(len(u.trade_ties) for u in sim.state.units.values()),
    "fam entries",
    sum(len(u.familiarity) for u in sim.state.units.values()),
)

"""madexplorer: a mechanism-based social-ecological civilization simulator.

Minimal API::

    from madexplorer import Scenario, Simulator

    scenario = Scenario.from_yaml("scenarios/mvp1_sandbox.yaml")
    result = Simulator(scenario).run()
    result.save("runs/experiment_001")
"""

from madexplorer.config.loader import Scenario
from madexplorer.core.simulation import SimulationResult, Simulator

__all__ = ["Scenario", "SimulationResult", "Simulator"]

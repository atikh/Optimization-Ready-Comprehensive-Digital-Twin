"""Regression test for output-transition label resolution."""

from dataclasses import dataclass
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SIMULATION_DIR = PROJECT_ROOT / "02- Simulation"
if str(SIMULATION_DIR) not in sys.path:
    sys.path.insert(0, str(SIMULATION_DIR))

from kpi_eval import _output_transition_names, _parse_io_summary


@dataclass
class Objective:
    name: str
    transition_ids: tuple[str, ...]


@dataclass
class Spec:
    objectives: tuple[Objective, ...]


class DummyTransition:
    def __init__(self, transition_id: str, label: str):
        self.mdpnml_id = transition_id
        self.mdpnml_name = label
        self.output_transition = True


class DummyModel:
    transitions_by_id = {
        "t8": DummyTransition("t8", "ReWork Completed"),
        "t10": DummyTransition("t10", "MAG1 Completed"),
        "t15": DummyTransition("t15", "MAG2 Completed"),
    }


def main() -> None:
    spec = Spec((Objective("outputs", ("t8", "t10", "t15")),))
    names = _output_transition_names(DummyModel(), spec)
    assert names == {"ReWork Completed", "MAG1 Completed", "MAG2 Completed"}

    console = """
Input value for New Task : 100
Output value for MAG1 Completed : 40
Output value for MAG2 Completed : 45
Output value for ReWork Completed : 10
"""
    inputs, outputs = _parse_io_summary(console, names)
    assert inputs == 100.0
    assert outputs == 95.0
    print("Output-name mapping regression test passed.")


if __name__ == "__main__":
    main()

"""Test exact-name mapping without requiring the MDPySPN components package."""

from pathlib import Path
import sys
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PREPARE_DIR = PROJECT_ROOT / "01- Prepare MDPNML"
SIMULATION_DIR = PROJECT_ROOT / "02- Simulation"
for path in (PREPARE_DIR, SIMULATION_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from prepare_mdpnml import prepare_optimization_model
from optimization_metadata import load_optimization_spec


def main() -> None:
    with TemporaryDirectory() as temp:
        result = Path(temp) / "ready.pnml"
        report = Path(temp) / "report.csv"
        prepare_optimization_model(
            PROJECT_ROOT / "01- Prepare MDPNML" / "MDPNML.pnml",
            PROJECT_ROOT / "01- Prepare MDPNML" / "optimization_parameters.json",
            result,
            report,
        )
        spec = load_optimization_spec(result)
        assert spec.names == [
            "tau_robot1", "tau_robot2", "tau_mag1", "tau_mag2",
            "tau_remag", "w_robot1", "w_mag1"
        ]
        assert len(spec.objectives) == 3
        assert report.exists()
    print("Raw-to-optimization-ready mapping test passed.")


if __name__ == "__main__":
    main()

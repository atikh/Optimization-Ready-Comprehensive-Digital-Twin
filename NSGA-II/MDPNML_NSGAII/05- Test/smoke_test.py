"""Fast two-policy simulation test before launching the full NSGA-II experiment."""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SIMULATION_DIR = PROJECT_ROOT / "02- Simulation"
if str(SIMULATION_DIR) not in sys.path:
    sys.path.insert(0, str(SIMULATION_DIR))

from kpi_eval import eval_candidate, make_replication_seeds
from optimization_metadata import load_optimization_spec

PNML_PATH = PROJECT_ROOT / "01- Prepare MDPNML" / "MDPNML_optimization_ready.pnml"


def main() -> None:
    spec = load_optimization_spec(PNML_PATH)
    baseline = spec.baseline_vector
    changed = list(baseline)

    name_to_index = {name: index for index, name in enumerate(spec.names)}
    changed[name_to_index["w_robot1"]] = 0.75
    changed[name_to_index["w_mag1"]] = 0.25
    changed[name_to_index["tau_robot1"]] = 2.0

    seeds = make_replication_seeds(20260717, 2)
    baseline_metrics = eval_candidate(
        baseline, pnml_path=PNML_PATH, replication_seeds=seeds
    )
    changed_metrics = eval_candidate(
        changed, pnml_path=PNML_PATH, replication_seeds=seeds
    )

    print("Variables:", spec.names)
    print("Baseline vector:", baseline)
    print("Changed vector:", changed)
    print("Baseline metrics:", baseline_metrics)
    print("Changed metrics:", changed_metrics)


if __name__ == "__main__":
    main()

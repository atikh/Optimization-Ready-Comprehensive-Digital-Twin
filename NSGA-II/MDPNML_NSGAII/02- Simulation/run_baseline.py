"""Run one baseline simulation using the optimization-ready MDPNML."""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SIMULATION_DIR = Path(__file__).resolve().parent
if str(SIMULATION_DIR) not in sys.path:
    sys.path.insert(0, str(SIMULATION_DIR))
from bootstrap import ensure_mdpyspn_on_path
ensure_mdpyspn_on_path()
from components.spn_simulate import simulate  # noqa: E402
from components.spn_visualization import draw_spn  # noqa: E402
from optimization_metadata import load_optimization_spec  # noqa: E402
from model_factory import build_spn_from_mdpnml  # noqa: E402

PNML_PATH = PROJECT_ROOT / "01- Prepare MDPNML" / "MDPNML_optimization_ready.pnml"

def main() -> None:
    (PROJECT_ROOT / "04- Outputs").mkdir(parents=True, exist_ok=True)
    spec = load_optimization_spec(PNML_PATH)
    baseline_policy = {p.name: p.baseline for p in spec.parameters}
    model = build_spn_from_mdpnml(policy=baseline_policy, pnml_path=PNML_PATH, verbose=True)
    simulate(model, max_time=spec.horizon, verbosity=1, protocol=str(PROJECT_ROOT / "04- Outputs" / "baseline_event_log.csv"))
    draw_spn(model, show=False, rankdir="LR")

if __name__ == "__main__":
    main()

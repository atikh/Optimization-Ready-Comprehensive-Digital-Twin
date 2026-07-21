"""One-command entry point for MDPNML preparation and NSGA-II.

Running this file performs two steps in order:
1. Convert the latest raw ``01- Prepare MDPNML/MDPNML.pnml`` into the
   optimization-ready model using ``optimization_parameters.json``.
2. Start the three-objective NSGA-II optimization.

Any command-line options such as ``--population`` or ``--generations`` are
left in ``sys.argv`` and are read by ``run_nsga2_core.py``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
PREPARE_SCRIPT = PROJECT_ROOT / "01- Prepare MDPNML" / "prepare_mdpnml.py"
SIMULATION_DIR = PROJECT_ROOT / "02- Simulation"
NSGA_COMPONENTS_DIR = PROJECT_ROOT / "03- NSGA-II Components"


def prepare_mdpnml() -> None:
    """Generate a fresh optimization-ready MDPNML before optimization."""
    if not PREPARE_SCRIPT.is_file():
        raise FileNotFoundError(f"Preparation script was not found: {PREPARE_SCRIPT}")

    print("=" * 72)
    print("STEP 1/2: Preparing the latest MDPNML model")
    print("=" * 72)
    subprocess.run(
        [sys.executable, str(PREPARE_SCRIPT)],
        cwd=str(PROJECT_ROOT),
        check=True,
    )


def run_optimization() -> None:
    """Load and run the NSGA-II core after preparation succeeds."""
    for folder in (SIMULATION_DIR, NSGA_COMPONENTS_DIR):
        if str(folder) not in sys.path:
            sys.path.insert(0, str(folder))

    from run_nsga2_core import main  # imported only after preparation

    print("\n" + "=" * 72)
    print("STEP 2/2: Running three-objective NSGA-II")
    print("=" * 72)
    main()


if __name__ == "__main__":
    prepare_mdpnml()
    run_optimization()

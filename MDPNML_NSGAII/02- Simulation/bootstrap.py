"""Locate the user's MDPySPN package without hard-coding one machine path."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def ensure_mdpyspn_on_path() -> Path:
    """Return a directory that contains ``components`` and add it to sys.path.

    Search order:
    1. MDPYSPN_ROOT environment variable.
    2. This project directory and each parent directory.
    3. Common sibling directory names next to this project.

    Raises a clear error when the simulator package is unavailable.
    """
    here = Path(__file__).resolve().parent
    candidates: list[Path] = []

    env_root = os.getenv("MDPYSPN_ROOT")
    if env_root:
        candidates.append(Path(env_root).expanduser().resolve())

    candidates.extend([here, *here.parents])
    for parent in [here, *here.parents]:
        candidates.extend(
            [
                parent / "MDPySPN-main",
                parent / "MDPySPN",
                parent / "mdpyspn",
            ]
        )

    seen: set[Path] = set()
    for candidate in candidates:
        try:
            candidate = candidate.resolve()
        except OSError:
            continue
        if candidate in seen:
            continue
        seen.add(candidate)
        if (candidate / "components" / "spn.py").is_file() and (candidate / "components" / "spn_simulate.py").is_file():
            if str(candidate) not in sys.path:
                sys.path.insert(0, str(candidate))
            return candidate

    raise ModuleNotFoundError(
        "Could not find a complete MDPySPN components package. Copy the "
        "contents of your original components folder into "
        "'02- Simulation/components', or set MDPYSPN_ROOT to a directory "
        "that contains components/spn.py and components/spn_simulate.py."
    )

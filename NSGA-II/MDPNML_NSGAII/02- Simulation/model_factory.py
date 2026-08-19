"""Build a fresh executable MDSPN from the optimization-ready MDPNML file."""

from __future__ import annotations

from pathlib import Path

from bootstrap import ensure_mdpyspn_on_path

ensure_mdpyspn_on_path()

from ParseMDPNML import parse_mdpnml_to_spn  # noqa: E402
from mdpnml_policy import apply_policy  # noqa: E402
from optimization_metadata import load_optimization_spec  # noqa: E402


DEFAULT_PNML_PATH = Path(__file__).resolve().parents[1] / "01- Prepare MDPNML" / "MDPNML_optimization_ready.pnml"


def build_spn_from_mdpnml(
    policy=None,
    vector=None,
    pnml_path: str | Path = DEFAULT_PNML_PATH,
    verbose: bool = False,
):
    """Parse a fresh model and apply one candidate policy."""
    pnml_path = Path(pnml_path)
    spec = load_optimization_spec(pnml_path)
    spn_model = parse_mdpnml_to_spn(str(pnml_path), verbose=verbose)
    if policy is not None or vector is not None:
        apply_policy(spn_model, spec, policy=policy, vector=vector)
    return spn_model

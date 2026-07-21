"""Evaluate NSGA-II candidates by direct simulation of the MDPNML model."""

from __future__ import annotations

from contextlib import redirect_stdout
from dataclasses import dataclass, asdict
import io
from pathlib import Path
import random
import re
from statistics import NormalDist
from typing import Iterable, Sequence

import numpy as np

from bootstrap import ensure_mdpyspn_on_path

ensure_mdpyspn_on_path()

from components.spn_simulate import simulate  # noqa: E402
from optimization_metadata import OptimizationSpec, load_optimization_spec  # noqa: E402
from model_factory import DEFAULT_PNML_PATH, build_spn_from_mdpnml  # noqa: E402


INPUT_RE = re.compile(
    r"Input\s+value\s+for\s+(.+?)\s*:\s*([-+]?\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
OUTPUT_RE = re.compile(
    r"Output\s+value\s+for\s+(.+?)\s*:\s*([-+]?\d+(?:\.\d+)?)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class RunMetrics:
    inputs: float
    outputs: float
    throughput_ratio: float
    energy: float
    emission: float


@dataclass(frozen=True)
class EvaluationMetrics:
    n_replications: int
    mean_inputs: float
    mean_outputs: float
    mean_throughput_ratio: float
    mean_energy: float
    mean_emission: float
    sd_outputs: float
    sd_energy: float
    sd_emission: float
    ci95_outputs_low: float
    ci95_outputs_high: float
    ci95_energy_low: float
    ci95_energy_high: float
    ci95_emission_low: float
    ci95_emission_high: float

    def to_dict(self) -> dict[str, float | int]:
        return asdict(self)


def make_replication_seeds(base_seed: int, n_replications: int) -> list[int]:
    """Create a deterministic common-random-number seed set."""
    if n_replications < 1:
        raise ValueError("n_replications must be at least 1.")
    seed_sequence = np.random.SeedSequence(int(base_seed))
    children = seed_sequence.spawn(int(n_replications))
    return [int(child.generate_state(1, dtype=np.uint32)[0]) for child in children]


def _objective_dimension_name(spec: OptimizationSpec, objective_id: str, default: str) -> str:
    for objective in spec.objectives:
        if objective.name == objective_id and objective.dimension_name:
            return objective.dimension_name
    return default


def _transition_display_name(transition) -> str:
    """Return the human-readable transition label across MDPySPN versions.

    The parser stores ``mdpnml_name`` explicitly.  ``label`` and ``name`` are
    retained as compatibility fallbacks for models parsed by older code.
    Converting the Transition object itself with ``str(...)`` is deliberately
    avoided because some versions return only ``<...Transition object at ...>``.
    """
    for attribute in ("mdpnml_name", "label", "name"):
        value = getattr(transition, attribute, None)
        if value is None or callable(value):
            continue
        text = str(value).strip()
        if text and not (text.startswith("<") and " object at " in text):
            return text

    transition_id = getattr(transition, "mdpnml_id", "<unknown>")
    raise RuntimeError(
        f"Could not determine the display name of output transition {transition_id}. "
        "Use the included ParseMDPNML.py so that mdpnml_name is preserved."
    )


def _output_transition_names(spn_model, spec: OptimizationSpec) -> set[str]:
    transitions_by_id = getattr(spn_model, "transitions_by_id", {})
    configured_ids: tuple[str, ...] = ()
    for objective in spec.objectives:
        if objective.name == "outputs":
            configured_ids = objective.transition_ids
            break

    if configured_ids:
        missing = [tid for tid in configured_ids if tid not in transitions_by_id]
        if missing:
            raise KeyError(f"Output transition IDs missing from MDPNML: {missing}")
        return {
            _transition_display_name(transitions_by_id[tid])
            for tid in configured_ids
        }

    names = set()
    for transition in transitions_by_id.values():
        if bool(getattr(transition, "output_transition", False)):
            names.add(_transition_display_name(transition))
    return names


def _parse_io_summary(text: str, expected_output_names: set[str]) -> tuple[float, float]:
    inputs_by_name = {name.strip(): float(value) for name, value in INPUT_RE.findall(text)}
    outputs_by_name = {name.strip(): float(value) for name, value in OUTPUT_RE.findall(text)}

    if not inputs_by_name:
        raise RuntimeError(
            "The simulator summary did not contain any 'Input value for ...' lines. "
            "Keep the simulator summary output enabled.\n\nCaptured tail:\n"
            + text[-2500:]
        )
    if not outputs_by_name:
        raise RuntimeError(
            "The simulator summary did not contain any 'Output value for ...' lines. "
            "Keep the simulator summary output enabled.\n\nCaptured tail:\n"
            + text[-2500:]
        )

    inputs = float(sum(inputs_by_name.values()))
    if expected_output_names:
        normalized = {name.strip(): value for name, value in outputs_by_name.items()}
        missing = sorted(expected_output_names - set(normalized))
        if missing:
            raise RuntimeError(
                f"Expected output transition summaries were not printed: {missing}. "
                f"Available output summaries: {sorted(normalized)}"
            )
        outputs = float(sum(normalized[name] for name in expected_output_names))
    else:
        outputs = float(sum(outputs_by_name.values()))
    return inputs, outputs


def _read_dimension(spn_model, dimension_name: str) -> float:
    value = spn_model.get_dimension_value(dimension_name)
    if value is None:
        raise RuntimeError(
            f"Dimension '{dimension_name}' is unavailable after simulation. "
            f"Model dimensions: {getattr(spn_model, 'dimensions', [])}"
        )
    return float(value)


def run_once(
    vector: Sequence[float] | None = None,
    *,
    policy: dict[str, float] | None = None,
    pnml_path: str | Path = DEFAULT_PNML_PATH,
    horizon: float | None = None,
    seed: int | None = None,
) -> RunMetrics:
    """Parse, parameterize, and simulate one independent replication."""
    pnml_path = Path(pnml_path)
    spec = load_optimization_spec(pnml_path)
    horizon = float(spec.horizon if horizon is None else horizon)

    if seed is not None:
        random.seed(int(seed))
        np.random.seed(int(seed) % (2**32 - 1))

    spn_model = build_spn_from_mdpnml(
        policy=policy,
        vector=vector,
        pnml_path=pnml_path,
        verbose=False,
    )
    output_names = _output_transition_names(spn_model, spec)

    console = io.StringIO()
    with redirect_stdout(console):
        simulate(
            spn_model,
            max_time=horizon,
            verbosity=0,
            protocol=False,
            event_log=False,
        )

    inputs, outputs = _parse_io_summary(console.getvalue(), output_names)
    energy_dimension = _objective_dimension_name(spec, "energy", "Grid")
    emission_dimension = _objective_dimension_name(spec, "emission", "Emission")
    energy = _read_dimension(spn_model, energy_dimension)
    emission = _read_dimension(spn_model, emission_dimension)
    throughput_ratio = outputs / inputs if inputs > 0 else 0.0

    return RunMetrics(
        inputs=inputs,
        outputs=outputs,
        throughput_ratio=throughput_ratio,
        energy=energy,
        emission=emission,
    )


def _mean_sd_ci95(values: Iterable[float]) -> tuple[float, float, float, float]:
    array = np.asarray(list(values), dtype=float)
    if array.size == 0:
        raise ValueError("Cannot summarize an empty sample.")
    mean = float(np.mean(array))
    sd = float(np.std(array, ddof=1)) if array.size > 1 else 0.0
    if array.size > 1:
        # Student t is preferable; use scipy when available and a normal fallback.
        try:
            from scipy.stats import t

            critical = float(t.ppf(0.975, df=array.size - 1))
        except Exception:
            critical = float(NormalDist().inv_cdf(0.975))
        half_width = critical * sd / np.sqrt(array.size)
    else:
        half_width = 0.0
    return mean, sd, mean - half_width, mean + half_width


def eval_candidate(
    vector: Sequence[float] | None = None,
    *,
    policy: dict[str, float] | None = None,
    pnml_path: str | Path = DEFAULT_PNML_PATH,
    horizon: float | None = None,
    replication_seeds: Sequence[int] | None = None,
    n_rep: int = 5,
    base_seed: int = 20260717,
) -> EvaluationMetrics:
    """Evaluate one policy over replications using common random numbers."""
    if replication_seeds is None:
        replication_seeds = make_replication_seeds(base_seed, n_rep)
    if not replication_seeds:
        raise ValueError("At least one replication seed is required.")

    runs = [
        run_once(
            vector,
            policy=policy,
            pnml_path=pnml_path,
            horizon=horizon,
            seed=int(seed),
        )
        for seed in replication_seeds
    ]

    outputs_mean, outputs_sd, outputs_low, outputs_high = _mean_sd_ci95(
        run.outputs for run in runs
    )
    energy_mean, energy_sd, energy_low, energy_high = _mean_sd_ci95(
        run.energy for run in runs
    )
    emission_mean, emission_sd, emission_low, emission_high = _mean_sd_ci95(
        run.emission for run in runs
    )

    return EvaluationMetrics(
        n_replications=len(runs),
        mean_inputs=float(np.mean([run.inputs for run in runs])),
        mean_outputs=outputs_mean,
        mean_throughput_ratio=float(np.mean([run.throughput_ratio for run in runs])),
        mean_energy=energy_mean,
        mean_emission=emission_mean,
        sd_outputs=outputs_sd,
        sd_energy=energy_sd,
        sd_emission=emission_sd,
        ci95_outputs_low=outputs_low,
        ci95_outputs_high=outputs_high,
        ci95_energy_low=energy_low,
        ci95_energy_high=energy_high,
        ci95_emission_low=emission_low,
        ci95_emission_high=emission_high,
    )


def get_baseline(
    *,
    pnml_path: str | Path = DEFAULT_PNML_PATH,
    horizon: float | None = None,
    replication_seeds: Sequence[int] | None = None,
    n_rep: int = 5,
    base_seed: int = 20260717,
) -> EvaluationMetrics:
    spec = load_optimization_spec(pnml_path)
    baseline_policy = {
        parameter.name: parameter.baseline for parameter in spec.parameters
    }
    return eval_candidate(
        policy=baseline_policy,
        pnml_path=pnml_path,
        horizon=horizon,
        replication_seeds=replication_seeds,
        n_rep=n_rep,
        base_seed=base_seed,
    )

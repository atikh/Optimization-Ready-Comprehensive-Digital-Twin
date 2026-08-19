"""Standalone equal-weight weighted-sum scalarization baseline.

Place this file in the SAME folder as:
    MDPNML.pnml
    ParseMDPNML.py
    components/

The scalarization uses exactly the same three reference-scaled criteria as
the NSGA-II formulation in the case study:

    f1(x) = E_hat(x) / E_hat_base
    f2(x) = C_hat(x) / C_hat_base
    f3(x) = -P_hat(x) / P_hat_base

and combines them a priori with equal weights:

    J(x) = (1/3) f1(x) + (1/3) f2(x) + (1/3) f3(x)

Therefore:

    J(x) =
        (1/3) * E_hat(x) / E_hat_base
      + (1/3) * C_hat(x) / C_hat_base
      - (1/3) * P_hat(x) / P_hat_base

No simulation-based constraints are imposed, matching the NSGA-II case-study
formulation in which completed products are treated directly as an objective.

The scalarized single-objective problem is solved using pymoo's real-valued GA.
The default experimental settings match the NSGA-II case:
    population size = 80
    generations = 20
    search-stage replications = 5
    final reevaluation replications = 100
    simulation horizon = 480 min
    crossover = SBX(prob=0.9, eta=15)
    mutation = PM(eta=20)
    duplicate elimination = enabled

The baseline configuration is included once in the initial population.
Common random numbers are used within each evaluation stage by applying the
same replication-seed set to every candidate configuration.
"""

from __future__ import annotations

import argparse
import csv
import io
import random
from contextlib import redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from statistics import NormalDist
from typing import Sequence

import numpy as np

# ---------------------------------------------------------------------------
# Local MDPNML simulation dependencies
# ---------------------------------------------------------------------------

HERE = Path(__file__).resolve().parent

from ParseMDPNML import parse_mdpnml_to_spn
import components.spn_simulate as simmod

# Suppress simulator-side KPI CSV files during optimization. The scalarization
# script writes its own result files at the end.
simmod.write_kpis_to_csv = lambda *args, **kwargs: None
simulate = simmod.simulate

try:
    from pymoo.algorithms.soo.nonconvex.ga import GA
    from pymoo.core.callback import Callback
    from pymoo.core.problem import ElementwiseProblem
    from pymoo.optimize import minimize
    from pymoo.operators.crossover.sbx import SBX
    from pymoo.operators.mutation.pm import PM
    from pymoo.termination import get_termination
except ImportError as exc:
    raise ImportError(
        "pymoo is required for the scalarization experiment. "
        "Install it with: pip install pymoo"
    ) from exc


# ---------------------------------------------------------------------------
# Case-study definition
# ---------------------------------------------------------------------------

PNML_DEFAULT = HERE / "MDPNML.pnml"
OUTPUT_DEFAULT = HERE / "scalarization_output"

VARIABLE_NAMES = [
    "tau_R1",
    "tau_R2",
    "tau_W1",
    "tau_W2",
    "tau_RW",
    "w_R1",
    "w_W1",
]

LOWER_BOUNDS = np.asarray(
    [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    dtype=float,
)

UPPER_BOUNDS = np.asarray(
    [20.0, 20.0, 20.0, 20.0, 20.0, 1.0, 1.0],
    dtype=float,
)

THRESHOLD_TRANSITIONS = {
    "tau_R1": "Robot1_Idle_to_ShutDown",
    "tau_R2": "Robot2_Idle_to_ShutDown",
    "tau_W1": "MAG1_Idle_to_ShutDown",
    "tau_W2": "MAG2_Idle_to_ShutDown",
    "tau_RW": "ReMAG_Idle_to_ShutDown",
}

ROUTING_TRANSITIONS = {
    "w_R1": ("Select Robot1", "Select Robot2"),
    "w_W1": ("Select MAG1", "Select MAG2"),
}

HORIZON = 480.0

# Equal-weight scalarization of the same three NSGA-II criteria:
# energy, CO2 emissions, and negative completed products.
W_ENERGY = 1.0 / 3.0
W_EMISSION = 1.0 / 3.0
W_PRODUCTION = 1.0 / 3.0


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RunMetrics:
    inputs: float
    outputs: float
    throughput_ratio: float
    energy: float       # model accumulation unit, converted to kWh by / 60
    emission: float     # g


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


# ---------------------------------------------------------------------------
# Reproducible replication seeds
# ---------------------------------------------------------------------------

def make_replication_seeds(base_seed: int, n_replications: int) -> list[int]:
    """Create a deterministic replication-seed set."""
    seq = np.random.SeedSequence(int(base_seed))
    children = seq.spawn(int(n_replications))
    return [
        int(child.generate_state(1, dtype=np.uint32)[0])
        for child in children
    ]


# ---------------------------------------------------------------------------
# MDPNML configuration
# ---------------------------------------------------------------------------

def transition_by_label(spn_model, label: str):
    """Return the unique transition with the specified label."""
    matches = [t for t in spn_model.transitions if t.label == label]

    if len(matches) != 1:
        raise KeyError(
            f"Expected exactly one transition named '{label}', "
            f"but found {len(matches)}."
        )

    return matches[0]


def read_baseline_vector(pnml_path: Path) -> np.ndarray:
    """Read the seven baseline decision-variable values from MDPNML."""
    with redirect_stdout(io.StringIO()):
        spn_model = parse_mdpnml_to_spn(str(pnml_path))

    values: list[float] = []

    # Five idle-to-shutdown thresholds.
    for variable in VARIABLE_NAMES[:5]:
        transition = transition_by_label(
            spn_model,
            THRESHOLD_TRANSITIONS[variable],
        )

        if not transition.distribution:
            raise RuntimeError(
                f"Transition '{transition.label}' has no distribution."
            )

        distribution_name = next(iter(transition.distribution))
        parameters = transition.distribution[distribution_name]

        if "a" not in parameters:
            raise RuntimeError(
                f"Transition '{transition.label}' does not contain "
                "distribution parameter 'a'."
            )

        values.append(float(parameters["a"]))

    # Primary routing weights. The complementary branch weights are 1-w.
    robot1 = transition_by_label(
        spn_model,
        ROUTING_TRANSITIONS["w_R1"][0],
    )
    mag1 = transition_by_label(
        spn_model,
        ROUTING_TRANSITIONS["w_W1"][0],
    )

    values.extend(
        [
            float(robot1.weight),
            float(mag1.weight),
        ]
    )

    baseline_vector = np.asarray(values, dtype=float)

    if baseline_vector.shape != (7,):
        raise RuntimeError(
            f"Expected 7 baseline values, got {baseline_vector.shape}."
        )

    return baseline_vector


def apply_vector(spn_model, vector: Sequence[float]) -> None:
    """Apply one seven-variable candidate configuration to the MDSPN."""
    x = np.asarray(vector, dtype=float).reshape(-1)

    if x.shape != (7,):
        raise ValueError(
            f"Expected 7 decision variables, received shape {x.shape}."
        )

    tolerance = 1e-12

    if np.any(x < LOWER_BOUNDS - tolerance) or np.any(
        x > UPPER_BOUNDS + tolerance
    ):
        raise ValueError(
            f"Candidate lies outside the declared decision bounds: {x}"
        )

    # Clip only numerical round-off at the exact bounds.
    x = np.clip(x, LOWER_BOUNDS, UPPER_BOUNDS)

    # Five idle-to-shutdown thresholds.
    for idx, variable in enumerate(VARIABLE_NAMES[:5]):
        transition = transition_by_label(
            spn_model,
            THRESHOLD_TRANSITIONS[variable],
        )

        if not transition.distribution:
            raise RuntimeError(
                f"Transition '{transition.label}' has no distribution."
            )

        distribution_name = next(iter(transition.distribution))
        parameters = dict(transition.distribution[distribution_name])

        parameters["a"] = float(x[idx])

        transition.set_distribution(
            distribution_name,
            a=parameters.get("a", 0.0),
            b=parameters.get("b", 0.0),
            c=parameters.get("c", 0.0),
            d=parameters.get("d", 0.0),
            **{
                key: value
                for key, value in parameters.items()
                if key not in {"a", "b", "c", "d"}
            },
        )

    # Robot routing:
    # w_R1 for Robot 1, 1-w_R1 for Robot 2.
    w_r1 = float(x[5])

    robot1 = transition_by_label(spn_model, "Select Robot1")
    robot2 = transition_by_label(spn_model, "Select Robot2")

    robot1.set_weight(w_r1)
    robot2.set_weight(1.0 - w_r1)

    # Welding routing:
    # w_W1 for MAG 1, 1-w_W1 for MAG 2.
    w_w1 = float(x[6])

    mag1 = transition_by_label(spn_model, "Select MAG1")
    mag2 = transition_by_label(spn_model, "Select MAG2")

    mag1.set_weight(w_w1)
    mag2.set_weight(1.0 - w_w1)


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------

def run_once(
    vector: Sequence[float],
    *,
    pnml_path: Path,
    seed: int,
    horizon: float = HORIZON,
) -> RunMetrics:
    """Run one independent simulation replication."""

    # Reinitialize both Python and NumPy RNGs for this replication.
    random.seed(int(seed))
    np.random.seed(int(seed) % (2**32 - 1))

    # Parse a fresh model for every replication so no state carries over.
    with redirect_stdout(io.StringIO()):
        spn_model = parse_mdpnml_to_spn(str(pnml_path))

        apply_vector(spn_model, vector)

        simulate(
            spn_model,
            max_time=float(horizon),
            verbosity=0,
            protocol=False,
            event_log=False,
        )

    input_values = [
        float(getattr(transition, "input_value", 0.0))
        for transition in spn_model.transitions
        if hasattr(transition, "input_value")
    ]

    output_values = [
        float(getattr(transition, "output_value", 0.0))
        for transition in spn_model.transitions
        if hasattr(transition, "output_value")
    ]

    inputs = float(sum(input_values))
    outputs = float(sum(output_values))

    energy = float(spn_model.get_dimension_value("Grid"))
    emission = float(spn_model.get_dimension_value("Emission"))

    throughput_ratio = outputs / inputs if inputs > 0.0 else 0.0

    return RunMetrics(
        inputs=inputs,
        outputs=outputs,
        throughput_ratio=throughput_ratio,
        energy=energy,
        emission=emission,
    )


def mean_sd_ci95(
    values: Sequence[float],
) -> tuple[float, float, float, float]:
    """Return mean, sample SD, and two-sided 95% CI for the mean."""
    array = np.asarray(values, dtype=float)

    mean = float(np.mean(array))
    sd = float(np.std(array, ddof=1)) if len(array) > 1 else 0.0

    if len(array) > 1:
        try:
            from scipy.stats import t

            critical = float(
                t.ppf(
                    0.975,
                    df=len(array) - 1,
                )
            )
        except Exception:
            # Fallback if scipy is unavailable.
            critical = float(
                NormalDist().inv_cdf(0.975)
            )

        half_width = critical * sd / np.sqrt(len(array))
    else:
        half_width = 0.0

    return (
        mean,
        sd,
        mean - half_width,
        mean + half_width,
    )


def evaluate(
    vector: Sequence[float],
    *,
    pnml_path: Path,
    seeds: Sequence[int],
    horizon: float = HORIZON,
) -> EvaluationMetrics:
    """Evaluate one candidate using the specified common seed set."""
    runs = [
        run_once(
            vector,
            pnml_path=pnml_path,
            seed=int(seed),
            horizon=horizon,
        )
        for seed in seeds
    ]

    outputs_mean, outputs_sd, outputs_low, outputs_high = mean_sd_ci95(
        [run.outputs for run in runs]
    )

    energy_mean, energy_sd, energy_low, energy_high = mean_sd_ci95(
        [run.energy for run in runs]
    )

    emission_mean, emission_sd, emission_low, emission_high = mean_sd_ci95(
        [run.emission for run in runs]
    )

    return EvaluationMetrics(
        n_replications=len(runs),

        mean_inputs=float(
            np.mean([run.inputs for run in runs])
        ),
        mean_outputs=outputs_mean,
        mean_throughput_ratio=float(
            np.mean([run.throughput_ratio for run in runs])
        ),
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


# ---------------------------------------------------------------------------
# Equal-weight weighted-sum scalarization
# ---------------------------------------------------------------------------

def scalar_score(
    metrics: EvaluationMetrics,
    baseline: EvaluationMetrics,
) -> float:
    """Calculate the equal-weight scalarization of the three NSGA-II criteria."""

    if baseline.mean_energy <= 0.0:
        raise ZeroDivisionError("Baseline mean energy must be positive.")

    if baseline.mean_emission <= 0.0:
        raise ZeroDivisionError("Baseline mean emissions must be positive.")

    if baseline.mean_outputs <= 0.0:
        raise ZeroDivisionError(
            "Baseline mean completed products must be positive."
        )

    normalized_energy = (
        metrics.mean_energy / baseline.mean_energy
    )

    normalized_emission = (
        metrics.mean_emission / baseline.mean_emission
    )

    # Production is maximized in the original problem, so the normalized
    # production criterion enters the minimization scalarization negatively.
    normalized_negative_production = -(
        metrics.mean_outputs / baseline.mean_outputs
    )

    return float(
        W_ENERGY * normalized_energy
        + W_EMISSION * normalized_emission
        + W_PRODUCTION * normalized_negative_production
    )


# ---------------------------------------------------------------------------
# Initial population
# ---------------------------------------------------------------------------

def make_initial_population(
    baseline_vector: np.ndarray,
    population: int,
    seed: int,
) -> np.ndarray:
    """Create uniform-random initialization and include the baseline once."""
    rng = np.random.default_rng(seed)

    initial = rng.uniform(
        LOWER_BOUNDS,
        UPPER_BOUNDS,
        size=(
            int(population),
            len(VARIABLE_NAMES),
        ),
    )

    initial[0] = np.asarray(
        baseline_vector,
        dtype=float,
    )

    return initial


# ---------------------------------------------------------------------------
# Progress reporting
# ---------------------------------------------------------------------------

class ProgressCallback(Callback):
    """Print the best scalarized candidate in each generation."""

    def notify(self, algorithm):
        population = algorithm.pop

        scores = np.asarray(
            population.get("F"),
            dtype=float,
        ).reshape(-1)

        best_index = int(np.argmin(scores))

        outputs = np.asarray(
            population.get("outputs"),
            dtype=float,
        ).reshape(-1)

        energy = np.asarray(
            population.get("energy"),
            dtype=float,
        ).reshape(-1)

        emission = np.asarray(
            population.get("emission"),
            dtype=float,
        ).reshape(-1)

        print(
            f"Generation {algorithm.n_gen:2d}: "
            f"J={scores[best_index]:.6f}, "
            f"P={outputs[best_index]:.2f}, "
            f"E={energy[best_index] / 60.0:.2f} kWh, "
            f"CO2={emission[best_index]:.2f} g"
        )


# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------

def write_csv(
    path: Path,
    rows: list[dict],
) -> None:
    """Write a list of dictionaries to CSV."""
    if not rows:
        return

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=list(rows[0].keys()),
        )

        writer.writeheader()
        writer.writerows(rows)


def candidate_row(
    vector: Sequence[float],
    metrics: EvaluationMetrics,
    *,
    scalarized_objective: float | None = None,
    baseline: EvaluationMetrics | None = None,
) -> dict:
    """Create one result row for CSV export."""
    row = {
        name: float(value)
        for name, value in zip(
            VARIABLE_NAMES,
            np.asarray(vector, dtype=float),
        )
    }

    row.update(
        {
            "replications": int(metrics.n_replications),
            "mean_inputs": float(metrics.mean_inputs),
            "mean_completed_products": float(metrics.mean_outputs),
            "mean_throughput_ratio": float(
                metrics.mean_throughput_ratio
            ),
            "mean_grid_energy_kWh": float(
                metrics.mean_energy / 60.0
            ),
            "mean_CO2_g": float(metrics.mean_emission),

            "sd_completed_products": float(
                metrics.sd_outputs
            ),
            "sd_grid_energy_kWh": float(
                metrics.sd_energy / 60.0
            ),
            "sd_CO2_g": float(
                metrics.sd_emission
            ),

            "CI95_completed_products_low": float(
                metrics.ci95_outputs_low
            ),
            "CI95_completed_products_high": float(
                metrics.ci95_outputs_high
            ),
            "CI95_grid_energy_kWh_low": float(
                metrics.ci95_energy_low / 60.0
            ),
            "CI95_grid_energy_kWh_high": float(
                metrics.ci95_energy_high / 60.0
            ),
            "CI95_CO2_g_low": float(
                metrics.ci95_emission_low
            ),
            "CI95_CO2_g_high": float(
                metrics.ci95_emission_high
            ),
        }
    )

    if scalarized_objective is not None:
        row["scalarized_objective_J"] = float(
            scalarized_objective
        )

    if baseline is not None:
        row.update(
            {
                "change_completed_products_percent":
                    100.0
                    * (
                        metrics.mean_outputs
                        / baseline.mean_outputs
                        - 1.0
                    ),

                "change_grid_energy_percent":
                    100.0
                    * (
                        metrics.mean_energy
                        / baseline.mean_energy
                        - 1.0
                    ),

                "change_CO2_percent":
                    100.0
                    * (
                        metrics.mean_emission
                        / baseline.mean_emission
                        - 1.0
                    ),
            }
        )

    return row


# ---------------------------------------------------------------------------
# Command-line settings
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Equal-weight weighted-sum scalarization baseline "
            "for the MDPNML case study."
        )
    )

    parser.add_argument(
        "--pnml",
        type=Path,
        default=PNML_DEFAULT,
    )

    parser.add_argument(
        "--out",
        type=Path,
        default=OUTPUT_DEFAULT,
    )

    parser.add_argument(
        "--population",
        type=int,
        default=80,
    )

    parser.add_argument(
        "--generations",
        type=int,
        default=20,
    )

    parser.add_argument(
        "--eval-reps",
        type=int,
        default=5,
    )

    parser.add_argument(
        "--report-reps",
        type=int,
        default=100,
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=3,
        help="Optimization seed.",
    )

    parser.add_argument(
        "--report-seed",
        type=int,
        default=2026071701,
        help=(
            "Independent seed base for the final "
            "higher-replication reevaluation."
        ),
    )

    return parser.parse_args()


# ---------------------------------------------------------------------------
# Main experiment
# ---------------------------------------------------------------------------

def main():
    args = parse_args()

    if not args.pnml.is_file():
        raise FileNotFoundError(
            f"MDPNML file not found: {args.pnml}\n"
            "Place this script beside MDPNML.pnml, "
            "ParseMDPNML.py, and the components folder."
        )

    if args.population < 2:
        raise ValueError(
            "Population size must be at least 2."
        )

    if args.generations < 1:
        raise ValueError(
            "Number of generations must be at least 1."
        )

    if args.eval_reps < 1:
        raise ValueError(
            "Search-stage replication count must be positive."
        )

    if args.report_reps < 1:
        raise ValueError(
            "Final reevaluation replication count must be positive."
        )

    args.out.mkdir(
        parents=True,
        exist_ok=True,
    )

    baseline_vector = read_baseline_vector(
        args.pnml
    )

    # Common random numbers within the search stage.
    search_seeds = make_replication_seeds(
        args.seed * 100_000 + 17,
        args.eval_reps,
    )

    # Independent seed set for the final higher-replication reevaluation.
    report_seeds = make_replication_seeds(
        args.report_seed,
        args.report_reps,
    )

    print(
        "\nEqual-weight weighted-sum scalarization baseline"
    )
    print("=" * 72)

    print(
        f"MDPNML: {args.pnml}"
    )

    print(
        "\nBaseline decision vector read from MDPNML:"
    )

    for name, value in zip(
        VARIABLE_NAMES,
        baseline_vector,
    ):
        print(
            f"  {name:7s} = {value:.10f}"
        )

    print(
        "\nScalarized objective:"
    )

    print(
        "  min J(x) = "
        "(1/3) * E/E_base "
        "+ (1/3) * CO2/CO2_base "
        "- (1/3) * P/P_base"
    )

    print(
        "\nNo simulation-based constraints are imposed."
    )

    print(
        "\nSearch settings:"
    )

    print(
        f"  population                  = {args.population}"
    )

    print(
        f"  generations                 = {args.generations}"
    )

    print(
        f"  search-stage replications   = {args.eval_reps}"
    )

    print(
        f"  final reevaluation reps     = {args.report_reps}"
    )

    print(
        f"  simulation horizon          = {HORIZON:.0f} min"
    )

    print(
        "  crossover                   = SBX(prob=0.9, eta=15)"
    )

    print(
        "  mutation                    = PM(eta=20)"
    )

    print(
        "  duplicate elimination       = enabled"
    )

    # ---------------------------------------------------------------
    # Search-stage baseline
    # ---------------------------------------------------------------

    print(
        "\nEvaluating search-stage baseline..."
    )

    baseline_search = evaluate(
        baseline_vector,
        pnml_path=args.pnml,
        seeds=search_seeds,
        horizon=HORIZON,
    )

    baseline_search_score = scalar_score(
        baseline_search,
        baseline_search,
    )

    print(
        f"Baseline (r={args.eval_reps}): "
        f"P={baseline_search.mean_outputs:.2f}, "
        f"E={baseline_search.mean_energy / 60.0:.2f} kWh, "
        f"CO2={baseline_search.mean_emission:.2f} g, "
        f"J={baseline_search_score:.6f}"
    )

    # ---------------------------------------------------------------
    # Scalarized single-objective problem
    # ---------------------------------------------------------------

    class ScalarizedProblem(ElementwiseProblem):
        def __init__(self):
            super().__init__(
                n_var=7,
                n_obj=1,
                n_ieq_constr=0,
                xl=LOWER_BOUNDS,
                xu=UPPER_BOUNDS,
            )

            # Repeated vectors occasionally occur in evolutionary search.
            # Cache only within the current run and search-stage seed set.
            self.cache: dict[
                tuple[float, ...],
                EvaluationMetrics,
            ] = {}

        def _evaluate(
            self,
            x,
            out,
            *args_,
            **kwargs,
        ):
            candidate = np.asarray(
                x,
                dtype=float,
            )

            cache_key = tuple(
                np.round(
                    candidate,
                    12,
                )
            )

            metrics = self.cache.get(
                cache_key
            )

            if metrics is None:
                metrics = evaluate(
                    candidate,
                    pnml_path=args.pnml,
                    seeds=search_seeds,
                    horizon=HORIZON,
                )

                self.cache[
                    cache_key
                ] = metrics

            score = scalar_score(
                metrics,
                baseline_search,
            )

            out["F"] = np.asarray(
                [score],
                dtype=float,
            )

            # Additional values are stored only for progress reporting.
            out["outputs"] = np.asarray(
                [metrics.mean_outputs],
                dtype=float,
            )

            out["throughput"] = np.asarray(
                [metrics.mean_throughput_ratio],
                dtype=float,
            )

            out["energy"] = np.asarray(
                [metrics.mean_energy],
                dtype=float,
            )

            out["emission"] = np.asarray(
                [metrics.mean_emission],
                dtype=float,
            )

    # ---------------------------------------------------------------
    # Initialization and GA
    # ---------------------------------------------------------------

    initial_population = make_initial_population(
        baseline_vector,
        args.population,
        args.seed,
    )

    algorithm = GA(
        pop_size=args.population,
        sampling=initial_population,
        crossover=SBX(
            prob=0.9,
            eta=15,
        ),
        mutation=PM(
            eta=20,
        ),
        eliminate_duplicates=True,
    )

    print(
        "\nRunning scalarized single-objective GA..."
    )

    result = minimize(
        ScalarizedProblem(),
        algorithm,
        get_termination(
            "n_gen",
            args.generations,
        ),
        seed=args.seed,
        callback=ProgressCallback(),
        save_history=False,
        verbose=False,
    )

    if result.X is None:
        raise RuntimeError(
            "The scalarization search returned no solution."
        )

    best_vector = np.asarray(
        result.X,
        dtype=float,
    ).reshape(-1)

    # ---------------------------------------------------------------
    # Search-stage best solution
    # ---------------------------------------------------------------

    best_search = evaluate(
        best_vector,
        pnml_path=args.pnml,
        seeds=search_seeds,
        horizon=HORIZON,
    )

    best_search_score = scalar_score(
        best_search,
        baseline_search,
    )

    write_csv(
        args.out
        / "scalarization_best_search_stage.csv",
        [
            candidate_row(
                best_vector,
                best_search,
                scalarized_objective=best_search_score,
                baseline=baseline_search,
            )
        ],
    )

    # ---------------------------------------------------------------
    # Independent higher-replication reevaluation
    # ---------------------------------------------------------------

    print(
        f"\nReevaluating baseline and scalarized solution "
        f"with {args.report_reps} independent replications..."
    )

    baseline_final = evaluate(
        baseline_vector,
        pnml_path=args.pnml,
        seeds=report_seeds,
        horizon=HORIZON,
    )

    best_final = evaluate(
        best_vector,
        pnml_path=args.pnml,
        seeds=report_seeds,
        horizon=HORIZON,
    )

    # IMPORTANT:
    # Recompute the scalarized score using the independently reevaluated
    # baseline, preserving the same reference-scaling principle.
    final_score = scalar_score(
        best_final,
        baseline_final,
    )

    baseline_final_score = scalar_score(
        baseline_final,
        baseline_final,
    )

    baseline_final_row = candidate_row(
        baseline_vector,
        baseline_final,
        scalarized_objective=baseline_final_score,
    )

    best_final_row = candidate_row(
        best_vector,
        best_final,
        scalarized_objective=final_score,
        baseline=baseline_final,
    )

    write_csv(
        args.out
        / "scalarization_baseline_100rep.csv",
        [baseline_final_row],
    )

    write_csv(
        args.out
        / "scalarization_best_100rep.csv",
        [best_final_row],
    )

    # ---------------------------------------------------------------
    # Settings file for reproducibility
    # ---------------------------------------------------------------

    settings_rows = [
        {
            "setting": "method",
            "value": (
                "equal-weight weighted-sum scalarization "
                "solved by single-objective GA"
            ),
        },
        {
            "setting": "objective",
            "value": (
                "(1/3)*(E/E_base) + "
                "(1/3)*(C/C_base) - "
                "(1/3)*(P/P_base)"
            ),
        },
        {
            "setting": "simulation_constraints",
            "value": "none",
        },
        {
            "setting": "population",
            "value": args.population,
        },
        {
            "setting": "generations",
            "value": args.generations,
        },
        {
            "setting": "search_replications",
            "value": args.eval_reps,
        },
        {
            "setting": "final_reevaluation_replications",
            "value": args.report_reps,
        },
        {
            "setting": "simulation_horizon_min",
            "value": HORIZON,
        },
        {
            "setting": "optimization_seed",
            "value": args.seed,
        },
        {
            "setting": "report_seed",
            "value": args.report_seed,
        },
        {
            "setting": "crossover",
            "value": "SBX(prob=0.9, eta=15)",
        },
        {
            "setting": "mutation",
            "value": "PM(eta=20)",
        },
        {
            "setting": "duplicate_elimination",
            "value": "enabled",
        },
        {
            "setting": "energy_weight",
            "value": W_ENERGY,
        },
        {
            "setting": "emission_weight",
            "value": W_EMISSION,
        },
        {
            "setting": "production_weight",
            "value": W_PRODUCTION,
        },
    ]

    write_csv(
        args.out
        / "scalarization_settings.csv",
        settings_rows,
    )

    # ---------------------------------------------------------------
    # Final console report
    # ---------------------------------------------------------------

    print(
        "\n" + "=" * 72
    )

    print(
        "FINAL SCALARIZATION RESULT"
    )

    print(
        "=" * 72
    )

    print(
        "\nDecision vector:"
    )

    for name, value in zip(
        VARIABLE_NAMES,
        best_vector,
    ):
        print(
            f"  {name:7s} = {value:.10f}"
        )

    print(
        f"\n{args.report_reps}-replication baseline:"
    )

    print(
        f"  completed products = "
        f"{baseline_final.mean_outputs:.2f}"
    )

    print(
        f"  throughput ratio   = "
        f"{baseline_final.mean_throughput_ratio:.4f}"
    )

    print(
        f"  grid energy        = "
        f"{baseline_final.mean_energy / 60.0:.2f} kWh"
    )

    print(
        f"  CO2 emissions      = "
        f"{baseline_final.mean_emission:.2f} g"
    )

    print(
        f"  scalar objective J = "
        f"{baseline_final_score:.6f}"
    )

    print(
        f"\n{args.report_reps}-replication scalarized solution:"
    )

    print(
        f"  completed products = "
        f"{best_final.mean_outputs:.2f}"
    )

    print(
        f"  throughput ratio   = "
        f"{best_final.mean_throughput_ratio:.4f}"
    )

    print(
        f"  grid energy        = "
        f"{best_final.mean_energy / 60.0:.2f} kWh"
    )

    print(
        f"  CO2 emissions      = "
        f"{best_final.mean_emission:.2f} g"
    )

    print(
        f"  scalar objective J = "
        f"{final_score:.6f}"
    )

    print(
        "\nChanges relative to the "
        f"{args.report_reps}-replication baseline:"
    )

    print(
        f"  completed products = "
        f"{best_final_row['change_completed_products_percent']:+.2f}%"
    )

    print(
        f"  grid energy        = "
        f"{best_final_row['change_grid_energy_percent']:+.2f}%"
    )

    print(
        f"  CO2 emissions      = "
        f"{best_final_row['change_CO2_percent']:+.2f}%"
    )

    print(
        "\nSaved result files:"
    )

    print(
        " ",
        args.out
        / "scalarization_best_search_stage.csv",
    )

    print(
        " ",
        args.out
        / "scalarization_baseline_100rep.csv",
    )

    print(
        " ",
        args.out
        / "scalarization_best_100rep.csv",
    )

    print(
        " ",
        args.out
        / "scalarization_settings.csv",
    )


if __name__ == "__main__":
    main()

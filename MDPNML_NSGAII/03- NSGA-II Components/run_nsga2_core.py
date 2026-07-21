"""Three-objective, unconstrained NSGA-II over an executable MDPNML model.

Objectives (all represented internally as minimization):
  1. Mean Grid energy / baseline energy
  2. Mean Emission / baseline emission
  3. -Mean completed outputs / baseline outputs

The only restrictions are the variable bounds declared inside MDPNML.pnml.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SIMULATION_DIR = PROJECT_ROOT / "02- Simulation"
NSGA_COMPONENTS_DIR = Path(__file__).resolve().parent
for path in (SIMULATION_DIR, NSGA_COMPONENTS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import argparse

import numpy as np

from bootstrap import ensure_mdpyspn_on_path

ensure_mdpyspn_on_path()

from pymoo.algorithms.moo.nsga2 import NSGA2  # noqa: E402
from pymoo.core.callback import Callback  # noqa: E402
from pymoo.core.problem import ElementwiseProblem  # noqa: E402
from pymoo.optimize import minimize  # noqa: E402
from pymoo.termination import get_termination  # noqa: E402

from kpi_eval import eval_candidate, get_baseline, make_replication_seeds  # noqa: E402
from optimization_metadata import load_optimization_spec  # noqa: E402
from plot_utils import generate_all_plots  # noqa: E402
from rank_pareto import run_ranking  # noqa: E402
from results_io import (  # noqa: E402
    pareto_mask_min,
    reevaluate_pareto_set,
    write_baseline,
    write_final_population,
    write_generation_history,
    write_population_history,
    write_raw_pareto_set,
)


DEFAULT_PNML = PROJECT_ROOT / "01- Prepare MDPNML" / "MDPNML_optimization_ready.pnml"
DEFAULT_OUT = PROJECT_ROOT / "04- Outputs"


class GenerationCallback(Callback):
    def __init__(self, history: list[dict]):
        super().__init__()
        self.history = history

    @staticmethod
    def _raw(population, name: str) -> np.ndarray:
        value = population.get(name)
        if value is None:
            return np.asarray([], dtype=float)
        return np.asarray(value, dtype=float).reshape(-1)

    def notify(self, algorithm):
        population = algorithm.pop
        energy = self._raw(population, "energy")
        emission = self._raw(population, "emission")
        outputs = self._raw(population, "outputs")
        if not len(energy):
            return

        raw_objectives = np.column_stack([energy, emission, -outputs])
        nondominated_count = int(np.sum(pareto_mask_min(raw_objectives)))
        record = {
            "generation": int(algorithm.n_gen),
            "population_size": int(len(energy)),
            "nondominated_count": nondominated_count,
            "minimum_energy": float(np.min(energy)),
            "minimum_emission": float(np.min(emission)),
            "maximum_outputs": float(np.max(outputs)),
            "median_energy": float(np.median(energy)),
            "median_emission": float(np.median(emission)),
            "median_outputs": float(np.median(outputs)),
        }
        self.history.append(record)
        print(
            f"[gen {algorithm.n_gen:3d}] "
            f"ND={nondominated_count:3d}/{len(energy):3d}  "
            f"min E={record['minimum_energy']:.3f}  "
            f"min Em={record['minimum_emission']:.3f}  "
            f"max outputs={record['maximum_outputs']:.3f}"
        )


def make_initial_population(spec, pop_size: int, seed: int) -> np.ndarray:
    """Random bounded population with the extracted baseline included once."""
    rng = np.random.default_rng(seed)
    lower = np.asarray(spec.lower_bounds, dtype=float)
    upper = np.asarray(spec.upper_bounds, dtype=float)
    population = rng.uniform(lower, upper, size=(pop_size, len(spec.parameters)))
    population[0] = np.asarray(spec.baseline_vector, dtype=float)
    return population


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run unconstrained three-objective NSGA-II on MDPNML."
    )
    parser.add_argument("--pnml", type=Path, default=DEFAULT_PNML)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--population", type=int, default=80)
    parser.add_argument("--generations", type=int, default=20)
    parser.add_argument("--eval-reps", type=int, default=5)
    parser.add_argument("--report-reps", type=int, default=100)
    parser.add_argument("--seed", type=int, default=3)
    parser.add_argument(
        "--report-seed",
        type=int,
        default=2026071701,
        help="Independent seed base for final 100-replication reevaluation.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    spec = load_optimization_spec(args.pnml)
    horizon = float(spec.horizon)

    if args.population < 4:
        raise ValueError("Population size must be at least 4.")
    if args.generations < 1:
        raise ValueError("Number of generations must be at least 1.")

    evaluation_seeds = make_replication_seeds(args.seed * 100_000 + 17, args.eval_reps)
    report_seeds = make_replication_seeds(args.report_seed, args.report_reps)

    print("Optimization variables from MDPNML:")
    for parameter in spec.parameters:
        print(
            f"  {parameter.name}: [{parameter.lower}, {parameter.upper}], "
            f"baseline={parameter.baseline}"
        )

    baseline_eval = get_baseline(
        pnml_path=args.pnml,
        horizon=horizon,
        replication_seeds=evaluation_seeds,
    )
    base_energy = baseline_eval.mean_energy if baseline_eval.mean_energy > 0 else 1.0
    base_emission = baseline_eval.mean_emission if baseline_eval.mean_emission > 0 else 1.0
    base_outputs = baseline_eval.mean_outputs if baseline_eval.mean_outputs > 0 else 1.0
    print(
        "Optimization-stage baseline: "
        f"outputs={baseline_eval.mean_outputs:.3f}, "
        f"energy={baseline_eval.mean_energy:.3f}, "
        f"emission={baseline_eval.mean_emission:.3f}"
    )

    lower = np.asarray(spec.lower_bounds, dtype=float)
    upper = np.asarray(spec.upper_bounds, dtype=float)

    class MDPNMLProblem(ElementwiseProblem):
        def __init__(self):
            super().__init__(
                n_var=len(spec.parameters),
                n_obj=3,
                n_ieq_constr=0,
                xl=lower,
                xu=upper,
            )
            self.cache: dict[tuple[float, ...], object] = {}

        def _evaluate(self, x, out, *args_, **kwargs):
            # Rounding only defines a stable cache key; the evaluated vector is unchanged.
            key = tuple(np.round(np.asarray(x, dtype=float), 12))
            metrics = self.cache.get(key)
            if metrics is None:
                metrics = eval_candidate(
                    x,
                    pnml_path=args.pnml,
                    horizon=horizon,
                    replication_seeds=evaluation_seeds,
                )
                self.cache[key] = metrics

            out["F"] = np.asarray(
                [
                    metrics.mean_energy / base_energy,
                    metrics.mean_emission / base_emission,
                    -(metrics.mean_outputs / base_outputs),
                ],
                dtype=float,
            )
            out["outputs"] = np.asarray([metrics.mean_outputs], dtype=float)
            out["throughput_ratio"] = np.asarray(
                [metrics.mean_throughput_ratio], dtype=float
            )
            out["energy"] = np.asarray([metrics.mean_energy], dtype=float)
            out["emission"] = np.asarray([metrics.mean_emission], dtype=float)

    initial_population = make_initial_population(spec, args.population, args.seed)
    history: list[dict] = []
    callback = GenerationCallback(history)
    algorithm = NSGA2(
        pop_size=args.population,
        sampling=initial_population,
        eliminate_duplicates=True,
    )

    result = minimize(
        MDPNMLProblem(),
        algorithm,
        get_termination("n_gen", args.generations),
        seed=args.seed,
        callback=callback,
        save_history=True,
        verbose=True,
    )

    if result.X is None:
        raise RuntimeError("NSGA-II completed without returning a Pareto set.")

    final_algorithm = result.algorithm

    paths = []
    paths.append(write_generation_history(args.out, history))
    paths.append(write_population_history(args.out, result, final_algorithm, spec))
    paths.append(write_final_population(args.out, final_algorithm, spec))
    paths.append(write_raw_pareto_set(args.out, result, spec))

    baseline_report = get_baseline(
        pnml_path=args.pnml,
        horizon=horizon,
        replication_seeds=report_seeds,
    )
    paths.append(write_baseline(args.out, baseline_report, spec))

    reevaluated_all, reevaluated_front = reevaluate_pareto_set(
        args.out,
        result,
        spec,
        evaluator=eval_candidate,
        pnml_path=args.pnml,
        horizon=horizon,
        replication_seeds=report_seeds,
    )
    paths.extend([reevaluated_all, reevaluated_front])

    ranked_path, selected_path = run_ranking(args.out)
    paths.extend([ranked_path, selected_path])
    paths.extend(generate_all_plots(args.out))

    print("\nCompleted. Generated:")
    for path in paths:
        print(f"  {Path(path).resolve()}")


if __name__ == "__main__":
    main()

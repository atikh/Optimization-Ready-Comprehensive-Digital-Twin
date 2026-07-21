"""Export three-objective NSGA-II histories and high-replication Pareto results."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Callable, Iterable, Sequence

import numpy as np

from optimization_metadata import OptimizationSpec


def pareto_mask_min(values: np.ndarray) -> np.ndarray:
    """Boolean mask of nondominated rows when every column is minimized."""
    values = np.asarray(values, dtype=float)
    if values.ndim != 2:
        raise ValueError("values must be a two-dimensional array.")
    n = len(values)
    mask = np.ones(n, dtype=bool)
    for i in range(n):
        if not mask[i]:
            continue
        dominated_by_other = (
            np.all(values <= values[i], axis=1)
            & np.any(values < values[i], axis=1)
        )
        dominated_by_other[i] = False
        if np.any(dominated_by_other):
            mask[i] = False
    return mask


def _as_2d(array, n_columns: int | None = None) -> np.ndarray:
    result = np.asarray(array, dtype=float)
    if result.ndim == 1:
        result = result.reshape(1, -1)
    if n_columns is not None and result.shape[1] != n_columns:
        raise ValueError(f"Expected {n_columns} columns, received {result.shape[1]}.")
    return result


def _write_rows(path: Path, fieldnames: Sequence[str], rows: Iterable[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(fieldnames), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


def write_generation_history(out_dir: str | Path, history: Sequence[dict]) -> Path:
    out_dir = Path(out_dir)
    if not history:
        raise ValueError("Generation history is empty.")
    return _write_rows(
        out_dir / "nsga2_generation_summary.csv",
        list(history[0].keys()),
        history,
    )


def _population_records(record, spec: OptimizationSpec, generation: int) -> list[dict]:
    population = getattr(record, "pop", None)
    if population is None and hasattr(record, "algorithm"):
        population = getattr(record.algorithm, "pop", None)
    if population is None:
        return []

    X = population.get("X")
    if X is None:
        return []
    X = _as_2d(X, len(spec.parameters))
    F = population.get("F")
    F = _as_2d(F, 3) if F is not None else np.full((len(X), 3), np.nan)

    def raw(name: str) -> np.ndarray:
        values = population.get(name)
        return (
            np.asarray(values, dtype=float).reshape(-1)
            if values is not None
            else np.full(len(X), np.nan)
        )

    outputs = raw("outputs")
    energy = raw("energy")
    emission = raw("emission")
    throughput_ratio = raw("throughput_ratio")

    rows = []
    for index, vector in enumerate(X):
        row = {
            "generation": int(generation),
            "individual": int(index),
            **{
                parameter.name: float(value)
                for parameter, value in zip(spec.parameters, vector)
            },
            "mean_outputs": float(outputs[index]),
            "mean_throughput_ratio": float(throughput_ratio[index]),
            "mean_energy": float(energy[index]),
            "mean_emission": float(emission[index]),
            "f_energy": float(F[index, 0]),
            "f_emission": float(F[index, 1]),
            "f_outputs_cost": float(F[index, 2]),
        }
        rows.append(row)
    return rows


def write_population_history(
    out_dir: str | Path,
    result,
    algorithm,
    spec: OptimizationSpec,
) -> Path:
    out_dir = Path(out_dir)
    records = list(getattr(result, "history", []) or [])
    if not records:
        records = [algorithm]

    rows: list[dict] = []
    for fallback_generation, record in enumerate(records, start=1):
        generation = getattr(record, "n_gen", fallback_generation)
        rows.extend(_population_records(record, spec, int(generation)))

    fields = [
        "generation",
        "individual",
        *spec.names,
        "mean_outputs",
        "mean_throughput_ratio",
        "mean_energy",
        "mean_emission",
        "f_energy",
        "f_emission",
        "f_outputs_cost",
    ]
    return _write_rows(out_dir / "nsga2_population_history.csv", fields, rows)


def write_final_population(
    out_dir: str | Path,
    algorithm,
    spec: OptimizationSpec,
) -> Path:
    out_dir = Path(out_dir)
    rows = _population_records(algorithm, spec, int(getattr(algorithm, "n_gen", 0)))
    fields = [
        "generation",
        "individual",
        *spec.names,
        "mean_outputs",
        "mean_throughput_ratio",
        "mean_energy",
        "mean_emission",
        "f_energy",
        "f_emission",
        "f_outputs_cost",
    ]
    return _write_rows(out_dir / "nsga2_final_population.csv", fields, rows)


def write_raw_pareto_set(
    out_dir: str | Path,
    result,
    spec: OptimizationSpec,
) -> Path:
    out_dir = Path(out_dir)
    if result.X is None:
        raise RuntimeError("NSGA-II did not return a Pareto decision set.")
    X = _as_2d(result.X, len(spec.parameters))
    F = _as_2d(result.F, 3)

    rows = []
    for index, (vector, objectives) in enumerate(zip(X, F)):
        rows.append(
            {
                "pareto_id": index,
                **{
                    parameter.name: float(value)
                    for parameter, value in zip(spec.parameters, vector)
                },
                "f_energy": float(objectives[0]),
                "f_emission": float(objectives[1]),
                "f_outputs_cost": float(objectives[2]),
            }
        )
    fields = ["pareto_id", *spec.names, "f_energy", "f_emission", "f_outputs_cost"]
    return _write_rows(out_dir / "nsga2_pareto_front_raw.csv", fields, rows)


def reevaluate_pareto_set(
    out_dir: str | Path,
    result,
    spec: OptimizationSpec,
    *,
    evaluator: Callable,
    pnml_path,
    horizon: float,
    replication_seeds: Sequence[int],
) -> tuple[Path, Path]:
    """Reevaluate raw Pareto decisions and recalculate dominance after noise reduction."""
    out_dir = Path(out_dir)
    X = _as_2d(result.X, len(spec.parameters))
    rows: list[dict] = []

    for pareto_id, vector in enumerate(X):
        metrics = evaluator(
            vector,
            pnml_path=pnml_path,
            horizon=horizon,
            replication_seeds=replication_seeds,
        )
        rows.append(
            {
                "pareto_id": pareto_id,
                **{
                    parameter.name: float(value)
                    for parameter, value in zip(spec.parameters, vector)
                },
                **metrics.to_dict(),
            }
        )

    objectives = np.column_stack(
        [
            [row["mean_energy"] for row in rows],
            [row["mean_emission"] for row in rows],
            [-row["mean_outputs"] for row in rows],
        ]
    )
    mask = pareto_mask_min(objectives)
    for row, is_nondominated in zip(rows, mask):
        row["nondominated_after_reevaluation"] = bool(is_nondominated)

    fields = [
        "pareto_id",
        *spec.names,
        "n_replications",
        "mean_inputs",
        "mean_outputs",
        "mean_throughput_ratio",
        "mean_energy",
        "mean_emission",
        "sd_outputs",
        "sd_energy",
        "sd_emission",
        "ci95_outputs_low",
        "ci95_outputs_high",
        "ci95_energy_low",
        "ci95_energy_high",
        "ci95_emission_low",
        "ci95_emission_high",
        "nondominated_after_reevaluation",
    ]

    all_path = _write_rows(
        out_dir / "nsga2_pareto_front_reevaluated_all.csv", fields, rows
    )
    front_rows = [row for row in rows if row["nondominated_after_reevaluation"]]
    front_path = _write_rows(
        out_dir / "nsga2_pareto_front_reevaluated.csv", fields, front_rows
    )
    return all_path, front_path


def write_baseline(out_dir: str | Path, baseline_metrics, spec: OptimizationSpec) -> Path:
    out_dir = Path(out_dir)
    row = {
        **{parameter.name: parameter.baseline for parameter in spec.parameters},
        **baseline_metrics.to_dict(),
    }
    fields = [
        *spec.names,
        "n_replications",
        "mean_inputs",
        "mean_outputs",
        "mean_throughput_ratio",
        "mean_energy",
        "mean_emission",
        "sd_outputs",
        "sd_energy",
        "sd_emission",
        "ci95_outputs_low",
        "ci95_outputs_high",
        "ci95_energy_low",
        "ci95_energy_high",
        "ci95_emission_low",
        "ci95_emission_high",
    ]
    return _write_rows(out_dir / "baseline_reevaluated.csv", fields, [row])

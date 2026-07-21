"""Post-Pareto ranking under different decision-maker priorities."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


DEFAULT_SCENARIOS = {
    "equal": {"energy": 1 / 3, "emission": 1 / 3, "outputs": 1 / 3},
    "throughput_priority": {"energy": 0.20, "emission": 0.20, "outputs": 0.60},
    "sustainability_priority": {"energy": 0.40, "emission": 0.40, "outputs": 0.20},
    "energy_priority": {"energy": 0.60, "emission": 0.20, "outputs": 0.20},
    "emission_priority": {"energy": 0.20, "emission": 0.60, "outputs": 0.20},
}


def _minmax_cost(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    span = float(np.max(values) - np.min(values))
    return np.zeros_like(values) if span == 0 else (values - np.min(values)) / span


def rank_front(front: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if front.empty:
        raise ValueError("The reevaluated Pareto front is empty.")

    energy_cost = _minmax_cost(front["mean_energy"].to_numpy(float))
    emission_cost = _minmax_cost(front["mean_emission"].to_numpy(float))
    output_cost = _minmax_cost(-front["mean_outputs"].to_numpy(float))

    ranked = front.copy()
    selected_rows = []
    for scenario, weights in DEFAULT_SCENARIOS.items():
        score = (
            weights["energy"] * energy_cost
            + weights["emission"] * emission_cost
            + weights["outputs"] * output_cost
        )
        ranked[f"score_{scenario}"] = score
        best_position = int(np.argmin(score))
        selected = ranked.iloc[best_position].copy()
        selected["scenario"] = scenario
        selected["weight_energy"] = weights["energy"]
        selected["weight_emission"] = weights["emission"]
        selected["weight_outputs"] = weights["outputs"]
        selected["preference_score"] = float(score[best_position])
        selected_rows.append(selected)

    selected_df = pd.DataFrame(selected_rows)
    return ranked, selected_df


def run_ranking(out_dir: str | Path) -> tuple[Path, Path]:
    out_dir = Path(out_dir)
    front_path = out_dir / "nsga2_pareto_front_reevaluated.csv"
    front = pd.read_csv(front_path)
    ranked, selected = rank_front(front)
    ranked_path = out_dir / "nsga2_pareto_rankings.csv"
    selected_path = out_dir / "nsga2_selected_solutions.csv"
    ranked.to_csv(ranked_path, index=False)
    selected.to_csv(selected_path, index=False)
    return ranked_path, selected_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "04- Outputs"), help="NSGA-II output directory")
    args = parser.parse_args()
    paths = run_ranking(args.out)
    for path in paths:
        print(f"Saved: {path}")

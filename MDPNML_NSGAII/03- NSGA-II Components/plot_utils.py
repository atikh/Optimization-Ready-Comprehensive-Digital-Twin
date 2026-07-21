"""Publication-ready plots for the three-objective NSGA-II experiment."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402


def _load_required(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    return pd.read_csv(path)


def plot_energy_emission(out_dir: str | Path) -> Path:
    out_dir = Path(out_dir)
    population = _load_required(out_dir / "nsga2_population_history.csv")
    front = _load_required(out_dir / "nsga2_pareto_front_reevaluated.csv")
    baseline = _load_required(out_dir / "baseline_reevaluated.csv").iloc[0]

    fig, ax = plt.subplots(figsize=(10, 7))
    scatter = ax.scatter(
        population["mean_energy"],
        population["mean_emission"],
        c=population["mean_outputs"],
        s=18,
        alpha=0.55,
        edgecolors="none",
        label="Evaluated solutions",
    )
    colorbar = fig.colorbar(scatter, ax=ax)
    colorbar.set_label("Mean completed outputs")

    ax.scatter(
        front["mean_energy"],
        front["mean_emission"],
        s=72,
        facecolors="none",
        edgecolors="black",
        linewidths=1.4,
        label="Reevaluated Pareto set",
    )
    ax.scatter(
        [baseline["mean_energy"]],
        [baseline["mean_emission"]],
        marker="s",
        s=100,
        facecolors="none",
        edgecolors="black",
        linewidths=1.8,
        label="Extracted baseline",
    )
    ax.set_xlabel("Mean grid energy")
    ax.set_ylabel("Mean emission")
    ax.grid(True, linestyle="--", alpha=0.3)
    ax.legend(frameon=True)
    fig.tight_layout()
    path = out_dir / "nsga2_energy_emission.png"
    fig.savefig(path, dpi=350, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_three_objectives(out_dir: str | Path) -> Path:
    out_dir = Path(out_dir)
    population = _load_required(out_dir / "nsga2_population_history.csv")
    front = _load_required(out_dir / "nsga2_pareto_front_reevaluated.csv")
    baseline = _load_required(out_dir / "baseline_reevaluated.csv").iloc[0]

    fig = plt.figure(figsize=(10, 8))
    ax = fig.add_subplot(111, projection="3d")
    scatter = ax.scatter(
        population["mean_energy"],
        population["mean_emission"],
        population["mean_outputs"],
        c=population["mean_outputs"],
        s=15,
        alpha=0.42,
        depthshade=True,
        label="Evaluated solutions",
    )
    colorbar = fig.colorbar(scatter, ax=ax, pad=0.10)
    colorbar.set_label("Mean completed outputs")
    ax.scatter(
        front["mean_energy"],
        front["mean_emission"],
        front["mean_outputs"],
        s=70,
        facecolors="none",
        edgecolors="black",
        linewidths=1.3,
        label="Reevaluated Pareto set",
    )
    ax.scatter(
        [baseline["mean_energy"]],
        [baseline["mean_emission"]],
        [baseline["mean_outputs"]],
        marker="s",
        s=110,
        facecolors="none",
        edgecolors="black",
        linewidths=1.8,
        label="Extracted baseline",
    )
    ax.set_xlabel("Mean grid energy")
    ax.set_ylabel("Mean emission")
    ax.set_zlabel("Mean completed outputs")
    ax.view_init(elev=24, azim=135)
    ax.legend(loc="best", frameon=True)
    fig.tight_layout()
    path = out_dir / "nsga2_three_objectives.png"
    fig.savefig(path, dpi=350, bbox_inches="tight")
    plt.close(fig)
    return path


def _plot_progress(
    history: pd.DataFrame,
    column: str,
    ylabel: str,
    path: Path,
) -> Path:
    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.plot(history["generation"], history[column], linewidth=2)
    ax.set_xlabel("Generation")
    ax.set_ylabel(ylabel)
    ax.grid(True, linestyle="--", alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_generation_progress(out_dir: str | Path) -> list[Path]:
    out_dir = Path(out_dir)
    history = _load_required(out_dir / "nsga2_generation_summary.csv")
    return [
        _plot_progress(
            history,
            "minimum_energy",
            "Minimum mean grid energy",
            out_dir / "progress_minimum_energy.png",
        ),
        _plot_progress(
            history,
            "minimum_emission",
            "Minimum mean emission",
            out_dir / "progress_minimum_emission.png",
        ),
        _plot_progress(
            history,
            "maximum_outputs",
            "Maximum mean completed outputs",
            out_dir / "progress_maximum_outputs.png",
        ),
    ]


def generate_all_plots(out_dir: str | Path) -> list[Path]:
    paths = [plot_energy_emission(out_dir), plot_three_objectives(out_dir)]
    paths.extend(plot_generation_progress(out_dir))
    for path in paths:
        print(f"Saved: {path}")
    return paths


if __name__ == "__main__":
    generate_all_plots(Path(__file__).resolve().parents[1] / "04- Outputs")

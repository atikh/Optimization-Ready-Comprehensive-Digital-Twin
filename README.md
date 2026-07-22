# Optimization-Ready Comprehensive Digital Twin with MDPNML and NSGA-II

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-TBD-lightgrey.svg)](#license)
[![DOI](https://img.shields.io/badge/DOI-pending-lightgrey.svg)](#citation)

This repository contains the implementation accompanying the manuscript:

> **Simulation-Based Multi-Objective Decision Support for Comprehensive Digital Twins of Smart Manufacturing Systems**  
> Atieh Khodadadi, Sanja Lazarova-Molnar, and Xueping Li.

The code transforms an automatically extracted, simulation-ready Multidimensional Stochastic Petri Net into an optimization-ready model represented in Multidimensional Petri Net Markup Language. It then couples the model with the Non-dominated Sorting Genetic Algorithm II (NSGA-II) for simulation-based multi-objective decision support.

## Overview

The workflow:

1. reads an automatically extracted Multidimensional Petri Net Markup Language model;
2. maps expert-defined optimization variables and bounds to model parameters;
3. creates an optimization-ready model and an auditable mapping report;
4. evaluates candidate configurations through repeated stochastic simulation;
5. applies NSGA-II to approximate the Pareto set;
6. reevaluates search-stage nondominated configurations using more replications;
7. recomputes nondominance and generates result tables and figures.

The case study considers three objectives:

- minimize grid-energy consumption;
- minimize CO₂ emissions;
- maximize the number of completed products.

No additional simulation-based performance constraint is imposed during the search. Decision-variable bounds define the admissible search space.

## Decision variables

The optimization uses seven continuous decision variables.

| Variable | Description | Bounds |
|---|---|---:|
| `tau_robot1` | Idle-to-shutdown threshold for Robot 1 | `[0, 20]` min |
| `tau_robot2` | Idle-to-shutdown threshold for Robot 2 | `[0, 20]` min |
| `tau_mag1` | Idle-to-shutdown threshold for Welding Machine 1 | `[0, 20]` min |
| `tau_mag2` | Idle-to-shutdown threshold for Welding Machine 2 | `[0, 20]` min |
| `tau_remag` | Idle-to-shutdown threshold for Rework Welding | `[0, 20]` min |
| `w_robot1` | Routing weight for Robot 1; Robot 2 receives `1 - w_robot1` | `[0, 1]` |
| `w_mag1` | Routing weight for Welding Machine 1; Welding Machine 2 receives `1 - w_mag1` | `[0, 1]` |

The mappings, bounds, and objective definitions are maintained in:

```text
01- Prepare MDPNML/optimization_parameters.json
```

## Repository structure

```text
MDPNML_NSGAII/
├── run_nsga2.py
├── requirements.txt
├── README.md
├── 01- Prepare MDPNML/
│   ├── MDPNML.pnml
│   ├── MDPNML_optimization_ready.pnml
│   ├── optimization_parameters.json
│   ├── optimization_mapping_report.csv
│   └── prepare_mdpnml.py
├── 02- Simulation/
│   ├── ParseMDPNML.py
│   ├── bootstrap.py
│   ├── kpi_eval.py
│   ├── mdpnml_policy.py
│   ├── model_factory.py
│   ├── optimization_metadata.py
│   ├── run_baseline.py
│   └── components/
├── 03- NSGA-II Components/
│   ├── run_nsga2_core.py
│   ├── results_io.py
│   ├── rank_pareto.py
│   └── plot_utils.py
├── 04- Outputs/
└── 05- Test/
    ├── README.txt
    ├── test_mapping.py
    ├── test_output_name_mapping.py
    └── smoke_test.py
```

## Requirements

- Python 3.11 or newer
- NumPy
- pandas
- SciPy
- Matplotlib
- pymoo
- openpyxl

Install the dependencies with:

```bash
python -m pip install -r requirements.txt
```

For a reproducible paper release, pin the exact package versions used for the reported experiment before creating the release tag.

## Installation

Clone the repository and create a virtual environment.

```bash
git clone https://github.com/USERNAME/REPOSITORY.git
cd REPOSITORY

python -m venv .venv
```

Activate the environment.

**Windows PowerShell**

```powershell
.venv\Scripts\Activate.ps1
```

**Linux or macOS**

```bash
source .venv/bin/activate
```

Install the requirements.

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Quick start

Run the complete preparation, simulation, optimization, reevaluation, ranking, and plotting workflow from the repository root:

```bash
python run_nsga2.py
```

The command first regenerates the optimization-ready model and mapping report. NSGA-II starts only after the model-to-decision-variable mapping has been validated successfully.

### Small trial run

Use a small run to verify the installation:

```bash
python run_nsga2.py \
  --population 10 \
  --generations 2 \
  --eval-reps 2 \
  --report-reps 5
```

On Windows Command Prompt, enter the same command on one line.

## Default experiment settings

| Setting | Default |
|---|---:|
| Simulation horizon | `480` min |
| Population size | `80` |
| Generations | `20` |
| Search-stage replications | `5` |
| Higher-replication reevaluation | `100` |
| Optimization seed | `3` |
| Reevaluation seed base | `2026071701` |
| Duplicate elimination | Enabled |
| Additional simulation-based constraints | None |

The reference configuration is inserted as the first member of the initial population. The same search-stage replication seeds are used across candidate configurations to support common-random-number comparisons. A separate seed set is used for higher-replication reevaluation.

## Command-line options

```text
--pnml PATH          Optimization-ready MDPNML file
--out PATH           Output directory
--population INT     NSGA-II population size
--generations INT    Number of generations
--eval-reps INT      Replications per candidate during the search
--report-reps INT    Replications used for final reevaluation
--seed INT           Optimization and initial-population seed
--report-seed INT    Independent seed base for final reevaluation
```

Example:

```bash
python run_nsga2.py \
  --population 80 \
  --generations 20 \
  --eval-reps 5 \
  --report-reps 100 \
  --seed 3 \
  --report-seed 2026071701
```

## Preparing another extracted model

Replace the automatically extracted model at:

```text
01- Prepare MDPNML/MDPNML.pnml
```

Then update:

```text
01- Prepare MDPNML/optimization_parameters.json
```

The configuration refers to transitions by exact human-readable names. During preparation, the mapper:

1. resolves each transition name to its current model identifier;
2. checks that each match is unique;
3. reads the reference parameter value from the model;
4. validates the reference value against the specified bounds;
5. writes optimization metadata into the generated model;
6. produces an audit report.

Run only the preparation stage with:

```bash
python "01- Prepare MDPNML/prepare_mdpnml.py"
```

Generated files:

```text
01- Prepare MDPNML/MDPNML_optimization_ready.pnml
01- Prepare MDPNML/optimization_mapping_report.csv
```

## Outputs

The complete workflow writes its results to:

```text
04- Outputs/
```

Main files include:

| File | Description |
|---|---|
| `baseline_reevaluated.csv` | Reference-configuration KPI estimates using the final replication set |
| `nsga2_generation_summary.csv` | Generation-level optimization progress |
| `nsga2_population_history.csv` | Candidate configurations and KPI estimates across generations |
| `nsga2_final_population.csv` | Final NSGA-II population |
| `nsga2_pareto_front_raw.csv` | Search-stage nondominated decision vectors and internal objective values |
| `nsga2_pareto_front_reevaluated_all.csv` | All search-stage nondominated configurations after higher-replication reevaluation |
| `nsga2_pareto_front_reevaluated.csv` | Configurations remaining nondominated after reevaluation |
| `nsga2_pareto_rankings.csv` | Post-search preference scores |
| `nsga2_selected_solutions.csv` | Configurations selected under the implemented preference scenarios |
| `nsga2_energy_emission.png` | Energy–emission projection |
| `nsga2_three_objectives.png` | Three-objective visualization |
| `progress_minimum_energy.png` | Minimum-energy progress by generation |
| `progress_minimum_emission.png` | Minimum-emission progress by generation |
| `progress_maximum_outputs.png` | Maximum-completed-products progress by generation |

Note: The mean_energy values exported by the implementation are expressed in kW·min. The energy values reported in the associated paper were converted to kWh by dividing the exported values by 60.

## Verification checks

The repository includes three optional checks.

```bash
python "05- Test/test_mapping.py"
python "05- Test/test_output_name_mapping.py"
python "05- Test/smoke_test.py"
```

- `test_mapping.py` verifies exact-name mapping and optimization metadata generation.
- `test_output_name_mapping.py` verifies output-transition label resolution.
- `smoke_test.py` checks that changed decision variables are applied to the model and affect the simulation.

The first two checks do not require a full optimization run.

## Reproducibility notes for the paper release

The uploaded implementation should be aligned with the final manuscript before creating the archival release.

1. **Energy unit**  
   The current simulation accumulator stores energy in `kW·min`. Divide by `60` to obtain `kWh`, which is the unit reported in the manuscript. For the archival release, either convert energy to kWh in the evaluation code or rename the output columns to state the raw unit explicitly.

2. **Internal objective scaling**  
   The current optimizer uses reference-scaled objective values internally:

   ```text
   mean energy / reference energy
   mean emission / reference emission
   -mean completed products / reference completed products
   ```

   Raw KPI estimates are still written to the output files. Positive scaling does not change Pareto-dominance relations, but the manuscript and code should describe the same formulation.

3. **Post-search scenario selection**  
   The current `rank_pareto.py` implements five generic weighted preference scenarios. The manuscript's selected scenario instead uses a production-retention threshold and baseline-based energy and emission conditions. Add a dedicated implementation of the manuscript's selection rule, or label the current ranking script as an optional supplementary analysis.

4. **Dependency versions**  
   Replace open-ended dependency ranges with the exact versions used for the paper experiment.

5. **Repository cleanup**  
   Remove `__pycache__/`, compiled `.pyc` files, temporary archives, and other generated files that are not needed for reproduction. Add a `.gitignore`.

## Citation

Pending...
```


## Funding

This work was supported by the ONE4ALL project under the European Union's Horizon Europe Research and Innovation Programme, Grant Agreement No. 101091877.

## Contact

For questions about the implementation, open a GitHub issue or contact:

> Atieh Khodadadi, atieh.khodadadi@kit.edu
> Institute AIFB, Karlsruhe Institute of Technology  

# Optimization-Ready Comprehensive Digital Twin

This repository contains the implementation of an optimization-ready Comprehensive Digital Twin based on MDSPN/MDPNML, with NSGA-II and weighted-sum scalarization for simulation-based multi-objective decision support.

**Simulation-Based Multi-Objective Decision Support for Comprehensive Digital Twins of Smart Manufacturing Systems**

The repository provides two optimization workflows for the same MDSPN-based Comprehensive Digital Twin:

- **NSGA-II:** Pareto-based multi-objective optimization.
- **Weighted-sum scalarization (GA):** equal-weight scalarization solved using a Genetic Algorithm (GA).

Both workflows evaluate candidate configurations through MDPySPN simulation.

## Folder structure

```text
NSGA-II/
└── MDPNML_NSGAII/
    ├── run_nsga2.py
    ├── requirements.txt
    ├── 01- Prepare MDPNML/
    ├── 02- Simulation/
    │   └── components/
    ├── 03- NSGA-II Components/
    ├── 04- Outputs/
    └── 05- Test/

Scalarization-GA/
└── similation/
    ├── run_scalarization_equal_weight.py
    ├── MDPNML.pnml
    ├── ParseMDPNML.py
    ├── components/
    └── scalarization_output/
```

## Optimization problem

The case study uses seven continuous decision variables:

```text
x = (tau_R1, tau_R2, tau_W1, tau_W2, tau_RW, w_R1, w_W1)
```

The optimization considers three objectives:

- minimize grid-energy consumption;
- minimize CO₂ emissions;
- maximize the number of completed products.

For NSGA-II, the three baseline-scaled objective components are retained separately:

```text
F_hat(x) = (
    E_hat(x) / E_hat_base,
    C_hat(x) / C_hat_base,
   -P_hat(x) / P_hat_base
)
```

For weighted-sum scalarization, the same objective components are combined using equal weights:

```text
J_hat(x) =
    (1/3) * E_hat(x) / E_hat_base
  + (1/3) * C_hat(x) / C_hat_base
  - (1/3) * P_hat(x) / P_hat_base
```

No additional simulation-based performance constraints are imposed.

## 1. NSGA-II

### Prepare the model

Place the automatically extracted model at:

```text
NSGA-II/MDPNML_NSGAII/01- Prepare MDPNML/MDPNML.pnml
```

Define the optimizable parameters and bounds in:

```text
NSGA-II/MDPNML_NSGAII/01- Prepare MDPNML/optimization_parameters.json
```

`run_nsga2.py` prepares the optimization-ready MDPNML model before starting the optimization.

### Run

From:

```text
NSGA-II/MDPNML_NSGAII/
```

run:

```bash
python run_nsga2.py
```

The default paper settings are:

```text
Population size:                 80
Generations:                     20
Search-stage replications:        5
Higher-replication reevaluation: 100
Optimization seed:                3
Reevaluation seed:       2026071701
```

Results are written to:

```text
NSGA-II/MDPNML_NSGAII/04- Outputs/
```

### Optional checks

```bash
python "05- Test/test_mapping.py"
python "05- Test/test_output_name_mapping.py"
python "05- Test/smoke_test.py"
```

## 2. Weighted-sum scalarization (GA)

The scalarization workflow uses the same seven decision variables and the same three baseline-scaled objective components as the NSGA-II workflow. The scalarized objective is minimized using a real-valued GA implemented with pymoo.

From:

```text
Scalarization-GA/similation/
```

run:

```bash
python run_scalarization_equal_weight.py
```

The default paper settings are:

```text
Population size:                 80
Generations:                     20
Search-stage replications:        5
Higher-replication reevaluation: 100
Simulation horizon:             480 min
Crossover:                       SBX(prob=0.9, eta=15)
Mutation:                        PM(eta=20)
Duplicate elimination:           enabled
Optimization seed:               3
Reevaluation seed:      2026071701
```

Results are written to:

```text
Scalarization-GA/similation/scalarization_output/
```

The main output files are:

```text
scalarization_best_search_stage.csv
scalarization_baseline_100rep.csv
scalarization_best_100rep.csv
scalarization_settings.csv
```

## Requirements

The NSGA-II workflow uses the packages listed in:

```text
NSGA-II/MDPNML_NSGAII/requirements.txt
```

Install them with:

```bash
pip install -r requirements.txt
```

The scalarization workflow requires the same main Python packages, including `numpy` and `pymoo`.

## Code availability

The repository contains the MDPNML preparation, MDPySPN simulation, NSGA-II optimization, weighted-sum scalarization, higher-replication reevaluation, and result-generation code used in the case study.

## Citation
The software release used for the reported experiments is archived on Zenodo:

Khodadadi, A., & Lazarova-Molnar, S. (2026).  
*Optimization-Ready Comprehensive Digital Twin* (Version 1.0.0). Zenodo.  
https://doi.org/10.5281/zenodo.22015004

Citation information for the corresponding publication will be added upon publication.

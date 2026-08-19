Optimization-Ready Comprehensive Digital Twin
This repository contains the implementation accompanying the manuscript:
> **Simulation-Based Multi-Objective Decision Support for Comprehensive Digital Twins of Smart Manufacturing Systems**  
> Atieh Khodadadi, Sanja Lazarova-Molnar, and Xueping Li
The repository demonstrates how an automatically extracted, simulation-ready Multidimensional Stochastic Petri Net (MDSPN), represented in Multidimensional Petri Net Markup Language (MDPNML), can be prepared and used as an optimization-ready Comprehensive Digital Twin (CDT) for simulation-based multi-objective decision support.
Two optimization formulations are provided:
NSGA-II — a Pareto-based multi-objective evolutionary optimization workflow that retains the three objectives separately and generates a Pareto-front approximation.
Weighted-sum scalarization (GA) — an equal-weight scalarization baseline that combines the same three objective components into a single scalar objective and solves the resulting single-objective problem using a Genetic Algorithm (GA).
Both implementations use the same case-study decision variables, admissible bounds, simulation horizon, search-stage replication count, and higher-replication reevaluation setting.
Case-study objectives
The illustrative manufacturing case study considers three objectives:
minimize grid-energy consumption;
minimize CO₂ emissions;
maximize the number of completed products.
No additional simulation-based performance constraint is imposed during either optimization search. The admissible search space is defined by the decision-variable bounds.
Decision variables
The optimization uses seven continuous decision variables.
Variable	Description	Bounds
`tau_robot1`	Idle-to-shutdown threshold for Robot 1	`[0, 20]` min
`tau_robot2`	Idle-to-shutdown threshold for Robot 2	`[0, 20]` min
`tau_mag1`	Idle-to-shutdown threshold for Welding Machine 1	`[0, 20]` min
`tau_mag2`	Idle-to-shutdown threshold for Welding Machine 2	`[0, 20]` min
`tau_remag`	Idle-to-shutdown threshold for Rework Welding	`[0, 20]` min
`w_robot1`	Routing weight for Robot 1; Robot 2 receives `1 - w_robot1`	`[0, 1]`
`w_mag1`	Routing weight for Welding Machine 1; Welding Machine 2 receives `1 - w_mag1`	`[0, 1]`
For the extracted CDT used in the paper, the baseline decision vector is:
```text
(5, 5, 5, 5, 5, 0.5106082037, 0.4913294798)
```
The routing weights differ slightly from the `0.5/0.5` values used in the reference model because the extracted values are estimated from a finite stochastic event-log sample.
Optimization formulations
NSGA-II
For a candidate decision vector `x`, the extracted CDT is simulated repeatedly and the mean KPI estimates are transformed into the baseline-scaled objective vector
```text
F_hat(x) = (
    E_hat(x) / E_hat_base,
    C_hat(x) / C_hat_base,
   -P_hat(x) / P_hat_base
)
```
where:
`E_hat(x)` is mean grid-energy consumption;
`C_hat(x)` is mean CO₂ emissions;
`P_hat(x)` is the mean number of completed products.
NSGA-II retains these three components separately during the search. At termination, the search-stage nondominated configurations are reevaluated using a larger number of independent simulation replications, and nondominance is recomputed from the updated objective estimates. Stakeholder preferences are applied only after this higher-replication reevaluation.
Weighted-sum scalarization (GA)
The scalarization implementation uses the same three baseline-scaled objective components as the NSGA-II implementation. For the comparative baseline reported in the paper, equal weights are assigned to all three objectives:
```text
J_hat(x) =
    (1/3) * E_hat(x) / E_hat_base
  + (1/3) * C_hat(x) / C_hat_base
  - (1/3) * P_hat(x) / P_hat_base
```
The resulting scalar objective is minimized using a real-valued Genetic Algorithm (GA).
At termination, the configuration with the lowest search-stage scalar objective is retained. The same decision vector and the baseline configuration are then reevaluated using the higher-replication setting, and the objective components and scalar objective are recomputed from the updated KPI estimates.
Repository structure
The repository is organized into two self-contained optimization folders:
```text
Optimization-Ready-Comprehensive-Digital-Twin/
├── README.md
├── LICENSE
├── CITATION.cff
├── .gitignore
│
├── NSGA-II/
│   ├── run_nsga2.py
│   ├── requirements.txt
│   ├── 01- Prepare MDPNML/
│   │   ├── MDPNML.pnml
│   │   ├── MDPNML_optimization_ready.pnml
│   │   ├── optimization_parameters.json
│   │   ├── optimization_mapping_report.csv
│   │   └── prepare_mdpnml.py
│   ├── 02- Simulation/
│   │   ├── ParseMDPNML.py
│   │   ├── bootstrap.py
│   │   ├── kpi_eval.py
│   │   ├── mdpnml_policy.py
│   │   ├── model_factory.py
│   │   ├── optimization_metadata.py
│   │   ├── run_baseline.py
│   │   └── components/
│   ├── 03- NSGA-II Components/
│   │   ├── run_nsga2_core.py
│   │   ├── results_io.py
│   │   ├── rank_pareto.py
│   │   └── plot_utils.py
│   ├── 04- Outputs/
│   └── 05- Test/
│       ├── README.txt
│       ├── test_mapping.py
│       ├── test_output_name_mapping.py
│       └── smoke_test.py
│
└── Scalarization-GA/
    ├── run_scalarization_equal_weight.py
    ├── requirements.txt
    ├── MDPNML.pnml
    ├── ParseMDPNML.py
    ├── components/
    └── scalarization_output/
        ├── scalarization_best_search_stage.csv
        ├── scalarization_baseline_100rep.csv
        ├── scalarization_best_100rep.csv
        └── scalarization_settings.csv
```
`Scalarization-GA` is used as the folder name rather than `Scalarization (GA)` to avoid spaces and parentheses in command-line paths. The manuscript can continue to refer to the method as weighted-sum scalarization solved using a Genetic Algorithm (GA).
Requirements
The implementations require Python 3.11 or newer and the packages specified in the corresponding `requirements.txt` files.
The main dependencies include:
NumPy
pandas
SciPy
Matplotlib
pymoo
openpyxl
Install the requirements for the selected workflow before execution.
For NSGA-II:
```bash
cd NSGA-II
python -m pip install -r requirements.txt
```
For scalarization:
```bash
cd Scalarization-GA
python -m pip install -r requirements.txt
```
For the archival paper release, the exact package versions used for the reported experiments should be pinned in the requirements files.
Running the NSGA-II workflow
From the `NSGA-II` folder:
```bash
python run_nsga2.py
```
The workflow prepares the optimization-ready MDPNML model, validates the decision-to-model mapping, evaluates the baseline configuration, executes the NSGA-II search, reevaluates the search-stage nondominated configurations, recomputes nondominance, and generates the corresponding result files.
A small installation test can be run with:
```bash
python run_nsga2.py --population 10 --generations 2 --eval-reps 2 --report-reps 5
```
The paper experiment uses:
```bash
python run_nsga2.py \
  --population 80 \
  --generations 20 \
  --eval-reps 5 \
  --report-reps 100 \
  --seed 3 \
  --report-seed 2026071701
```
On Windows Command Prompt, enter the command on one line.
Running the weighted-sum scalarization workflow
From the `Scalarization-GA` folder:
```bash
python run_scalarization_equal_weight.py
```
The implementation:
reads the baseline decision vector from the MDPNML model;
evaluates the baseline configuration;
applies equal-weight weighted-sum scalarization to the three baseline-scaled objective components;
solves the resulting scalarized problem using a real-valued GA;
retains the best search-stage scalarized configuration;
reevaluates the baseline and scalarized configurations using 100 independent replications; and
writes the final scalarization results to `scalarization_output/`.
The paper experiment uses:
Setting	Value
Simulation horizon	`480` min
Population size	`80`
Generations	`20`
Search-stage replications	`5`
Higher-replication reevaluation	`100`
Crossover	`SBX(prob=0.9, eta=15)`
Mutation	`PM(eta=20)`
Duplicate elimination	Enabled
Scalarization weights	`1/3, 1/3, 1/3`
Additional simulation-based constraints	None
Case-study experimental settings
The two optimization workflows use equivalent case-study settings wherever applicable.
Setting	NSGA-II	Weighted-sum scalarization
Simulation horizon	`480` min	`480` min
Decision variables	`7` continuous	`7` continuous
Search-stage replications	`5`	`5`
Higher-replication reevaluation	`100`	`100`
Population size	`80`	`80`
Termination	`20` generations	`20` generations
Objective treatment	Three components retained separately	Equal-weight scalar objective
Objective weights	None	`1/3, 1/3, 1/3`
Optimizer	NSGA-II	Genetic Algorithm (GA)
Duplicate elimination	Enabled	Enabled
Additional simulation-based constraints	None	None
Within each evaluation stage, the same replication-seed set is applied across candidate configurations for consistent stochastic comparison. A separate seed set is used for the higher-replication reevaluation.
NSGA-II outputs
The main NSGA-II result files are written to:
```text
NSGA-II/04- Outputs/
```
Main files include:
File	Description
`baseline_reevaluated.csv`	Baseline-configuration KPI estimates using the final replication set
`nsga2_generation_summary.csv`	Generation-level optimization progress
`nsga2_population_history.csv`	Candidate configurations and KPI estimates across generations
`nsga2_final_population.csv`	Final NSGA-II population
`nsga2_pareto_front_raw.csv`	Search-stage nondominated decision vectors and objective estimates
`nsga2_pareto_front_reevaluated_all.csv`	All search-stage nondominated configurations after higher-replication reevaluation
`nsga2_pareto_front_reevaluated.csv`	Configurations remaining nondominated after reevaluation
`nsga2_pareto_rankings.csv`	Post-search preference results
`nsga2_selected_solutions.csv`	Configurations selected under the implemented preference rule
`nsga2_energy_emission.png`	Grid-energy–CO₂ projection
`nsga2_three_objectives.png`	Three-objective visualization
Scalarization outputs
The scalarization result files are written to:
```text
Scalarization-GA/scalarization_output/
```
File	Description
`scalarization_best_search_stage.csv`	Best scalarized configuration using the search-stage estimates
`scalarization_baseline_100rep.csv`	Baseline configuration after 100-replication reevaluation
`scalarization_best_100rep.csv`	Scalarized configuration after 100-replication reevaluation
`scalarization_settings.csv`	Scalarization and GA settings used for the experiment
Verification checks
The NSGA-II implementation includes optional checks for the MDPNML decision-to-model mapping and model execution:
```bash
cd NSGA-II
python "05- Test/test_mapping.py"
python "05- Test/test_output_name_mapping.py"
python "05- Test/smoke_test.py"
```
The checks verify:
exact transition-name mapping and optimization metadata generation;
output-transition label resolution; and
whether changes in the decision variables are applied to the model and affect simulation behavior.
Reproducibility notes
Before creating the archival release associated with the manuscript:
Use the final code and data reported in the manuscript. Remove temporary files, local test outputs, `__pycache__/` folders, compiled `.pyc` files, and unused archives.
Pin dependency versions. Record the exact package versions used for the reported experiments.
Use consistent terminology. `baseline configuration` refers to the extracted-CDT configuration used for objective scaling. `reference model` refers to the independently developed AnyLogic model used in the paper for validation and final scenario evaluation.
Keep energy units explicit. The manuscript reports grid-energy consumption in kWh. If any raw NSGA-II output remains stored in kW·min, either convert the exported value to kWh or label the raw output column explicitly.
Ensure that the implemented post-search selection rule matches the manuscript. The paper uses a production-retention requirement together with baseline-based energy and emission conditions before the final equally weighted energy/emission selection.
Create an archival release. Tag the exact version used for the revised manuscript and archive the release with a persistent DOI.
Add a software license and citation metadata. Include `LICENSE` and `CITATION.cff` files at the repository root.
License
Add the selected open-source software license in the root `LICENSE` file before the archival release.
Citation
Citation information for the manuscript and the archived software release should be provided in `CITATION.cff`.
Manuscript:
> Atieh Khodadadi, Sanja Lazarova-Molnar, and Xueping Li,  
> **Simulation-Based Multi-Objective Decision Support for Comprehensive Digital Twins of Smart Manufacturing Systems.**
Add the final journal citation and archival software DOI when available.
Funding
This work was supported by the ONE4ALL project under the European Union's Horizon Europe Research and Innovation Programme, Grant Agreement No. 101091877.
Contact
For questions about the implementation, open a GitHub issue or contact:
> Atieh Khodadadi  
> Institute AIFB, Karlsruhe Institute of Technology

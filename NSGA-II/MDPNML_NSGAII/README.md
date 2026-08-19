# MDPNML-based NSGA-II

## Folder structure

```text
run_nsga2.py
01- Prepare MDPNML/
02- Simulation/
    components/
03- NSGA-II Components/
04- Outputs/
05- Test/
```

## 1. Supply the latest model

Copy or replace the automatically extracted model at:

```text
01- Prepare MDPNML/MDPNML.pnml
```

Define the optimizable parameters and bounds in:

```text
01- Prepare MDPNML/optimization_parameters.json
```

You do **not** need to run the preparation script separately. The root
`run_nsga2.py` regenerates these files before every optimization run:

- `MDPNML_optimization_ready.pnml`
- `optimization_mapping_report.csv`

The mapper resolves exact transition names from the JSON configuration and
stores the corresponding transition IDs in the optimization metadata.

## 2. Add the simulator

Copy the complete contents of your original MDPySPN `components` folder into:

```text
02- Simulation/components/
```

The directory must contain at least `spn.py`, `spn_simulate.py`, and the other
files required by your simulator.

## 3. Run everything with one command

From the project root:

```bash
python run_nsga2.py
```

This command first prepares the latest MDPNML and starts NSGA-II only when the
mapping succeeds.

Small trial:

```bash
python run_nsga2.py --population 10 --generations 2 --eval-reps 2 --report-reps 5
```

All generated tables and figures are written to:

```text
04- Outputs/
```

## Optional manual preparation

You may still run the preparation stage alone when you only want to inspect the
mapping report:

```bash
python "01- Prepare MDPNML/prepare_mdpnml.py"
```

## Optional checks

```bash
python "05- Test/test_mapping.py"
python "05- Test/test_output_name_mapping.py"
python "05- Test/smoke_test.py"
```

The checks are safeguards only. They are not required by NSGA-II.

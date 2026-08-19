The files in this folder are optional verification checks. They are not used by
NSGA-II during a normal optimization run.

1. test_mapping.py
   Checks that exact transition names in optimization_parameters.json are found
   once in MDPNML.pnml and that the optimization-ready MDPNML is generated.

2. test_output_name_mapping.py
   Prevents the earlier error where Transition objects were converted to memory
   addresses instead of labels such as MAG1 Completed.

3. smoke_test.py
   Runs a very small baseline-versus-changed-policy simulation to confirm that
   candidate parameters are actually applied and affect the simulated model.

You may keep these files for safety or delete the whole 05- Test folder after
all checks pass. The root run_nsga2.py does not import this folder.

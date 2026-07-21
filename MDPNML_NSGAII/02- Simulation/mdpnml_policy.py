"""Apply an optimizer candidate to a freshly parsed executable MDSPN."""

from __future__ import annotations

from typing import Mapping

from optimization_metadata import OptimizationSpec, policy_dict_from_vector


def _set_transition_field(transition, field: str, value: float) -> None:
    if field == "weight":
        transition.set_weight(float(value))
        return

    prefix = "distribution.parameters."
    if field.startswith(prefix):
        parameter_name = field[len(prefix):]
        distribution_type = getattr(transition, "mdpnml_distribution_type", None)
        distribution_params = dict(
            getattr(transition, "mdpnml_distribution_params", {}) or {}
        )
        if not distribution_type:
            raise ValueError(
                f"Transition {getattr(transition, 'mdpnml_id', transition)} "
                "does not have a parsed distribution."
            )
        distribution_params[parameter_name] = float(value)
        transition.set_distribution(
            distribution_type,
            a=distribution_params.get("a", 0.0),
            b=distribution_params.get("b", 0.0),
            c=distribution_params.get("c", 0.0),
            d=distribution_params.get("d", 0.0),
            **{
                key: val
                for key, val in distribution_params.items()
                if key not in {"a", "b", "c", "d"}
            },
        )
        transition.mdpnml_distribution_params = distribution_params
        return

    raise ValueError(f"Unsupported optimization target field: {field}")


def apply_policy(
    spn_model,
    spec: OptimizationSpec,
    policy: Mapping[str, float] | None = None,
    vector=None,
):
    """Apply a named policy or decision vector to ``spn_model`` in memory."""
    if policy is None:
        if vector is None:
            raise ValueError("Provide either policy or vector.")
        policy = policy_dict_from_vector(spec, vector)

    transitions = getattr(spn_model, "transitions_by_id", None)
    if not transitions:
        raise AttributeError(
            "Parsed model does not expose transitions_by_id. Use the included ParseMDPNML.py."
        )

    unknown = set(policy) - set(spec.names)
    if unknown:
        raise ValueError(f"Unknown policy variables: {sorted(unknown)}")

    for parameter in spec.parameters:
        value = float(policy.get(parameter.name, parameter.baseline))
        if not parameter.lower <= value <= parameter.upper:
            raise ValueError(
                f"{parameter.name}={value} is outside "
                f"[{parameter.lower}, {parameter.upper}]."
            )
        for target in parameter.targets:
            if target.transition_id not in transitions:
                raise KeyError(
                    f"Transition {target.transition_id} for {parameter.name} "
                    "was not found in the parsed MDPNML model."
                )
            target_value = 1.0 - value if target.complement else value
            _set_transition_field(
                transitions[target.transition_id], target.field, target_value
            )

    spn_model.optimization_policy = dict(policy)
    return spn_model

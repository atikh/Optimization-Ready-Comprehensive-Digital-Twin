"""Convert a raw extracted MDPNML file into an optimization-ready MDPNML file.

Mapping strategy
----------------
The external JSON configuration refers to transitions by their exact
``<transition><name><text>...`` label.  The mapper resolves each label to the
current MDPNML transition ID, validates that the match is unique, reads the
baseline value from the raw model, and writes an ``MDSPN-Optimization``
metadata block containing the resolved IDs.

The optimization runtime therefore uses IDs, while the user-maintained
configuration remains readable and survives changes in generated IDs.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import xml.etree.ElementTree as ET

PNML_NS = "http://www.pnml.org/version-2009/grammar/pnml"
ET.register_namespace("", PNML_NS)


def _q(local: str) -> str:
    return f"{{{PNML_NS}}}{local}"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _first_child(parent: ET.Element, local_name: str) -> ET.Element | None:
    return next((c for c in list(parent) if _local(c.tag) == local_name), None)


def _first_descendant(parent: ET.Element, local_name: str) -> ET.Element | None:
    return next((e for e in parent.iter() if _local(e.tag) == local_name), None)


def _transition_label(transition: ET.Element) -> str:
    name = _first_child(transition, "name")
    if name is not None:
        text = _first_descendant(name, "text")
        if text is not None and text.text is not None:
            return text.text.strip()
    return ""


def _index_transitions(root: ET.Element):
    by_id: dict[str, ET.Element] = {}
    by_name: dict[str, list[ET.Element]] = {}
    for element in root.iter():
        if _local(element.tag) != "transition":
            continue
        transition_id = str(element.get("id", "")).strip()
        if not transition_id:
            raise ValueError("A transition without an id was found.")
        label = _transition_label(element)
        by_id[transition_id] = element
        by_name.setdefault(label, []).append(element)
    return by_id, by_name


def _resolve_transition(ref: dict, by_id, by_name) -> tuple[ET.Element, str]:
    if ref.get("transition_id"):
        transition_id = str(ref["transition_id"])
        if transition_id not in by_id:
            raise KeyError(f"Transition id {transition_id!r} was not found.")
        element = by_id[transition_id]
        return element, _transition_label(element)

    label = str(ref.get("transition_name", "")).strip()
    if not label:
        raise ValueError("Each target needs transition_name or transition_id.")
    matches = by_name.get(label, [])
    if not matches:
        available = sorted(name for name in by_name if name)
        raise KeyError(
            f"Exact transition name {label!r} was not found. "
            f"Available names include: {available}"
        )
    if len(matches) != 1:
        ids = [m.get("id") for m in matches]
        raise ValueError(
            f"Transition name {label!r} is not unique; matching ids: {ids}. "
            "Use transition_id in the JSON mapping for this target."
        )
    return matches[0], label


def _read_target_value(transition: ET.Element, field: str) -> float:
    if field == "weight":
        weight = _first_descendant(transition, "weight")
        if weight is None or weight.text is None:
            return 1.0
        return float(weight.text.strip())

    prefix = "distribution.parameters."
    if field.startswith(prefix):
        parameter_name = field[len(prefix):]
        distribution = _first_descendant(transition, "distribution")
        if distribution is None:
            raise ValueError(
                f"Transition {_transition_label(transition)!r} has no distribution."
            )
        parameters = _first_child(distribution, "parameters")
        if parameters is None:
            raise ValueError(
                f"Transition {_transition_label(transition)!r} has no distribution parameters."
            )
        parameter = _first_child(parameters, parameter_name)
        if parameter is None or parameter.text is None:
            raise ValueError(
                f"Transition {_transition_label(transition)!r} has no parameter {parameter_name!r}."
            )
        return float(parameter.text.strip())

    raise ValueError(f"Unsupported target field {field!r}.")


def _dimension_names(root: ET.Element) -> set[str]:
    return {
        str(element.get("name"))
        for element in root.iter()
        if _local(element.tag) in {"dimension", "subdimension", "subDimension"}
        and element.get("name")
    }


def _remove_old_metadata(net: ET.Element) -> None:
    for child in list(net):
        if _local(child.tag) == "toolspecific" and child.get("tool") == "MDSPN-Optimization":
            net.remove(child)


def prepare_optimization_model(
    input_path: str | Path,
    config_path: str | Path,
    output_path: str | Path,
    report_path: str | Path | None = None,
) -> Path:
    input_path = Path(input_path)
    config_path = Path(config_path)
    output_path = Path(output_path)
    config = json.loads(config_path.read_text(encoding="utf-8"))

    if config.get("matching_rule", "exact_transition_name") != "exact_transition_name":
        raise ValueError("Only exact_transition_name matching is supported.")

    tree = ET.parse(input_path)
    root = tree.getroot()
    net = next((e for e in root.iter() if _local(e.tag) == "net"), None)
    if net is None:
        raise ValueError("No PNML net element was found.")
    by_id, by_name = _index_transitions(root)
    dimensions = _dimension_names(root)

    _remove_old_metadata(net)
    toolspecific = ET.Element(
        _q("toolspecific"),
        {"tool": "MDSPN-Optimization", "version": "1.0"},
    )
    model = ET.SubElement(
        toolspecific,
        _q("optimizationModel"),
        {
            "horizon": str(config.get("horizon", 480)),
            "replicationSeedMode": "common-random-numbers",
            "mappingSource": "exact-transition-name",
        },
    )
    parameters_parent = ET.SubElement(model, _q("optimizationParameters"))
    report_rows: list[dict] = []

    parameter_ids: set[str] = set()
    for parameter in config.get("parameters", []):
        parameter_id = str(parameter["id"])
        if parameter_id in parameter_ids:
            raise ValueError(f"Duplicate parameter id {parameter_id!r}.")
        parameter_ids.add(parameter_id)

        target_element, target_label = _resolve_transition(
            parameter["target"], by_id, by_name
        )
        target_id = str(target_element.get("id"))
        field = str(parameter["target"]["field"])
        baseline = _read_target_value(target_element, field)
        lower = float(parameter["lower_bound"])
        upper = float(parameter["upper_bound"])
        if lower >= upper:
            raise ValueError(f"Invalid bounds for {parameter_id}.")
        if not lower <= baseline <= upper:
            raise ValueError(
                f"Baseline {baseline} for {parameter_id} is outside [{lower}, {upper}]."
            )

        p = ET.SubElement(
            parameters_parent,
            _q("parameter"),
            {
                "id": parameter_id,
                "type": str(parameter.get("type", "continuous")),
                "lowerBound": str(lower),
                "upperBound": str(upper),
                "baselineValue": repr(float(baseline)),
            },
        )
        ET.SubElement(
            p,
            _q("target"),
            {
                "transition": target_id,
                "transitionName": target_label,
                "field": field,
            },
        )
        report_rows.append(
            {
                "parameter": parameter_id,
                "role": "target",
                "transition_name": target_label,
                "resolved_transition_id": target_id,
                "field": field,
                "baseline_value": baseline,
                "lower_bound": lower,
                "upper_bound": upper,
            }
        )

        complement = parameter.get("complement_target")
        if complement:
            comp_element, comp_label = _resolve_transition(complement, by_id, by_name)
            comp_id = str(comp_element.get("id"))
            comp_field = str(complement["field"])
            comp_baseline = _read_target_value(comp_element, comp_field)
            if field == "weight" and comp_field == "weight":
                if abs((baseline + comp_baseline) - 1.0) > 1e-6:
                    raise ValueError(
                        f"Complementary baseline weights for {parameter_id} do not sum to 1: "
                        f"{baseline} + {comp_baseline}."
                    )
            ET.SubElement(
                p,
                _q("complementTarget"),
                {
                    "transition": comp_id,
                    "transitionName": comp_label,
                    "field": comp_field,
                },
            )
            report_rows.append(
                {
                    "parameter": parameter_id,
                    "role": "complementTarget",
                    "transition_name": comp_label,
                    "resolved_transition_id": comp_id,
                    "field": comp_field,
                    "baseline_value": comp_baseline,
                    "lower_bound": "1 - upper",
                    "upper_bound": "1 - lower",
                }
            )

    objectives_parent = ET.SubElement(model, _q("optimizationObjectives"))
    for objective in config.get("objectives", []):
        attrs = {
            "id": str(objective["id"]),
            "source": str(objective["source"]),
            "direction": str(objective.get("direction", "min")),
        }
        if objective["source"] == "dimension":
            name = str(objective["name"])
            if name not in dimensions:
                raise KeyError(
                    f"Objective dimension {name!r} was not found. Available: {sorted(dimensions)}"
                )
            attrs["name"] = name
        elif objective["source"] == "outputTransitions":
            ids = []
            labels = []
            for label in objective.get("transition_names", []):
                element, resolved_label = _resolve_transition(
                    {"transition_name": label}, by_id, by_name
                )
                if str(element.get("output_transition", "")).lower() not in {"1", "true", "yes"}:
                    raise ValueError(
                        f"Configured output transition {resolved_label!r} is not marked output_transition=True."
                    )
                ids.append(str(element.get("id")))
                labels.append(resolved_label)
            if not ids:
                raise ValueError("The outputs objective has no transition_names.")
            attrs["transitions"] = ",".join(ids)
            attrs["transitionNames"] = "|".join(labels)
        else:
            raise ValueError(f"Unsupported objective source {objective['source']!r}.")
        ET.SubElement(objectives_parent, _q("objective"), attrs)

    # Insert metadata before the first page for readability.
    net.insert(0, toolspecific)
    ET.indent(tree, space="  ")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(output_path, encoding="utf-8", xml_declaration=True)

    if report_path is not None:
        report_path = Path(report_path)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with report_path.open("w", newline="", encoding="utf-8") as stream:
            fieldnames = [
                "parameter", "role", "transition_name", "resolved_transition_id",
                "field", "baseline_value", "lower_bound", "upper_bound"
            ]
            writer = csv.DictWriter(stream, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(report_rows)

    return output_path


def parse_args() -> argparse.Namespace:
    folder = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="Map MDPNML.pnml to an optimization-ready MDPNML file."
    )
    parser.add_argument(
        "--input", type=Path,
        default=folder / "MDPNML.pnml",
        help="Raw automatically extracted MDPNML file."
    )
    parser.add_argument(
        "--config", type=Path,
        default=folder / "optimization_parameters.json",
        help="Optimization parameter definitions and objective mapping."
    )
    parser.add_argument(
        "--output", type=Path,
        default=folder / "MDPNML_optimization_ready.pnml",
        help="Generated MDPNML file used by simulation and optimization."
    )
    parser.add_argument(
        "--report", type=Path,
        default=folder / "optimization_mapping_report.csv",
        help="Audit table showing exact transition-name to ID mapping."
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output = prepare_optimization_model(
        args.input, args.config, args.output, args.report
    )
    print(f"Created optimization-ready MDPNML: {output.resolve()}")
    print(f"Mapping report: {args.report.resolve()}")


if __name__ == "__main__":
    main()

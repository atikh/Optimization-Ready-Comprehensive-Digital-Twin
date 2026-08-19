"""Read optimization variables and objective declarations from MDPNML."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import xml.etree.ElementTree as ET


@dataclass(frozen=True)
class TargetSpec:
    transition_id: str
    field: str
    complement: bool = False


@dataclass(frozen=True)
class ParameterSpec:
    name: str
    variable_type: str
    lower: float
    upper: float
    baseline: float
    targets: tuple[TargetSpec, ...]


@dataclass(frozen=True)
class ObjectiveSpec:
    name: str
    source: str
    direction: str
    dimension_name: str | None = None
    transition_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class OptimizationSpec:
    horizon: float
    parameters: tuple[ParameterSpec, ...]
    objectives: tuple[ObjectiveSpec, ...]

    @property
    def names(self) -> list[str]:
        return [p.name for p in self.parameters]

    @property
    def lower_bounds(self) -> list[float]:
        return [p.lower for p in self.parameters]

    @property
    def upper_bounds(self) -> list[float]:
        return [p.upper for p in self.parameters]

    @property
    def baseline_vector(self) -> list[float]:
        return [p.baseline for p in self.parameters]


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _children_by_name(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in list(element) if _local_name(child.tag) == name]


def _first_descendant(root: ET.Element, name: str) -> ET.Element | None:
    return next((el for el in root.iter() if _local_name(el.tag) == name), None)


def load_optimization_spec(pnml_path: str | Path) -> OptimizationSpec:
    path = Path(pnml_path)
    root = ET.parse(path).getroot()

    toolspecific = None
    for el in root.iter():
        if _local_name(el.tag) == "toolspecific" and el.get("tool") == "MDSPN-Optimization":
            toolspecific = el
            break
    if toolspecific is None:
        raise ValueError(
            f"{path} does not contain a toolspecific block with "
            "tool='MDSPN-Optimization'. Use the optimization-ready MDPNML.pnml."
        )

    model = _first_descendant(toolspecific, "optimizationModel")
    if model is None:
        raise ValueError("Missing optimizationModel element in MDPNML metadata.")
    horizon = float(model.get("horizon", "480"))

    parameters_parent = _first_descendant(model, "optimizationParameters")
    if parameters_parent is None:
        raise ValueError("Missing optimizationParameters element in MDPNML metadata.")

    parameters: list[ParameterSpec] = []
    for element in _children_by_name(parameters_parent, "parameter"):
        targets: list[TargetSpec] = []
        for target in _children_by_name(element, "target"):
            targets.append(
                TargetSpec(
                    transition_id=str(target.get("transition")),
                    field=str(target.get("field")),
                    complement=False,
                )
            )
        for target in _children_by_name(element, "complementTarget"):
            targets.append(
                TargetSpec(
                    transition_id=str(target.get("transition")),
                    field=str(target.get("field")),
                    complement=True,
                )
            )
        if not targets:
            raise ValueError(f"Optimization parameter {element.get('id')} has no targets.")

        lower = float(element.get("lowerBound", "0"))
        upper = float(element.get("upperBound", "1"))
        baseline = float(element.get("baselineValue", str(lower)))
        if not lower <= baseline <= upper:
            raise ValueError(
                f"Baseline for {element.get('id')} ({baseline}) is outside [{lower}, {upper}]."
            )

        parameters.append(
            ParameterSpec(
                name=str(element.get("id")),
                variable_type=str(element.get("type", "continuous")),
                lower=lower,
                upper=upper,
                baseline=baseline,
                targets=tuple(targets),
            )
        )

    objectives_parent = _first_descendant(model, "optimizationObjectives")
    objectives: list[ObjectiveSpec] = []
    if objectives_parent is not None:
        for element in _children_by_name(objectives_parent, "objective"):
            transition_ids = tuple(
                value.strip()
                for value in str(element.get("transitions", "")).split(",")
                if value.strip()
            )
            objectives.append(
                ObjectiveSpec(
                    name=str(element.get("id")),
                    source=str(element.get("source", "dimension")),
                    direction=str(element.get("direction", "min")).lower(),
                    dimension_name=element.get("name"),
                    transition_ids=transition_ids,
                )
            )

    spec = OptimizationSpec(
        horizon=horizon,
        parameters=tuple(parameters),
        objectives=tuple(objectives),
    )
    validate_optimization_spec(spec)
    return spec


def validate_optimization_spec(spec: OptimizationSpec) -> None:
    if not spec.parameters:
        raise ValueError("No optimization parameters were declared.")
    if len(set(spec.names)) != len(spec.names):
        raise ValueError("Optimization parameter IDs must be unique.")
    for parameter in spec.parameters:
        if parameter.variable_type != "continuous":
            raise ValueError(
                f"This NSGA-II implementation currently expects continuous variables; "
                f"{parameter.name} is {parameter.variable_type}."
            )
        if parameter.lower >= parameter.upper:
            raise ValueError(f"Invalid bounds for {parameter.name}.")


def policy_dict_from_vector(spec: OptimizationSpec, vector) -> dict[str, float]:
    values = list(vector)
    if len(values) != len(spec.parameters):
        raise ValueError(
            f"Expected {len(spec.parameters)} variables {spec.names}, received {len(values)}."
        )
    return {parameter.name: float(value) for parameter, value in zip(spec.parameters, values)}

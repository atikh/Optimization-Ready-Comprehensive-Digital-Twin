import xml.etree.ElementTree as ET
from components import spn


def _as_bool(v):
    if v is None:
        return False
    return str(v).strip().lower() in ("1", "true", "yes")



def _as_float(v, default=0.0):
    if v is None:
        return default
    try:
        return float(str(v).strip())
    except (ValueError, TypeError):
        return default


def _rebuild_executable_dimensions(spn_model):
    spn_model.executable_dimensions = []
    for dim in getattr(spn_model, "dimensions", []):
        if dim in getattr(spn_model, "subdimensions", {}):
            spn_model.executable_dimensions.extend(spn_model.subdimensions[dim])
        else:
            spn_model.executable_dimensions.append(dim)

    if not hasattr(spn_model, "initial_dimension_values") or spn_model.initial_dimension_values is None:
        spn_model.initial_dimension_values = {}

    for dim in spn_model.executable_dimensions:
        if spn.is_time_dimension(dim):
            spn_model.initial_dimension_values[dim] = 0.0
        elif dim not in spn_model.initial_dimension_values:
            spn_model.initial_dimension_values[dim] = 0.0


def _make_guard(spn_model, conditions):
    def guard():
        for dim, operator, value in conditions:
            current = spn_model.get_dimension_value(dim)
            if current is None:
                return False
            current = float(current)
            if operator == "<=":
                ok = current <= value
            elif operator == "<":
                ok = current < value
            elif operator == ">=":
                ok = current >= value
            elif operator == ">":
                ok = current > value
            elif operator in ("=", "=="):
                ok = current == value
            elif operator in ("!=", "<>"):
                ok = current != value
            else:
                ok = False
            if not ok:
                return False
        return True
    return guard



def _infer_charging_battery_dim(element, ns):
    """Infer battery subdimension for old/incomplete charge distributions.

    Priority:
      1) impactedDimension with impactType charge: source/name/dimension
      2) condition source/dimension if it looks like a battery subdimension
      3) transition label fallback for the current AGV example
    """
    # 1) Best source: the charge impactedDimension
    for dc in element.findall(".//mdpnml:impactedDimensions/mdpnml:impactedDimension", ns):
        ctype_el = dc.find("mdpnml:impactType", ns)
        ctype = (ctype_el.text or "").strip().lower() if ctype_el is not None else ""
        if ctype in {"charge", "charging"}:
            dim = dc.get("source") or dc.get("dimension") or dc.get("name")
            if dim and dim.strip() and dim.strip().lower() != "battery":
                return dim.strip()

    # 2) Fallback: condition source such as BatteryH <= 30
    for cond in element.findall(".//mdpnml:conditions/mdpnml:condition", ns):
        dim = cond.get("source") or cond.get("dimension")
        if dim and dim.strip() and dim.strip().lower() != "battery":
            return dim.strip()

    # 3) Last-resort fallback for this model family
    name_el = element.find(".//mdpnml:name/mdpnml:text", ns)
    label = name_el.text if name_el is not None and name_el.text is not None else ""
    if "BatteryH" in label or "AGVHigh" in label:
        return "BatteryH"
    if "BatteryL" in label or "AGVLow" in label:
        return "BatteryL"

    return None

def parse_mdpnml_to_spn(mdpnml):
    print(f"\nParsing PNML file: {mdpnml}")
    tree = ET.parse(mdpnml)
    root = tree.getroot()
    ns = {'mdpnml': 'http://www.pnml.org/version-2009/grammar/pnml'}

    # ---- DIMENSIONS ---------------------------------------------------------
    dims = []
    subdims = {}
    initial_values = {}

    for d in root.findall(".//mdpnml:dimensions/mdpnml:dimension", ns):
        name = d.get("name")
        if not name:
            continue
        dims.append(name)

        dim_initial = _as_float(d.get("initialValue"), 0.0)
        children = []

        # Accept both <subdimension> and <subDimension>, namespaced or not.
        sub_nodes = []
        sub_nodes.extend(d.findall("mdpnml:subdimension", ns))
        sub_nodes.extend(d.findall("mdpnml:subDimension", ns))
        sub_nodes.extend([x for x in list(d) if x.tag.split("}")[-1] in {"subdimension", "subDimension"}])

        seen_subs = set()
        for sd in sub_nodes:
            sd_name = sd.get("name")
            if not sd_name or sd_name in seen_subs:
                continue
            seen_subs.add(sd_name)
            children.append(sd_name)
            initial_values[sd_name] = _as_float(sd.get("initialValue"), dim_initial)

        if children:
            subdims[name] = children
        else:
            initial_values[name] = 0.0 if spn.is_time_dimension(name) else dim_initial

    spn_model = spn.SPN(dimensions=dims, subdimensions=subdims, initial_dimension_values=initial_values)
    _rebuild_executable_dimensions(spn_model)

    places_dict = {}
    transitions_dict = {}

    # ---- PLACES -------------------------------------------------------------
    print("Parsing places.")
    for element in root.findall(".//mdpnml:place", ns):
        place_id = element.get('id')

        label_el = element.find(".//mdpnml:name/mdpnml:text", ns)
        fallback_text = element.find(".//mdpnml:text", ns)
        label = label_el.text if label_el is not None else (fallback_text.text if fallback_text is not None else place_id)

        im_el = element.find(".//mdpnml:initialMarking/mdpnml:text", ns)
        n_tokens = int(float(im_el.text)) if im_el is not None and im_el.text is not None else 0

        DoT_attr = element.get("DoT")
        dim_tracked = element.get("dimensionTracked") or element.get("dimension_tracked")

        place_kwargs = {}
        if dim_tracked:
            place_kwargs["dimension_tracked"] = dim_tracked

        if DoT_attr is not None and str(DoT_attr).strip() != "":
            try:
                place_kwargs["DoT"] = float(DoT_attr) if "." in str(DoT_attr) else int(DoT_attr)
            except ValueError:
                place_kwargs["DoT"] = DoT_attr
        elif dim_tracked:
            place_kwargs["DoT"] = 1

        place = spn.Place(label, n_tokens, **place_kwargs)
        places_dict[place_id] = place
        spn_model.add_place(place)

    # ---- TRANSITIONS --------------------------------------------------------
    print("Parsing transitions.")
    for element in root.findall(".//mdpnml:transition", ns):
        transition_id = element.get('id')
        t_type = element.get('type')
        name_el = element.find(".//mdpnml:name/mdpnml:text", ns)
        fallback_text = element.find(".//mdpnml:text", ns)
        name = name_el.text if name_el is not None else (fallback_text.text if fallback_text is not None else transition_id)

        transition = spn.Transition(
            name,
            t_type,
            parallel_timing=_as_bool(element.get("parallel_timing")),
            asset_level=_as_bool(element.get("asset_level")),
            input_transition=_as_bool(element.get("input_transition")),
            output_transition=_as_bool(element.get("output_transition")),
        )

        dist_type, dist_params = parse_distribution(element, ns)

        # Robustness for charge distributions from older/incomplete PNML exports:
        # spn.Transition.set_distribution("charging") requires battery_dim.
        # If the parameter is missing, infer it from the charge impactedDimension
        # instead of crashing during parsing.
        if dist_type == "charging" and not dist_params.get("battery_dim"):
            inferred_battery_dim = _infer_charging_battery_dim(element, ns)
            if inferred_battery_dim:
                dist_params["battery_dim"] = inferred_battery_dim

        if t_type == "T" and dist_type:
            transition.set_distribution(
                dist_type,
                a=dist_params.get("a", 0.0),
                b=dist_params.get("b", 0.0),
                c=dist_params.get("c", 0.0),
                d=dist_params.get("d", 0.0),
                **{k: v for k, v in dist_params.items() if k not in ("a", "b", "c", "d")}
            )
        elif t_type == "I":
            weight_elem = element.find(".//mdpnml:weight", ns)
            # Missing <weight> in PNML means default executable immediate weight 1.0.
            # Without this, impacted *_ready transitions can be present in the graph
            # but not participate correctly in simulation.
            weight_value = 1.0
            if weight_elem is not None and weight_elem.text is not None:
                weight_value = _as_float(weight_elem.text, 1.0)
            transition.set_weight(weight_value)

        # Conditions / guards, e.g. BatteryH <= 30.
        guard_conditions = []
        for cond in element.findall(".//mdpnml:conditions/mdpnml:condition", ns):
            dim = cond.get("source") or cond.get("dimension")
            operator = (cond.get("operator") or cond.get("op") or "").strip()
            value = cond.get("value")

            # Robust fallback: read operator from condition text, e.g. "BatteryH <= 30.0"
            cond_text = (cond.text or "").strip()
            if not operator and cond_text:
                for op in ["<=", ">=", "!=", "<>", "==", "<", ">", "="]:
                    if op in cond_text:
                        operator = op
                        break

            # Threshold conditions from exporter mean <= by default
            if not operator and str(cond.get("type", "")).strip().lower() == "threshold":
                operator = "<="

            if dim and operator and value is not None:
                guard_conditions.append((dim, operator, _as_float(value)))
        if guard_conditions:
            transition.set_guard_function(_make_guard(spn_model, guard_conditions))

        # Dimension changes / impacted dimensions.
        dc_parent = element.find(".//mdpnml:impactedDimensions", ns)
        if dc_parent is not None:
            for dc in dc_parent.findall("mdpnml:impactedDimension", ns):
                dname = dc.get("name")
                source = dc.get("source")
                dim_key = source or dname
                direction = (dc.get("direction") or "increase").strip().lower()

                ctype_el = dc.find("mdpnml:impactType", ns)
                val_el = dc.find("mdpnml:impactValue", ns)
                if not dim_key or ctype_el is None:
                    continue

                ctype = (ctype_el.text or "").strip()
                ctype_norm = ctype.lower()
                value = _as_float(val_el.text if val_el is not None else 0.0, 0.0)

                # Battery charging is handled by distribution("charging", battery_dim=...).
                # Keep it visible in the dimension table, but do not add a normal dimension change.
                if ctype_norm == "charge":
                    transition.dimension_table.setdefault(dim_key, 0.0)
                    continue

                if direction == "decrease":
                    value = -abs(value)
                elif direction == "increase":
                    value = abs(value)

                if ctype_norm == "rate":
                    transition.add_dimension_change(dim_key, "rate", value)
                elif ctype_norm == "fixed":
                    transition.add_dimension_change(dim_key, "fixed", value)
                elif ctype_norm == "dynamicrate":
                    transition.add_dimension_change(dim_key, "dynamicRate", value)
                else:
                    # Unknown impact type: keep table key visible, but avoid breaking simulation.
                    transition.dimension_table.setdefault(dim_key, 0.0)

        transitions_dict[transition_id] = transition
        spn_model.add_transition(transition)

    # ---- ARCS ---------------------------------------------------------------
    print("Parsing arcs.")
    for element in root.findall(".//mdpnml:arc", ns):
        source_id = element.get('source')
        target_id = element.get('target')
        arc_type = element.get('type')
        mult_el = element.find(".//mdpnml:inscription/mdpnml:text", ns)
        multiplicity = int(float(mult_el.text)) if mult_el is not None and mult_el.text is not None else 1

        source = places_dict.get(source_id) or transitions_dict.get(source_id)
        target = places_dict.get(target_id) or transitions_dict.get(target_id)

        if source and target:
            if arc_type == "input":
                spn_model.add_input_arc(source, target, multiplicity)
            elif arc_type == "output":
                spn_model.add_output_arc(source, target, multiplicity)
            elif arc_type == "inhibitor":
                spn_model.add_inhibitor_arc(target, source, multiplicity)

    print("\nSPN model created from PNML.")
    print(f"Dimensions: {spn_model.dimensions}")
    if getattr(spn_model, "subdimensions", {}):
        print(f"Subdimensions: {spn_model.subdimensions}")

    return spn_model


def parse_distribution(element, ns):
    dist_elem = element.find(".//mdpnml:distribution", ns)
    if dist_elem is None:
        return None, {}

    dist_type_el = dist_elem.find("mdpnml:type", ns)
    params_el = dist_elem.find("mdpnml:parameters", ns)
    if dist_type_el is None or dist_type_el.text is None:
        return None, {}

    raw_type = dist_type_el.text.strip()
    dist_type = "charging" if raw_type.lower() in {"charge", "charging"} else raw_type

    params = {"a": 0.0, "b": 0.0, "c": 0.0, "d": 0.0}
    if params_el is not None:
        for child in list(params_el):
            tag = child.tag.split("}")[-1]
            text = child.text.strip() if child.text is not None else ""
            if tag in ("a", "b", "c", "d", "r", "max_charging", "min_charging"):
                params[tag] = _as_float(text, 0.0)
            elif tag.lower() in {"battery_dim", "batterydim", "battery_dimension", "batterydimension"}:
                params["battery_dim"] = text
            else:
                # Keep future numeric parameters if possible.
                params[tag] = _as_float(text, text)

    # For old charge notation: a=max, b=min, c/r=rate.
    if dist_type == "charging":
        params.setdefault("max_charging", params.get("a", 100.0))
        params.setdefault("min_charging", params.get("b", 0.0))
        params.setdefault("r", params.get("c", 0.0))
        if not params.get("max_charging"):
            params["max_charging"] = params.get("a", 100.0)
        if not params.get("r"):
            params["r"] = params.get("c", 0.0)

    return dist_type, params

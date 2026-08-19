from .spn import *
from graphviz import Digraph
import math


def format_label(value):
    value_str = f"{value:.2f}"
    if len(value_str) > 9:
        return value_str[:6] + "..."
    return value_str


def _count_in_service(t: Transition) -> int:
    """Count tokens reserved inside a parallel-timed transition (pt_instances)."""
    if not getattr(t, "parallel_timing", False):
        return 0
    if not hasattr(t, "pt_instances") or t.pt_instances is None:
        return 0
    return sum(len(inst.get("tokens", [])) for inst in t.pt_instances)


def draw_spn(spn, file="spn_default", show=True, print_place_labels=False, rankdir="TB"):
    spn_graph = Digraph(engine="dot", graph_attr={'rankdir': rankdir})

    # Fetch simulation time directly from the SPN object
    simulation_time = getattr(spn, "simulation_time", 0.0)
    dimension_totals = spn.get_transition_dimension_totals()

    dimension_summary = "Simulation Clock:\n\nMain dimensions:\n"

    for dim in spn.dimensions:
        if is_time_dimension(dim):
            dimension_summary += f"{dim}: {simulation_time:.2f}\n"
        elif dim in getattr(spn, "subdimensions", {}):
            dimension_summary += f"{dim}: [parent dimension]\n"
        else:
            dimension_summary += f"{dim}: {spn.get_dimension_value(dim):.2f}\n"

    if getattr(spn, "subdimensions", {}):
        dimension_summary += "\nSubdimensions:\n"
        for parent, children in spn.subdimensions.items():
            for child in children:
                dimension_summary += f"{child}: {spn.get_dimension_value(child):.2f}\n"

    # Add a text box at the top left of the diagram for the summary
    spn_graph.attr('node', shape='plaintext', style='filled', fillcolor='lightgrey')
    spn_graph.node('summary', label=dimension_summary)
    spn_graph.attr('node', shape='ellipse', style='', fillcolor='')

    # --- NEW: compute reserved (in-service) tokens per input place for parallel-timed transitions ---
    reserved_for_place = {p: 0 for p in spn.places}
    for t in spn.transitions:
        k = _count_in_service(t)
        if k > 0 and hasattr(t, "input_arcs") and t.input_arcs:
            # Your parallel_timing implementation uses exactly 1 input arc (no Join).
            p_in = t.input_arcs[0].from_place
            reserved_for_place[p_in] = reserved_for_place.get(p_in, 0) + k

    # Draw places and marking
    for place in spn.places:
        waiting = len(place.tokens)
        in_service = reserved_for_place.get(place, 0)
        token_count = waiting + in_service

        if getattr(place, "is_tracking", False):
            # Keep tracked places as value circles,
            # but show token info in xlabel if there are reserved tokens.
            formatted_value = f"{place.value:.2f}"
            dimension_label = place.dimension_tracked
            if in_service > 0 or waiting > 0:
                xlabel = f"{dimension_label}\n(toks:{waiting}+{in_service})"
            else:
                xlabel = f"{dimension_label}"
            spn_graph.node(place.label, label=formatted_value, shape="circle",
                           style='', fontsize='8', width='0.6', fixedsize='true', xlabel=xlabel)
            continue

        # Non-tracked places: show tokens
        if token_count == 0:
            label = "" if not print_place_labels else place.label
            spn_graph.node(place.label, shape="circle", label=label,
                           xlabel=place.label if print_place_labels else "",
                           height="0.6", width="0.6", fixedsize='true')
        else:
            # If parallel timing reserved tokens exist, show waiting+in_service
            if in_service > 0:
                lb = f"{waiting + in_service}"
            else:
                if token_count < 5:
                    lb = "<"
                    for token_number in range(1, token_count + 1):
                        lb += "&#9679;"
                        if token_number % 2 == 0:
                            lb += "<br/>"
                    lb += ">"
                else:
                    lb = f"{token_count}"

            label = lb if not print_place_labels else ""
            spn_graph.node(place.label, shape='circle', label=label,
                           xlabel=place.label if print_place_labels else "",
                           height='0.6', width='0.6', fixedsize='true')

    # Draw transitions with external labels and tables beside them
    for transition in spn.transitions:
        # NEW: show PT:<k> for parallel timing
        pt_k = _count_in_service(transition)
        xlabel_text = transition.label

        if transition.dimension_changes:
            total_dimensions = spn.dimensions

            if hasattr(transition, "get_connected_dimensions"):
                connected_dimensions = transition.get_connected_dimensions()
            else:
                connected_dimensions = [dim for dim, _, _ in transition.dimension_changes]

            connected_main_dimensions = set()

            for dim in connected_dimensions:
                parent = spn.get_parent_dimension(dim)
                if parent is not None:
                    connected_main_dimensions.add(parent)
                else:
                    connected_main_dimensions.add(dim)

            colors = []

            for dim in total_dimensions:
                if is_time_dimension(dim):
                    colors.append("white" if transition.t_type == "T" else "black")
                else:
                    colors.append("white" if dim in connected_main_dimensions else "black")

            color_string = ":".join(colors)

            spn_graph.node(
                transition.label,
                shape="rect",
                style="striped",
                fillcolor=color_string,
                label="",
                xlabel=xlabel_text,
                height='0.2',
                width='0.6',
                fixedsize='true'
            )
        else:
            total_dimensions = spn.dimensions
            colors = [
                "white" if is_time_dimension(dim) and transition.t_type == "T" else "black"
                for dim in total_dimensions
            ]
            color_string = ":".join(colors)

            spn_graph.node(
                transition.label,
                shape="rect",
                style="striped",
                fillcolor=color_string,
                label="",
                xlabel=xlabel_text,
                height='0.2',
                width='0.6',
                fixedsize='true'
            )

        # Dimension table node
        # Build rows first. Graphviz cannot render an empty HTML table such as
        # <<table border='1' cellborder='1' cellspacing='0'></table>>.
        table_rows = []
        if transition.dimension_table:
            for dimension, value in transition.dimension_table.items():
                if dimension is None:
                    continue
                try:
                    value_text = f"{float(value):.2f}"
                except (TypeError, ValueError):
                    value_text = str(value)

                table_rows.append(
                    f"<tr><td>{dimension}</td><td>{value_text}</td></tr>"
                )

        if table_rows:
            table_label = (
                    "<<table border='1' cellborder='1' cellspacing='0'>"
                    + "".join(table_rows)
                    + "</table>>"
            )

            table_node_label = f"{transition.label}_table"
            spacer_node_label = f"{transition.label}_spacer"

            spn_graph.node(spacer_node_label, label="", width="0", height="0", style="invis")
            spn_graph.node(table_node_label, shape="plaintext", label=table_label)

            spn_graph.edge(spacer_node_label, transition.label, style="invis")
            spn_graph.edge(spacer_node_label, table_node_label, style="invis")

        # Arcs (unchanged)
        for input_arc in transition.input_arcs:
            label = str(input_arc.multiplicity) if input_arc.multiplicity > 1 else ""
            spn_graph.edge(input_arc.from_place.label, transition.label, label=label)

        for output_arc in transition.output_arcs:
            spn_graph.edge(transition.label, output_arc.to_place.label,
                           label=str(output_arc.multiplicity) if output_arc.multiplicity > 1 else "")

        for inhibitor_arc in transition.inhibitor_arcs:
            spn_graph.edge(inhibitor_arc.from_place.label, transition.label,
                           arrowhead="dot",
                           label=str(inhibitor_arc.multiplicity) if inhibitor_arc.multiplicity > 1 else "")

    spn_graph.render(f'../output/graphs/{file}', view=show)
    return spn_graph

from __future__ import annotations
import uuid
import importlib

def is_time_dimension(dim) -> bool:
    return isinstance(dim, str) and dim.strip().lower() == "time"

class SPN(object):
    def __init__(self, dimensions=None, subdimensions=None, initial_dimension_values=None):
        if dimensions is None:
            try:
                main_module = importlib.import_module("__main__")
                dimensions = getattr(main_module, "Total_Dimensions", None)
                if subdimensions is None:
                    subdimensions = getattr(main_module, "Subdimensions", {})
            except Exception:
                dimensions = None
                subdimensions = {}

        self.dimensions = dimensions or []
        self.subdimensions = subdimensions or {}
        self.simulation_time = 0
        self.places = []
        self.transitions = []

        # executable dimensions = main dimensions without children + all children
        self.executable_dimensions = []
        for dim in self.dimensions:
            if dim in self.subdimensions:
                self.executable_dimensions.extend(self.subdimensions[dim])
            else:
                self.executable_dimensions.append(dim)
        self.initial_dimension_values = initial_dimension_values or {}

        # Time must always start at 0
        for dim in self.executable_dimensions:
            if is_time_dimension(dim):
                self.initial_dimension_values[dim] = 0.0
            elif dim not in self.initial_dimension_values:
                self.initial_dimension_values[dim] = 0.0

    def add_place(self, place):
        self.places.append(place)

    def add_transition(self, transition):
        self.transitions.append(transition)

    def add_input_arc(self, place, transition, multiplicity=1):
        arc = InputArc()
        arc.from_place = place
        arc.to_transition = transition
        arc.multiplicity = multiplicity
        transition.input_arcs.append(arc)
        place.input_arcs.append(arc)
        # Auto-set Join: more than one distinct input place -> Join
        transition.Join = len(transition.input_arcs) > 1

    def add_output_arc(self, transition, place, multiplicity=1):
        arc = OutputArc()
        arc.from_transition = transition
        arc.to_place = place
        arc.multiplicity = multiplicity
        transition.output_arcs.append(arc)
        place.output_arcs.append(arc)
        # Auto-set Fork: more than one distinct output place -> Fork
        transition.Fork = len(transition.output_arcs) > 1

    def add_inhibitor_arc(self, transition, place, multiplicity=1):
        arc = InhibitorArc()
        arc.to_transition = transition
        arc.from_place = place
        arc.multiplicity = multiplicity
        transition.inhibitor_arcs.append(arc)
        place.inhibitor_arcs.append(arc)

    def get_place_by_label(self, label):
        for place in self.places:
            if place.label == label:
                return place
        print("No place found with specified label.")
        return None

    def get_transition_by_label(self, label):
        for transition in self.transitions:
            if transition.label == label:
                return transition
        print("No transition found with specified label.")
        return None

    def get_arrival_transitions(self):
        arrival_transitions = []
        for transition in self.transitions:
            if not transition.input_arcs:
                arrival_transitions.append(transition)
        return arrival_transitions

    def is_parent_dimension(self, dim):
        return dim in self.subdimensions

    def get_parent_dimension(self, child_dim):
        for parent, children in self.subdimensions.items():
            if child_dim in children:
                return parent
        return None

    def get_transition_dimension_totals(self):
        totals = {}
        for transition in self.transitions:
            if hasattr(transition, "dimension_table") and transition.dimension_table:
                for dimension, value in transition.dimension_table.items():
                    if dimension is not None:
                        totals[dimension] = totals.get(dimension, 0.0) + float(value)
        return totals

    def get_dimension_value(self, dim):
        # Parent dimensions do not carry numeric values
        if dim in self.subdimensions:
            return None

        total = float(self.initial_dimension_values.get(dim, 0.0))
        for transition in self.transitions:
            if hasattr(transition, "dimension_table") and transition.dimension_table:
                total += float(transition.dimension_table.get(dim, 0.0))
        return total

    def summarize_dimensions(self):
        dimension_totals = {}
        for place in self.places:
            if place.is_tracking:
                dim = place.dimension_tracked
                if dim in dimension_totals:
                    dimension_totals[dim] += place.get_value()
                else:
                    dimension_totals[dim] = place.get_value()
        return dimension_totals

    def print_dimension_summary(self):
        totals = self.get_transition_dimension_totals()

        print("\nMain dimensions:")
        for dim in self.dimensions:
            if is_time_dimension(dim):
                print(f"{dim}: {self.simulation_time:.2f}")
            elif dim in self.subdimensions:
                print(f"{dim}: [parent dimension]")
            else:
                print(f"{dim}: {self.get_dimension_value(dim):.2f}")

        if self.subdimensions:
            print("\nSubdimensions:")
            for parent, children in self.subdimensions.items():
                for child in children:
                    print(f"{child}: {self.get_dimension_value(child):.2f}")
        

class Place:
    def __init__(self, label: str, n_tokens: int = 0, is_tracking=False, dimension_tracked=None, initial_value=None, DoT=None):
        self.label = label
        self.n_tokens = n_tokens
        self.is_tracking = is_tracking
        self.dimension_tracked = dimension_tracked
        self.value = initial_value if initial_value is not None else 0.0  # Ensure value is initialized
        self.DoT = DoT
        self.time_entered = 0.0  # Initialize time_entered for tracking DoT
        self.tokens = [Token() for _ in range(n_tokens)]  # Tokens present in the place

        self.tokens = []

        if not is_tracking:
            for _ in range(n_tokens):
                self.tokens.append(Token())

        self.max_tokens = 0
        self.time_changed = 0
        self.total_tokens = 0
        self.time_non_empty = 0

        self.input_arcs = []
        self.output_arcs = []
        self.inhibitor_arcs = []

    def set_tokens(self, n_tokens: int):
        current_tokens = len(self.tokens)
        if n_tokens > current_tokens:
            self.tokens.extend([Token() for _ in range(n_tokens - current_tokens)])
        elif n_tokens < current_tokens:
            self.tokens = self.tokens[:n_tokens]

    def __str__(self):
        if self.is_tracking:
            return f"Place {self.label}: {self.dimension_tracked} = {self.value}"
        else:
            return f"Place {self.label}: Tokens = {len(self.tokens)}"

    def set_value(self, value):
        if self.is_tracking:
            self.value = value
        else:
            raise ValueError("This place is not a dimension holder.")

    def get_value(self):
        if self.is_tracking:
            return self.value
        else:
            raise ValueError("This place is not a dimension holder.")

    def refresh_join_fork(self):
        """Recompute Join/Fork flags for all transitions based on arc counts."""
        for t in self.transitions:
            t.Join = len(t.input_arcs) > 1
            t.Fork = len(t.output_arcs) > 1

class Transition(object):

    def __init__(self, label: str, t_type: str, Join=0, Fork=0, dimension_changes=None, capacity=1, input_transition=False, output_transition=False, **kwargs):
        self.label = label
        self.t_type = t_type
        self.capacity = capacity
        self.dimension_changes = dimension_changes or []
        self.input_transition = input_transition
        self.output_transition = output_transition
        self.dimension_table = {}  # New table to store dimension values        # --- Parallel timing (one timer per token/instance) ---
        # Accept parallel_timing as keyword arg to avoid breaking existing constructors.
        self.parallel_timing = bool(kwargs.pop("parallel_timing", False))
        # asset_level replaces the old unify_tokens meaning.
        # Backward-compatible fallback accepts unify_tokens if an old model still provides it.
        self.asset_level = bool(kwargs.pop("asset_level", kwargs.pop("unify_tokens", False)))
        self.pt_instances = []   # list of dicts: {"fire_time": ..., "delay": ..., "tokens": [...]}
        self.dimension_table = {}

        if self.t_type == "T":
            self.distribution = None
            self.time_unit = None
        elif self.t_type == "I":
            self.weight = 1
        else:
            raise Exception("Not a valid transition type.")

        self.handicap = 1
        self.handicap_type = None
        self.allow_reset = False
        self.reset_threshold = 0
        self.reset_time = 0

        self.guard_function = None
        self.memory_policy = "ENABLE"
        self.clock_active = False

        self.enabled = False
        self.enabled_at = 0
        self.disabled_at = 0
        self.disabled_time = 0
        self.firing_delay = 0
        self.firing_time = 0

        self.time_enabled = 0
        self.n_times_fired = 0

        self.input_arcs = []
        self.output_arcs = []
        self.inhibitor_arcs = []

        self.counter = 0
        self.Join = Join
        self.Fork = Fork

    def set_distribution(self, distribution, a=0.0, b=0.0, c=0.0, d=0.0, time_unit: str = None, **kwargs):
        if self.t_type != "T":
            raise Exception("Cannot set distribution for immediate transition.")

        params = {"a": a, "b": b, "c": c, "d": d}
        params.update(kwargs)
        self.distribution = {distribution: params}
        self.time_unit = time_unit

        # Charging is a special timed distribution:
        # it contributes to the battery subdimension named by battery_dim.
        # We register the dimension here so visualization and export know this
        # transition is connected to Battery, without adding a duplicate rate.
        if str(distribution).lower() == "charging":
            battery_dim = params.get("battery_dim")
            if battery_dim is None:
                raise ValueError(f"{self.label}: charging distribution requires battery_dim.")

            if battery_dim not in self.dimension_table:
                self.dimension_table[battery_dim] = 0.0

    def set_weight(self, weight: float):
        if self.t_type == "I":
            self.weight = weight
        else:
            raise Exception("Cannot set weight for timed transition.")

    def set_guard_function(self, guard_function):
        self.guard_function = guard_function

    def set_memory_policy(self, type):
        self.memory_policy = type

    def add_dimension_change(self, dimension, change_type, value=None, column=None, offset=0):
        # If change_type is dynamicRate, pack CSV spec as a tuple
        if change_type == "dynamicRate" and column is not None:
            value = (value, column, int(offset))

        self.dimension_changes.append((dimension, change_type, value))

        # Make sure we have a running accumulator for this dimension
        if dimension not in self.dimension_table:
            self.dimension_table[dimension] = 0.0

    def get_charging_battery_dim(self):
        if self.t_type != "T" or self.distribution is None:
            return None

        dist = list(self.distribution.keys())[0]
        if str(dist).lower() != "charging":
            return None

        return self.distribution[dist].get("battery_dim")

    def get_connected_dimensions(self):
        """
        Returns all dimensions this transition is connected to.

        Normal dimensions come from add_dimension_change(...).
        Charging battery dimension comes from set_distribution("charging", battery_dim=...).
        """
        dims = []

        for dim, _, _ in self.dimension_changes:
            if dim not in dims:
                dims.append(dim)

        charging_battery_dim = self.get_charging_battery_dim()
        if charging_battery_dim and charging_battery_dim not in dims:
            dims.append(charging_battery_dim)

        return dims

    def set_parallel_timing(self, enabled: bool = True):
        self.parallel_timing = bool(enabled)
        if not hasattr(self, "pt_instances") or self.pt_instances is None:
            self.pt_instances = []

    def set_asset_level(self, enabled: bool = True):
        self.asset_level = bool(enabled)



class InputArc(object):
    def __init__(self):
        self.to_transition = None
        self.from_place = None
        self.multiplicity = 0

class InhibitorArc(object):
    def __init__(self):
        self.to_transition = None
        self.from_place = None
        self.multiplicity = 0

class OutputArc(object):
    def __init__(self):
        self.to_place = None
        self.from_transition = None
        self.multiplicity = 0


# Hypothetical Token class implementation
class Token:
    _id_counter = -1

    def __init__(self):
        type(self)._id_counter += 1
        self.id = type(self)._id_counter

    def __str__(self):
        return str(self.id)

    def __repr__(self):
        return f"Token({self.id})"

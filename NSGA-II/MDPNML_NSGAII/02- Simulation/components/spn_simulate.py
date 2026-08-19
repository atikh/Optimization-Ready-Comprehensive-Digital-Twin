import random
import os
import math

from .spn import *
from .spn_io import *
from .RNGFactory import *

SIMULATION_TIME = 0
SIMULATION_TIME_UNIT = None
VERBOSITY = 0
PROTOCOL = False
PROTOCOL = False
SCHEDULE_ITERATOR = 0

# Global list to track places with DoT
tracking_places = []


def marking(place: Place) -> int:
    return len(place.tokens)


def mean_tokens(place: Place) -> float:
    return place.total_tokens / SIMULATION_TIME


def p_not_empty(place: Place) -> float:
    return place.time_non_empty / SIMULATION_TIME


def p_enabled(transition: Transition) -> float:
    return transition.time_enabled / SIMULATION_TIME


def n_firings(transtion: Transition) -> int:
    return transtion.n_times_fired


def throughput(transition: Transition) -> float:
    return transition.n_times_fired / SIMULATION_TIME


def add_tokens(place: Place, n_tokens: int):
    # Assuming `tokens` is a list of token IDs in the Place class

    if PROTOCOL == True:
        # Write the protocol with the ID of the last added token, if any, or 'None'
        last_token_id = place.tokens[-1] if place.tokens else 'None'
        write_to_protocol(place.label, SIMULATION_TIME, len(place.tokens))

    # Update statistics calculations using the current_number_of_tokens instead of place.n_tokens
    place.total_tokens += len(place.tokens) * (SIMULATION_TIME - place.time_changed)
    if len(place.tokens) > 0:
        place.time_non_empty += SIMULATION_TIME - place.time_changed

    place.time_changed = SIMULATION_TIME
    place.n_tokens = len(place.tokens)
    place.n_tokens += n_tokens

    # Handle the addition of new tokens
    for _ in range(n_tokens):
        place.tokens.append(Token())
    place.n_tokens = len(place.tokens)

    if len(place.tokens) > place.max_tokens:
        place.max_tokens = len(place.tokens)

    # Correctly calling write_to_protocol at the end of the function
    if PROTOCOL:
        write_to_protocol(place.label, SIMULATION_TIME, place.n_tokens)


def sub_tokens(place: Place, n_tokens: int):
    if PROTOCOL:
        write_to_protocol(place.label, SIMULATION_TIME, len(place.tokens))

    # stats with current marking
    place.total_tokens += len(place.tokens) * (SIMULATION_TIME - place.time_changed)
    if len(place.tokens) > 0:
        place.time_non_empty += SIMULATION_TIME - place.time_changed
    place.time_changed = SIMULATION_TIME

    # actually remove tokens
    k = min(n_tokens, len(place.tokens))
    for _ in range(k):
        place.tokens.pop(0)   # same policy as your transition logic

    if n_tokens > k:
        print(f"Negative number of tokens in Place {place}")

    place.n_tokens = len(place.tokens)

    if PROTOCOL:
        write_to_protocol(place.label, SIMULATION_TIME, place.n_tokens)



def get_initial_marking(spn: SPN):
    marking = {}
    for place in spn.places:
        place: Place
        # Instead of n_tokens, we store a copy of the current token IDs for each place
        marking[place] = list(place.tokens)  # Assuming `tokens` is a list of token IDs
    return marking


def set_initial_marking(spn: SPN, marking):
    for place in spn.places:
        place.tokens = list(marking[place])
        place.n_tokens = len(place.tokens)


def reset_state(spn: SPN, marking):
    """Reset all places/transitions to a clean state, then restore the initial marking.

    `marking` is expected to be a dict mapping Place -> list_of_tokens
    as returned by get_initial_marking().
    """

    # --- Reset places (CLEAR TOKENS + stats) ---
    for place in spn.places:
        place: Place
        place.tokens = []              # IMPORTANT: clear actual token list
        place.n_tokens = 0             # keep counter consistent
        place.max_tokens = 0 if hasattr(place, "max_tokens") else getattr(place, "max_tokens", 0)

        # Reset DoT FULL-idle tracking fields (used only by the end-of-simulation
        # idle-rate accounting for immediate transitions).
        for attr in ("dot_full_marking", "dot_full_active", "dot_full_start"):
            if hasattr(place, attr):
                try:
                    delattr(place, attr)
                except Exception:
                    setattr(place, attr, None)

        place.time_changed = 0.0
        place.total_tokens = 0.0
        place.time_non_empty = 0.0

    # --- Reset transitions (counters + clocks + parallel instances) ---
    for transition in spn.transitions:
        transition: Transition
        transition.time_enabled = 0.0
        transition.n_times_fired = 0

        transition.enabled_at = 0.0
        transition.disabled_at = 0.0
        transition.disabled_time = 0.0

        transition.firing_delay = 0.0
        transition.firing_time = 0.0

        transition.clock_active = False
        transition.enabled = False

        # add this
        if hasattr(transition, "dimension_table"):
            for dim in list(transition.dimension_table.keys()):
                transition.dimension_table[dim] = 0.0

        if hasattr(transition, "pt_instances"):
            transition.pt_instances = []
            transition.pt_busy_until = 0.0

        # Reset any join/fork counters used by existing logic
        if hasattr(transition, "counter"):
            transition.counter = 0

        # Reset reset-policy fields if they exist in your model
        if hasattr(transition, "reset_time"):
            transition.reset_time = 0.0

    # --- Restore initial marking (tokens list per place) ---
    for place in spn.places:
        place: Place
        place.tokens = list(marking.get(place, []))
        place.n_tokens = len(place.tokens)
        if hasattr(place, "max_tokens"):
            place.max_tokens = max(place.max_tokens, place.n_tokens)


def complete_statistics(spn: SPN):
    for place in spn.places:
        add_tokens(place, 0)
    for transition in spn.transitions:
        transition: Transition
        if transition.enabled == True:
            transition.time_enabled += SIMULATION_TIME - transition.enabled_at


def set_firing_time(transition: Transition, spn: SPN = None):
    """Sets the firing time of a transition based on the transition type and distribution"""
    global SCHEDULE_ITERATOR

    transition.enabled_at = SIMULATION_TIME

    if transition.t_type == "I":
        transition.firing_delay = 0.0
    elif transition.t_type == "T":
        dist = list(transition.distribution.keys())[0]
        parameters = list(transition.distribution[dist].values())
        match dist:
            case "det":
                transition.firing_delay = get_delay("det", parameters[0])
            case "uniform":
                transition.firing_delay = get_delay("uniform", parameters[0], parameters[1])
            case "expon":
                transition.firing_delay = get_delay("expon", parameters[0], parameters[1])
            case "norm":
                transition.firing_delay = get_delay("norm", parameters[0], parameters[1])
            case "lognorm":
                transition.firing_delay = get_delay("lognorm", parameters[0], parameters[1], parameters[2])
            case "triang":
                transition.firing_delay = get_delay("triang", parameters[0], parameters[1], parameters[2])
            case "cauchy":
                transition.firing_delay = get_delay("cauchy", parameters[0], parameters[1])
            case "exponpow":
                transition.firing_delay = get_delay("exponpow", parameters[0], parameters[1], parameters[2])
            case "gamma":
                transition.firing_delay = get_delay("gamma", parameters[0], parameters[1], parameters[2])
            case "weibull_min":
                transition.firing_delay = get_delay("weibull_min", parameters[0], parameters[1], parameters[2])
            case "charging":
                if spn is None:
                    raise ValueError("Charging distribution requires spn.")

                charging_rate = transition.distribution[dist].get("r", None)
                max_charging = transition.distribution[dist].get("max_charging", 100.0)
                battery_dim = transition.distribution[dist].get("battery_dim", None)

                if battery_dim is None:
                    raise ValueError(f"{transition.label}: charging distribution requires battery_dim.")

                current_level = spn.get_dimension_value(battery_dim)

                transition.firing_delay = get_charging_delay(
                    current_level=current_level,
                    charging_rate=charging_rate,
                    max_charging=max_charging
                )
            case _:
                raise Exception("Distribution undefined for transition {}".format(transition))

    if transition.handicap != 1:
        if transition.handicap_type == "increase":
            transition.firing_delay = round(transition.handicap, 2) * transition.firing_delay
        elif transition.handicap_type == "decrease":
            transition.firing_delay = transition.firing_delay / round(transition.handicap, 2)

    if transition.t_type == "T" and SIMULATION_TIME_UNIT != None:
        transition.firing_delay = convert_delay(transition.firing_delay, time_unit=transition.time_unit,
                                                simulation_time_unit=SIMULATION_TIME_UNIT)

    transition.firing_time = transition.enabled_at + transition.firing_delay

def sample_firing_delay(transition: Transition) -> float:
    """Sample a delay without overwriting the transition's single-clock fields."""
    if transition.t_type != "T":
        return 0.0

    dist = list(transition.distribution.keys())[0]
    parameters = list(transition.distribution[dist].values())

    match dist:
        case "det":
            delay = get_delay("det", parameters[0])
        case "uniform":
            delay = get_delay("uniform", parameters[0], parameters[1])
        case "expon":
            delay = get_delay("expon", parameters[0], parameters[1])
        case "norm":
            delay = get_delay("norm", parameters[0], parameters[1])
        case "lognorm":
            delay = get_delay("lognorm", parameters[0], parameters[1], parameters[2])
        case "triang":
            delay = get_delay("triang", parameters[0], parameters[1], parameters[2])
        case "cauchy":
            delay = get_delay("cauchy", parameters[0], parameters[1])
        case "exponpow":
            delay = get_delay("exponpow", parameters[0], parameters[1], parameters[2])
        case "gamma":
            delay = get_delay("gamma", parameters[0], parameters[1], parameters[2])
        case "weibull_min":
            delay = get_delay("weibull_min", parameters[0], parameters[1], parameters[2])
        case _:
            raise Exception("Distribution undefined for transition {}".format(transition))

    if transition.handicap != 1:
        if transition.handicap_type == "increase":
            delay = round(transition.handicap, 2) * delay
        elif transition.handicap_type == "decrease":
            delay = delay / round(transition.handicap, 2)

    if transition.t_type == "T" and SIMULATION_TIME_UNIT is not None:
        delay = convert_delay(delay, time_unit=transition.time_unit, simulation_time_unit=SIMULATION_TIME_UNIT)

    return delay

def set_reset_time(transition: Transition):
    transition.reset_time = transition.enabled_at + transition.reset_threshold


def convert_delay(delay, time_unit=None, simulation_time_unit=None):
    if time_unit == "d" and simulation_time_unit == "h":
        return delay * 24
    else:
        return delay


def is_enabled(transition: Transition):
    """Checks whether a transition is currently enabled"""
    input_arcs = transition.input_arcs
    inhibitor_arcs = transition.inhibitor_arcs

    # Check each input arc to see if the from_place has any tokens
    for arc in input_arcs:
        if len(arc.from_place.tokens) >= arc.multiplicity:  # Ensure enough tokens are available
            continue
        else:
            return False

    # Assuming the logic for inhibitor arcs remains the same, unless they also use the tokens list
    for arc in inhibitor_arcs:
        if len(arc.from_place.tokens) >= arc.multiplicity:  # Adjusted for token list handling
            return False

    # If the transition has a guard function, its logic might also need adjustment
    if transition.guard_function is not None:
        return transition.guard_function()

    return True

def _is_asset_level(transition: Transition) -> bool:
    """
    Asset-level means:
      - the transition represents one physical asset
      - arc multiplicities may consume/produce several capacity tokens
      - dimension impact is counted once
      - only one logical firing happens per fire_transition call
    """
    return bool(getattr(transition, "asset_level", False))


def _has_batch_multiplicity(transition: Transition) -> bool:
    """
    True when one transition firing moves multiple product tokens
    using arc multiplicity. This is batch behavior, not parallel timing.
    """
    if getattr(transition, "parallel_timing", False):
        return False

    if _is_asset_level(transition):
        return False

    arcs = list(getattr(transition, "input_arcs", [])) + list(getattr(transition, "output_arcs", []))

    return any(
        int(getattr(arc, "multiplicity", 1) or 1) > 1
        for arc in arcs
    )


def _impact_units(transition: Transition, default_units: float = 1.0) -> float:
    """
    Asset-level transitions and batch-multiplicity transitions count energy once.
    Normal transitions scale by processed tokens.
    """
    if _is_asset_level(transition):
        return 1.0

    if _has_batch_multiplicity(transition):
        return 1.0

    return float(default_units)

def _logical_fire_capacity(transition: Transition):
    """
    Normal transitions may fire up to transition.capacity.
    Asset-level transitions fire once, even if arc multiplicity consumes/produces many tokens.
    """
    if _is_asset_level(transition):
        return 1

    return transition.capacity if transition.capacity is not None else float("inf")


def _apply_charging_dimension_update(transition: Transition, spn: SPN):
    """Apply the implicit Battery contribution of a charging transition.

    A transition with ``set_distribution("charging", ..., battery_dim=...)``
    changes the battery subdimension from its current value to ``max_charging``.
    This is a distribution-level effect, not a normal rate contribution, so it
    must be applied even when ``transition.dimension_changes`` is empty or only
    contains another dimension such as Grid/Electricity.
    """
    if transition.t_type != "T" or transition.distribution is None:
        return

    dist = list(transition.distribution.keys())[0]
    if dist != "charging":
        return

    params = transition.distribution[dist]
    battery_dim = params.get("battery_dim", None)
    max_charging = float(params.get("max_charging", 100.0))

    if battery_dim is None:
        raise ValueError(f"{transition.label}: charging distribution requires battery_dim.")

    if battery_dim not in transition.dimension_table:
        transition.dimension_table[battery_dim] = 0.0

    current_value = spn.get_dimension_value(battery_dim)
    if current_value is None:
        raise ValueError(
            f"{transition.label}: battery_dim '{battery_dim}' is not an executable dimension. "
            "Use a battery subdimension, not the parent Battery dimension."
        )

    # Keep the same semantics as RNGFactory.get_charging_delay(): charging only
    # adds the missing amount up to max_charging. If the battery is already at
    # or above max_charging, this contribution is zero.
    delta = max(0.0, max_charging - float(current_value))
    transition.dimension_table[battery_dim] += delta * _impact_units(transition, 1.0)

def start_parallel_instances(transition: Transition):
    """Start as many independent instances as possible right now.

    Minimal safe semantics:
      - timed transitions only
      - exactly 1 input arc
      - not Join/Fork
      - reserves tokens immediately (removes them from input place)
    """
    if getattr(transition, "parallel_timing", False) != True:
        return
    if transition.t_type != "T":
        return

    if not hasattr(transition, "pt_instances") or transition.pt_instances is None:
        transition.pt_instances = []

    if transition.Join == 1:
        raise Exception(
            "parallel_timing only implemented for transitions with exactly 1 input arc (no Join): {}".format(
                transition.label
            )
        )
    if len(transition.input_arcs) != 1:
        raise Exception("parallel_timing currently requires exactly 1 input arc: {}".format(transition.label))

    iarc = transition.input_arcs[0]

    while is_enabled(transition) == True:
        if len(iarc.from_place.tokens) < iarc.multiplicity:
            break

        # Reserve tokens NOW (so they cannot be taken by other transitions).
        reserved = []
        for _ in range(iarc.multiplicity):
            # DoT FULL tracking (no side effects besides timestamps)
            dot_full_on_remove(iarc.from_place)
            reserved.append(iarc.from_place.tokens.pop(0))

        delay = sample_firing_delay(transition)
        finish_time = SIMULATION_TIME + delay
        base = max(getattr(transition, "pt_busy_until", SIMULATION_TIME), SIMULATION_TIME)
        busy_time = max(0.0, finish_time - base)
        busy_end = max(base, finish_time)
        transition.pt_busy_until = busy_end

        transition.pt_instances.append({
            "fire_time": finish_time,
            "delay": delay,
            "busy_time": busy_time,
            "busy_start": base,
            "busy_end": busy_end,
            "tokens": reserved,
        })


def fire_parallel_instance(transition: Transition, spn: SPN, instance: dict):
    """Complete one scheduled instance: move reserved tokens to outputs + apply dimension impacts."""
    if not hasattr(transition, "pt_instances") or transition.pt_instances is None:
        transition.pt_instances = []

    try:
        transition.pt_instances.remove(instance)
    except:
        pass

    delay = instance.get("delay", 0.0)
    tokens = instance.get("tokens", [])

    # 1) Move tokens to outputs and write event log (same style as your existing fire_transition)
    for tok in tokens:
        # Move reserved tokens to outputs
        if transition.output_arcs:

            # Fork: first produced token uses the reserved entity token,
            # remaining produced tokens are NEW tokens
            if transition.Fork == 1:
                entity_token = tokens[0] if tokens else Token()
                used_entity = False

                for oarc in transition.output_arcs:
                    for _ in range(oarc.multiplicity):
                        if not used_entity:
                            produced = entity_token
                            used_entity = True
                        else:
                            produced = Token()

                        oarc.to_place.tokens.append(produced)
                        dot_full_on_add(oarc.to_place)
                        oarc.to_place.n_tokens = len(oarc.to_place.tokens)
                        write_to_event_log(SIMULATION_TIME, produced.id, transition.label, transition, spn)

            # Non-fork: keep your old behavior (move token to outputs)
            else:
                for tok in tokens:
                    for oarc in transition.output_arcs:
                        oarc.to_place.tokens.append(tok)
                        dot_full_on_add(oarc.to_place)
                        oarc.to_place.n_tokens = len(oarc.to_place.tokens)
                    write_to_event_log(SIMULATION_TIME, tok.id, transition.label, transition, spn)

        else:
            # No outputs: still log the event(s)
            for tok in tokens:
                write_to_event_log(SIMULATION_TIME, tok.id, transition.label, transition, spn)

    # 2) Apply dimension changes (copy of your logic, but using instance delay)
    instance_impact_units = _impact_units(transition, max(1, len(tokens)))
    if transition.dimension_changes:
        for dimension, change_type, value in transition.dimension_changes:
            if dimension not in transition.dimension_table:
                transition.dimension_table[dimension] = 0.0

            if change_type == "fixed":
                transition.dimension_table[dimension] += value * instance_impact_units

            elif change_type == "rate":
                eff = float(instance.get("busy_time", delay))
                transition.dimension_table[dimension] += value * eff * instance_impact_units
            elif change_type == "dynamicRate":
                # value must be (csv_filename, column_name[, offset])
                if not isinstance(value, (tuple, list)) or len(value) < 2:
                    raise ValueError("dynamicRate requires (csv_filename, column_name[, offset]).")

                csv_filename = value[0]
                col_name = value[1]
                offset = int(value[2]) if len(value) >= 3 else 0

                # cache per transition
                if not hasattr(transition, "_dynamic_rate_cache"):
                    transition._dynamic_rate_cache = {}

                # load CSV from ../Input data/<filename>
                import os, csv, math
                if os.path.isabs(csv_filename) or "/" in csv_filename or "\\" in csv_filename:
                    raise ValueError("dynamicRate CSV must be filename only; put it in 'Input data' folder.")

                input_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, "Input data"))
                csv_path = os.path.join(input_dir, csv_filename)

                cache_key = (csv_path, col_name)
                if cache_key not in transition._dynamic_rate_cache:
                    with open(csv_path, newline="") as f:
                        reader = csv.DictReader(f)
                        series = []
                        for row in reader:
                            cell = (row.get(col_name) or "").strip()
                            series.append(0.0 if cell == "" or cell.lower() == "nan" else float(cell))
                    transition._dynamic_rate_cache[cache_key] = series

                rates = transition._dynamic_rate_cache[cache_key]
                if rates:
                    idx = int(math.floor(SIMULATION_TIME)) + offset
                    idx = max(0, min(idx, len(rates) - 1))
                    transition.dimension_table[dimension] += float(rates[idx]) * instance_impact_units

    # Charging distributions have an implicit Battery contribution even if
    # Battery is not listed in transition.dimension_changes.
    _apply_charging_dimension_update(transition, spn)

    # 3) Update stats (same counters as a normal firing)
    transition.n_times_fired += 1
    transition.time_enabled += delay
    transition.enabled = False


def update_enabled_flag(spn: SPN):
    """Updates enabled flags.
    If a timed transition has parallel_timing=True, start per-token instances and keep simulation alive while pending.
    """
    found_enabled = False

    # 0) Start new parallel instances first (so timers exist even if transition itself isn't 'enabled' later)
    for transition in spn.transitions:
        if getattr(transition, "parallel_timing", False) == True and transition.t_type == "T":
            start_parallel_instances(transition)
            transition.enabled = is_enabled(transition)  # can start another instance now?
            if transition.enabled or (hasattr(transition, "pt_instances") and len(transition.pt_instances) > 0):
                found_enabled = True

    # 1) Original disable logic for non-parallel transitions
    for transition in spn.transitions:
        if getattr(transition, "parallel_timing", False) == True and transition.t_type == "T":
            continue

        if is_enabled(transition) == False:
            if transition.enabled == True and transition.memory_policy == "AGE":
                transition.disabled_at = SIMULATION_TIME
                transition.clock_active = True
            transition.enabled = False

    # 2) Original enable logic for non-parallel transitions
    for transition in spn.transitions:
        if getattr(transition, "parallel_timing", False) == True and transition.t_type == "T":
            continue

        if is_enabled(transition) == True:
            if transition.enabled == False:
                if transition.clock_active == True:
                    transition.disabled_time += SIMULATION_TIME - transition.disabled_at
                else:
                    set_firing_time(transition, spn)
            transition.enabled = True
            found_enabled = True

    return found_enabled

def dot_full_init(place: Place):
    """
    Initialize FULL-idle tracking for a DoT place.

    FULL means: len(place.tokens) == place.dot_full_marking (the initial marking).
    """
    if getattr(place, "DoT", 0) != 1:
        return
    # Store the initial "full" marking.
    # We intentionally reset it here so each simulation run uses the
    # current initial marking after reset_state(...).
    place.dot_full_marking = len(place.tokens)

    place.dot_full_active = (len(place.tokens) == place.dot_full_marking and place.dot_full_marking > 0)
    place.dot_full_start = SIMULATION_TIME if place.dot_full_active else None


def dot_full_on_remove(place: Place):
    """
    Call this RIGHT BEFORE removing a token from `place`.
    We only maintain timestamps/flags; no KPIs are updated here.
    """
    if getattr(place, "DoT", 0) != 1:
        return
    if not hasattr(place, "dot_full_marking"):
        place.dot_full_marking = len(place.tokens)
    if place.dot_full_marking <= 0:
        return

    # leaving FULL state now?
    if getattr(place, "dot_full_active", False) and len(place.tokens) == place.dot_full_marking:
        place.dot_full_active = False
        place.dot_full_start = None


def dot_full_on_add(place: Place):
    """
    Call this RIGHT AFTER adding a token to `place`.
    If we just reached FULL, start a new FULL interval.
    """
    if getattr(place, "DoT", 0) != 1:
        return
    if not hasattr(place, "dot_full_marking"):
        place.dot_full_marking = len(place.tokens)

    # entering FULL state now?
    if (not getattr(place, "dot_full_active", False)) and len(place.tokens) == place.dot_full_marking and place.dot_full_marking > 0:
        place.dot_full_active = True
        place.dot_full_start = SIMULATION_TIME


def maybe_capture_dot_full_leave(place: Place, captured: dict):
    """For IMMEDIATE transitions: capture the duration of the *FULL* interval
    that ends now because we're about to remove a token from a FULL DoT place.

    This fixes multi-token DoT places where the old entrance_time logic treated
    any token removal as ending the idle interval.
    """
    if getattr(place, "DoT", 0) != 1:
        return
    if place in captured:
        return
    if not hasattr(place, "dot_full_marking"):
        return
    if not getattr(place, "dot_full_active", False):
        return
    if getattr(place, "dot_full_start", None) is None:
        return
    # Only if we are currently FULL (right before removal)
    if len(place.tokens) == getattr(place, "dot_full_marking", -1):
        captured[place] = float(SIMULATION_TIME) - float(place.dot_full_start)


def fire_transition(transition: Transition, spn: SPN):
    """Fires a transition, moves tokens, and updates dimension tables.

    IMPORTANT:
      - Token consumption/production happens ONLY ONCE in this function.
      - Fork policy matches PySPN:
          * consume entity token from input
          * first produced output token uses entity token
          * all additional produced output tokens are NEW tokens
    """
    global tracking_places
    import math

    # For IMMEDIATE transitions with DoT places that hold multiple tokens, we need
    # to measure the time the DoT place was *FULL* (all initial tokens present)
    # before it leaves FULL due to this firing. We capture that duration right
    # before consuming tokens, and apply it once per DoT place.
    full_leave_durations = {}
    for iarc in transition.input_arcs:
        iarc.from_place.n_tokens = len(iarc.from_place.tokens)
    for oarc in transition.output_arcs:
        oarc.to_place.n_tokens = len(oarc.to_place.tokens)

    # Protocol pre-log
    if PROTOCOL:
        for iarc in transition.input_arcs:
            write_to_protocol(iarc.from_place.label, SIMULATION_TIME, len(iarc.from_place.tokens))
        for oarc in transition.output_arcs:
            write_to_protocol(oarc.to_place.label, SIMULATION_TIME, len(oarc.to_place.tokens))

    # For asset_level transitions, arc multiplicity may consume/produce
    # several capacity tokens, but only ONE logical firing is allowed.
    max_tokens_to_transfer = _logical_fire_capacity(transition)
    remaining_cap = max_tokens_to_transfer

    # ADDED: count how many entity-units we actually processed in THIS fire()
    # (so rate impacts can be scaled correctly)
    entities_processed = 0
    tokens_processed = 0

    # --------------------------
    # 1) Source transitions (no inputs): create tokens once
    # --------------------------
    if not transition.input_arcs:
        for oarc in transition.output_arcs:
            for _ in range(oarc.multiplicity):
                if remaining_cap <= 0:
                    break
                t = Token()
                oarc.to_place.tokens.append(t)
                dot_full_on_add(oarc.to_place)
                oarc.to_place.n_tokens = len(oarc.to_place.tokens)
                write_to_event_log(SIMULATION_TIME, t.id, transition.label, transition, spn)
                remaining_cap -= 1
                entities_processed += 1  # ADDED
                tokens_processed += 1

        # DoT output tracking (keep your existing tracking approach)
        for oarc in transition.output_arcs:
            output_place = oarc.to_place
            if output_place.DoT == 1:
                existing_entry = next((e for e in tracking_places if e["place"] == output_place), None)
                if not existing_entry:
                    tracking_places.append({
                        "place": output_place,
                        "dimension": output_place.dimension_tracked,
                        "entrance_time": SIMULATION_TIME
                    })
                else:
                    existing_entry["entrance_time"] = SIMULATION_TIME

        transition.n_times_fired += 1
        transition.time_enabled += transition.firing_delay
        transition.enabled = False

        # IMPORTANT: apply dimension_changes here too (otherwise sources never add rate impacts)
        source_impact_units = _impact_units(transition, max(1, tokens_processed))

        if transition.dimension_changes:
            for dimension, change_type, value in transition.dimension_changes:
                if dimension not in transition.dimension_table:
                    transition.dimension_table[dimension] = 0.0

                if change_type == "fixed":
                    transition.dimension_table[dimension] += value * source_impact_units
                elif change_type == "rate":
                    def fix_fraction2(x: float) -> float:
                        m = math.floor(x)
                        frac_hundred = math.floor((x - m) * 100)
                        if frac_hundred >= 60:
                            frac_hundred -= 60
                        return m + frac_hundred / 100.0

                    transition.dimension_table[dimension] += value * fix_fraction2(transition.firing_delay) * source_impact_units

                elif change_type == "dynamicRate":
                    # Expects `value` packed by Transition.add_dimension_change(...) as:
                    #   (csv_filename, column_name[, offset])
                    # Example call:
                    #   Mt1.add_dimension_change("RES", "dynamicRate", "karlsruhe_next_hours_egr.csv", "EGR_kWh")
                    # Cache per transition so we don't re-read CSV every firing
                    if not hasattr(transition, "_dynamic_rate_cache"):
                        transition._dynamic_rate_cache = {}
                    # Unpack CSV spec
                    if isinstance(value, (tuple, list)):
                        if len(value) < 2:
                            raise ValueError("dynamicRate requires (csv_filename, column_name[, offset]).")
                        csv_filename = value[0]
                        col_name = value[1]
                        offset = int(value[2]) if len(value) >= 3 else 0
                    else:
                        raise ValueError("dynamicRate requires value as (csv_filename, column_name[, offset]).")
                    # Enforce filename-only (no paths) and read only from project root 'Input data' folder
                    if (not isinstance(csv_filename, str) or os.path.isabs(csv_filename)
                            or "/" in csv_filename or "\\" in csv_filename):
                        raise ValueError(
                            "dynamicRate CSV must be a filename only (no paths). "
                            "Put the file in the 'Input data' folder."
                        )
                    input_dir = os.path.abspath(
                        os.path.join(os.path.dirname(__file__), os.pardir, "Input data")
                    )
                    csv_path = os.path.join(input_dir, csv_filename)
                    if not os.path.isfile(csv_path):
                        raise FileNotFoundError(f"CSV '{csv_filename}' not found in {input_dir}.")
                   # IMPORTANT: correct variable name is cache_key (you had cace_key)
                    cache_key = (csv_path, col_name)
                    if cache_key not in transition._dynamic_rate_cache:
                        with open(csv_path, newline="") as f:
                            reader = csv.DictReader(f)
                            series = []
                            for row in reader:
                                if col_name not in row:
                                    raise KeyError(
                                        f"Column '{col_name}' not found in '{csv_filename}'. "
                                        f"Available columns: {list(row.keys())}"
                                    )
                                cell = (row.get(col_name) or "").strip()
                                series.append(0.0 if cell == "" or cell.lower() == "nan" else float(cell))
                        transition._dynamic_rate_cache[cache_key] = series
                    rates = transition._dynamic_rate_cache[cache_key]
                    if not rates:
                        continue

                    # --- WARNING if CSV shorter than required simulation range (warn once) ---
                    # With your current mapping: idx = floor(SIMULATION_TIME) + offset
                    # the largest index you may request is ~ floor(spn.simulation_time) + offset
                    required_max_idx = int(math.floor(getattr(spn, "simulation_time", SIMULATION_TIME))) + offset
                    if required_max_idx >= len(rates):
                        if not hasattr(transition, "_dynamic_rate_warned"):
                            transition._dynamic_rate_warned = set()
                        if cache_key not in transition._dynamic_rate_warned:
                            import warnings
                            warnings.warn(
                                f"[dynamicRate] CSV '{csv_filename}' column '{col_name}' has only {len(rates)} rows, "
                                f"but simulation may request index up to {required_max_idx}. "
                                f"Values will be clamped to the last available row.",
                                RuntimeWarning
                            )
                            transition._dynamic_rate_warned.add(cache_key)
                    # --- end warning ---

                    # Map firing time to row index
                    idx = int(math.floor(SIMULATION_TIME)) + offset
                    idx = max(0, min(idx, len(rates) - 1))
                    transition.dimension_table[dimension] += rates[idx] * source_impact_units
        # Charging distributions have an implicit Battery contribution even if
        # Battery is not listed in transition.dimension_changes.
        _apply_charging_dimension_update(transition, spn)

        if PROTOCOL:
            for oarc in transition.output_arcs:
                write_to_protocol(oarc.to_place.label, SIMULATION_TIME, len(oarc.to_place.tokens))
        return

    # --------------------------
    # 2) Join: consume from each input arc, produce ONE token
    # --------------------------
    if transition.Join == 1:
        if remaining_cap <= 0:
            transition.enabled = False
            return

        collected = []  # (place, token)
        for iarc in transition.input_arcs:
            for _ in range(iarc.multiplicity):
                if not iarc.from_place.tokens:
                    raise RuntimeError(
                        f"Join transition {transition.label} fired but {iarc.from_place.label} lacks tokens."
                    )
                if transition.t_type == "I":
                    maybe_capture_dot_full_leave(iarc.from_place, full_leave_durations)
                dot_full_on_remove(iarc.from_place)
                tok = iarc.from_place.tokens.pop(0)
                collected.append((iarc.from_place, tok))
            iarc.from_place.n_tokens = len(iarc.from_place.tokens)

        # Preserve one token from a "normal" place (DoT != 1) if any; else create a new token
        preserved = None
        for place, tok in collected:
            if place.DoT != 1:
                preserved = tok
                break
        new_tok = preserved if preserved is not None else Token()

        for oarc in transition.output_arcs:
            for _ in range(oarc.multiplicity):
                oarc.to_place.tokens.append(new_tok)
                dot_full_on_add(oarc.to_place)
                oarc.to_place.n_tokens = len(oarc.to_place.tokens)

        nid = new_tok.id if hasattr(new_tok, "id") else new_tok
        write_to_event_log(SIMULATION_TIME, nid, transition.label, transition, spn)

        remaining_cap -= 1
        entities_processed += 1  # ADDED
        tokens_processed += len(collected)

    # --------------------------
    # 3) Fork: entity token goes to first produced output token, others are NEW tokens
    # --------------------------
    elif transition.Fork == 1:
        if remaining_cap <= 0:
            transition.enabled = False
            return

        if len(transition.input_arcs) != 1:
            raise RuntimeError(
                f"Fork transition {transition.label} expects exactly 1 input arc in this implementation.")

        iarc = transition.input_arcs[0]

        # consume multiplicity (usually 1)
        consumed = []
        for _ in range(iarc.multiplicity):
            if not iarc.from_place.tokens:
                raise RuntimeError(
                    f"Fork transition {transition.label} fired but {iarc.from_place.label} lacks tokens."
                )
            if transition.t_type == "I":
                maybe_capture_dot_full_leave(iarc.from_place, full_leave_durations)
            dot_full_on_remove(iarc.from_place)
            consumed.append(iarc.from_place.tokens.pop(0))
        iarc.from_place.n_tokens = len(iarc.from_place.tokens)

        entity_token = consumed[0] if consumed else Token()

        used_entity = False
        for oarc in transition.output_arcs:
            for _ in range(oarc.multiplicity):
                if not used_entity:
                    oarc.to_place.tokens.append(entity_token)
                    dot_full_on_add(oarc.to_place)
                    write_to_event_log(SIMULATION_TIME, entity_token.id, transition.label, transition, spn)
                    used_entity = True
                else:
                    t = Token()
                    oarc.to_place.tokens.append(t)
                    dot_full_on_add(oarc.to_place)
                    write_to_event_log(SIMULATION_TIME, t.id, transition.label, transition, spn)

                oarc.to_place.n_tokens = len(oarc.to_place.tokens)

        remaining_cap -= 1
        entities_processed += 1  # ADDED
        tokens_processed += len(consumed)

    # --------------------------
    # 4) Normal: move consumed token(s) to outputs (same token identity)
    # --------------------------
    else:
        for iarc in transition.input_arcs:
            # each "entity" here consumes iarc.multiplicity tokens
            while remaining_cap > 0:
                # if not enough tokens to consume multiplicity, stop
                if len(iarc.from_place.tokens) < iarc.multiplicity:
                    break

                consumed = []
                for _ in range(iarc.multiplicity):
                    if transition.t_type == "I":
                        maybe_capture_dot_full_leave(iarc.from_place, full_leave_durations)
                    dot_full_on_remove(iarc.from_place)
                    consumed.append(iarc.from_place.tokens.pop(0))

                iarc.from_place.n_tokens = len(iarc.from_place.tokens)

                tok = consumed[0]  # entity token identity

                for oarc in transition.output_arcs:
                    for __ in range(oarc.multiplicity):
                        oarc.to_place.tokens.append(tok)
                        dot_full_on_add(oarc.to_place)
                        oarc.to_place.n_tokens = len(oarc.to_place.tokens)

                tid = tok.id if hasattr(tok, "id") else tok
                write_to_event_log(SIMULATION_TIME, tid, transition.label, transition, spn)

                remaining_cap -= 1
                entities_processed += 1  # ADDED
                tokens_processed += len(consumed)

    # --------------------------
    # ---- KEEP YOUR MULTI-DIMENSION / DoT LOGIC BELOW (unchanged) ----
    # --------------------------

    # Track the entrance time and place details for DoT places
    for oarc in transition.output_arcs:
        if oarc.to_place.DoT == 1 and transition.t_type == "I":
            for iarc in transition.input_arcs:
                dimension = iarc.from_place.dimension_tracked
                duration = SIMULATION_TIME - iarc.from_place.time_entered

                if dimension in transition.dimension_table:
                    transition.dimension_table[dimension] += duration
                else:
                    transition.dimension_table[dimension] = duration

                iarc.from_place.time_entered = SIMULATION_TIME

    # Handle dimension changes
    normal_impact_units = _impact_units(transition, max(1, tokens_processed))
    if transition.dimension_changes:
        for dimension, change_type, value in transition.dimension_changes:
            if dimension not in transition.dimension_table:
                transition.dimension_table[dimension] = 0.0

            if change_type == "fixed":
                transition.dimension_table[dimension] += value * normal_impact_units

            elif change_type == "rate":
                # ADDED: scale by how many entity-units were actually processed in this fire()
                transition.dimension_table[dimension] += value * transition.firing_delay * normal_impact_units

            elif change_type == "dynamicRate":
                # value must be (csv_filename, column_name[, offset])
                if not isinstance(value, (tuple, list)) or len(value) < 2:
                    raise ValueError("dynamicRate requires (csv_filename, column_name[, offset]).")

                csv_filename = value[0]
                col_name = value[1]
                offset = int(value[2]) if len(value) >= 3 else 0

                # cache per transition
                if not hasattr(transition, "_dynamic_rate_cache"):
                    transition._dynamic_rate_cache = {}

                # load CSV from ../Input data/<filename>
                import os, csv, math
                if os.path.isabs(csv_filename) or "/" in csv_filename or "\\" in csv_filename:
                    raise ValueError("dynamicRate CSV must be filename only; put it in 'Input data' folder.")

                input_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, "Input data"))
                csv_path = os.path.join(input_dir, csv_filename)

                cache_key = (csv_path, col_name)
                if cache_key not in transition._dynamic_rate_cache:
                    with open(csv_path, newline="") as f:
                        reader = csv.DictReader(f)
                        series = []
                        for row in reader:
                            cell = (row.get(col_name) or "").strip()
                            series.append(0.0 if cell == "" or cell.lower() == "nan" else float(cell))
                    transition._dynamic_rate_cache[cache_key] = series

                rates = transition._dynamic_rate_cache[cache_key]
                if rates:
                    idx = int(math.floor(SIMULATION_TIME)) + offset
                    idx = max(0, min(idx, len(rates) - 1))
                    transition.dimension_table[dimension] += float(rates[idx]) * normal_impact_units

    # Charging distributions have an implicit Battery contribution even if
    # Battery is not listed in transition.dimension_changes.
    _apply_charging_dimension_update(transition, spn)

    # Check if input places are DoT and calculate the duration
    #
    # IMPORTANT FIX (multi-token DoT, IMMEDIATE transitions):
    # Some "ready" DoT places hold multiple tokens (e.g., STR1_ready=10, STR2_ready=6,
    # MPL03_ready=174 at the end of your run). In those cases, the correct "idle"
    # interval is the time the DoT place was *FULL* (all initial tokens present) until
    # the moment it stops being FULL (first token taken).
    #
    # The previous tracking_places-based logic effectively treated *any* token removal
    # as ending the idle interval, which over/under-counts when >1 token exists.
    #
    # So for IMMEDIATE transitions where at least one DoT input place has an initial
    # FULL marking >1, we use the FULL-leave duration captured earlier.
    dot_inputs = [arc.from_place for arc in transition.input_arcs if getattr(arc.from_place, "DoT", 0) == 1]
    use_full_idle_logic = (
        transition.t_type == "I" and any(getattr(p, "dot_full_marking", 1) > 1 for p in dot_inputs)
    )

    if use_full_idle_logic and transition.dimension_changes:
        for p, duration in full_leave_durations.items():
            tracked_dimension = getattr(p, "dimension_tracked", None)
            if tracked_dimension is None:
                continue
            for dimension, change_type, value in transition.dimension_changes:
                if dimension == tracked_dimension and change_type == "rate":
                    if dimension not in transition.dimension_table:
                        transition.dimension_table[dimension] = 0.0
                    transition.dimension_table[dimension] += float(duration) * float(value) * _impact_units(transition, 1.0)
    elif transition.t_type == "I":
        for iarc in transition.input_arcs:
            input_place = iarc.from_place
            if input_place.DoT == 1:
                tracking_entry = next((entry for entry in tracking_places if entry["place"] == input_place), None)
                if tracking_entry:
                    duration = SIMULATION_TIME - tracking_entry["entrance_time"]
                    tracked_dimension = tracking_entry["dimension"]

                    for dimension, change_type, value in transition.dimension_changes:
                        if dimension == tracked_dimension and change_type == "rate":
                            if dimension in transition.dimension_table:
                                transition.dimension_table[dimension] += duration * value * _impact_units(transition,1.0)

                    tracking_places.remove(tracking_entry)

    # Track again the entrance time and place details for DoT places
    for oarc in transition.output_arcs:
        output_place = oarc.to_place
        if output_place.DoT == 1:
            existing_entry = next((entry for entry in tracking_places if entry["place"] == output_place), None)
            if not existing_entry:
                tracking_places.append({
                    "place": output_place,
                    "dimension": output_place.dimension_tracked,
                    "entrance_time": SIMULATION_TIME
                })
            else:
                existing_entry["entrance_time"] = SIMULATION_TIME

    # Protocol post-log
    if PROTOCOL:
        for iarc in transition.input_arcs:
            write_to_protocol(iarc.from_place.label, SIMULATION_TIME, len(iarc.from_place.tokens))
        for oarc in transition.output_arcs:
            write_to_protocol(oarc.to_place.label, SIMULATION_TIME, len(oarc.to_place.tokens))

    transition.n_times_fired += 1
    transition.time_enabled += transition.firing_delay
    transition.enabled = False



def find_next_firing(spn: SPN):
    total_prob = 0.0
    inc_prob = 0.0
    min_time = 1.0e9
    next_trans = None
    next_instance = None

    # 1) Immediate transitions (unchanged)
    for transition in spn.transitions:
        if transition.enabled == True and transition.t_type == "I":
            total_prob = total_prob + transition.weight

    if total_prob > 0:
        min_time = SIMULATION_TIME
        ran = random.uniform(0, total_prob)
        for transition in spn.transitions:
            if transition.enabled == True and transition.t_type == "I":
                inc_prob = inc_prob + transition.weight
                if inc_prob > ran:
                    return transition, min_time, None

    # 2) Parallel instance events
    for transition in spn.transitions:
        if getattr(transition, "parallel_timing", False) == True and transition.t_type == "T":
            if hasattr(transition, "pt_instances") and transition.pt_instances and len(transition.pt_instances) > 0:
                inst = min(transition.pt_instances, key=lambda x: x["fire_time"])
                if inst["fire_time"] < min_time:
                    min_time = inst["fire_time"]
                    next_trans = transition
                    next_instance = inst

    # 3) Regular timed transitions (unchanged)
    for transition in spn.transitions:
        if getattr(transition, "parallel_timing", False) == True and transition.t_type == "T":
            continue

        if transition.enabled == True:
            firing_due_at = transition.enabled_at + transition.firing_delay
            if firing_due_at < min_time:
                min_time = firing_due_at
                next_trans = transition
                next_instance = None

    return next_trans, min_time, next_instance



def process_next_event(spn: SPN, max_time):
    global SIMULATION_TIME

    next_transition, min_time, next_instance = find_next_firing(spn)

    if min_time > max_time:
        SIMULATION_TIME = max_time
        return True
    else:
        SIMULATION_TIME = min_time

    if next_instance is not None and getattr(next_transition, "parallel_timing", False) == True:
        fire_parallel_instance(next_transition, spn, next_instance)
    else:
        fire_transition(next_transition, spn)

    if VERBOSITY > 1:
        print("\nTransition {} fires at time {}".format(next_transition.label, round(SIMULATION_TIME, 2)))

    if VERBOSITY > 2:
        print_marking(spn, SIMULATION_TIME)

    found_enabled = update_enabled_flag(spn)
    return found_enabled

def finalize_parallel_inprocess_rate_impacts(spn: SPN, end_time: float):
    """
    At simulation end, account for the *already consumed* part of rate-impacts
    for parallel_timing transitions whose next (front) instance did NOT fire yet.

    We only count the *front* processing token (the one whose effective-busy interval
    currently covers end_time). This avoids counting queued/behind tokens.
    """
    for transition in spn.transitions:
        if not getattr(transition, "parallel_timing", False):
            continue
        if getattr(transition, "t_type", None) != "T":
            continue
        if not getattr(transition, "dimension_changes", None):
            continue

        instances = getattr(transition, "pt_instances", None)
        if not instances:
            continue

        # Optional user-requested guard: only do this if there is at least
        # one token logically waiting/being processed for this transition.
        pending = sum(len(inst.get("tokens", [])) for inst in instances)
        in_place = 0
        if getattr(transition, "input_arcs", None):
            try:
                in_place = len(transition.input_arcs[0].from_place.tokens)
            except Exception:
                in_place = 0
        if (pending + in_place) <= 0:
            continue

        # Find the "front" (in-service) instance: the one whose effective busy interval
        # currently covers end_time. This avoids counting queued/behind tokens.
        front_inst = None
        front_start = float("-inf")
        front_end = None

        for inst in instances:
            # eff_time is your “non-overlapping busy time” for this instance
            eff = float(inst.get("eff_time", inst.get("busy_time", inst.get("delay", 0.0))))
            if eff <= 0:
                continue

            # Prefer the queued-server timestamps we store at scheduling time.
            inst_start = inst.get("busy_start", None)
            inst_end = inst.get("busy_end", None)

            # Backward compatible fallback for older instances
            if inst_start is None or inst_end is None:
                inst_end = float(inst.get("fire_time", 0.0))
                inst_start = inst_end - eff

            inst_start = float(inst_start)
            inst_end = float(inst_end)

            if inst_start < end_time < inst_end and inst_start > front_start:
                front_inst = inst
                front_start = inst_start
                front_end = inst_end

        if front_inst is None:
            continue

        partial_eff_time = max(0.0, min(end_time, front_end) - front_start)
        if partial_eff_time <= 0.0:
            continue

        # Add partial rate impacts for ALL rate-type dimension changes
        for dimension, change_type, value in transition.dimension_changes:
            if change_type != "rate":
                continue
            if dimension not in transition.dimension_table:
                transition.dimension_table[dimension] = 0.0
            transition.dimension_table[dimension] += (
                float(value)
                * partial_eff_time
                * _impact_units(transition, max(1, len(front_inst.get("tokens", []))))
            )

def finalize_enabled_timed_rate_impacts(spn: SPN, end_time: float):
    """
    At simulation end, account for partially elapsed regular timed transitions.

    If the simulation stops before an enabled timed transition fires, add only
    the already elapsed rate-based impact:

        impact = rate * elapsed_time

    not the full transition delay.
    """

    for transition in spn.transitions:
        if getattr(transition, "t_type", None) != "T":
            continue

        if getattr(transition, "parallel_timing", False):
            continue

        if not getattr(transition, "enabled", False):
            continue

        if not getattr(transition, "dimension_changes", None):
            continue

        if not any(change_type == "rate" for _, change_type, _ in transition.dimension_changes):
            continue

        enabled_at = float(getattr(transition, "enabled_at", end_time) or 0.0)
        firing_delay = float(getattr(transition, "firing_delay", 0.0) or 0.0)

        if firing_delay <= 0:
            continue

        elapsed = max(0.0, float(end_time) - enabled_at)

        # Important: only elapsed time, never more than the sampled delay
        elapsed = min(elapsed, firing_delay)

        if elapsed <= 0.0:
            continue

        units = _impact_units(transition, 1.0)

        for dimension, change_type, value in transition.dimension_changes:
            if change_type != "rate":
                continue

            if dimension not in transition.dimension_table:
                transition.dimension_table[dimension] = 0.0

            transition.dimension_table[dimension] += float(value) * elapsed * units

def finalize_immediate_dot_full_rate_impacts(spn: SPN, end_time: float):
    """
    At simulation end, add idle-rate impact for immediate asset-ready transitions.

    Example:
        NIR Eqpt_idle still has a token at the end.
        The waiting time from the last idle entry until simulation end
        must be added to NIR Eqpt_ready__Grid.
    """

    for transition in spn.transitions:
        if getattr(transition, "t_type", None) != "I":
            continue

        if not getattr(transition, "dimension_changes", None):
            continue

        if not any(change_type == "rate" for _, change_type, _ in transition.dimension_changes):
            continue


        dot_inputs = [
            arc.from_place
            for arc in getattr(transition, "input_arcs", [])
            if getattr(arc.from_place, "DoT", 0) == 1
        ]

        if not dot_inputs:
            continue

        # We calculate only for idle places that still contain tokens at the end.
        active_dot_inputs = [
            p for p in dot_inputs
            if len(getattr(p, "tokens", [])) > 0
        ]

        if not active_dot_inputs:
            continue

        starts = []

        for p in active_dot_inputs:
            start = getattr(p, "dot_full_start", None)

            # fallback to tracking_places if dot_full_start is not available
            if start is None:
                tracking_entry = next(
                    (entry for entry in tracking_places if entry["place"] == p),
                    None
                )
                if tracking_entry:
                    start = tracking_entry.get("entrance_time", None)

            if start is not None:
                starts.append(float(start))

        if not starts:
            continue

        idle_start = max(starts)
        duration = float(end_time) - idle_start

        if duration <= 0:
            continue

        for dimension, change_type, value in transition.dimension_changes:
            if change_type != "rate":
                continue

            if dimension not in transition.dimension_table:
                transition.dimension_table[dimension] = 0.0

            transition.dimension_table[dimension] += (
                float(value)
                * duration
                * _impact_units(transition, 1.0)
            )

def simulate(spn: SPN, max_time=10, start_time=0, time_unit=None, verbosity=2, protocol=True, event_log=True,
             Dimensions=None):
    print("Simulation starts", Dimensions)

    global SIMULATION_TIME, SIMULATION_TIME_UNIT, VERBOSITY, PROTOCOL, tracking_places

    VERBOSITY = verbosity
    spn.simulation_time = max_time  # Store max_time in the SPN object

    if VERBOSITY > 0:
        print("Starting simulation...")
        print(f"Simulation time limit = {spn.simulation_time}")

    SIMULATION_TIME = 0
    SIMULATION_TIME_UNIT = time_unit
    PROTOCOL = protocol

    if protocol == True:
        path = os.path.join(os.getcwd(), "../output/protocols/protocol.csv")
        with open(path, "w", newline="") as protocol:
            writer = csv.writer(protocol)
            writer.writerow(["Place", "Time", "Marking"])

    if event_log == True:
        path = os.path.join(os.getcwd(), "../output/event_logs/event_log.csv")
        dims_source = Dimensions if Dimensions is not None else getattr(spn, "executable_dimensions", [])
        dimension_headers = [f"{dim}_Stamp" for dim in dims_source if not is_time_dimension(dim)]
        headers = ["Time_Stamp", "ID"] + dimension_headers + ["Event"]

        with open(path, "w", newline="") as event_log:
            writer = csv.writer(event_log)
            writer.writerow(headers)

    initial_marking = get_initial_marking(spn)
    reset_state(spn, initial_marking)

    # Initialize tracking_places with DoT places
    tracking_places = [
        {
            "place": place,
            "dimension": place.dimension_tracked,
            "entrance_time": 0
        }
        for place in spn.places if place.DoT == 1
    ]

    if VERBOSITY > 1:
        print_marking(spn, SIMULATION_TIME)

    # IMPORTANT: initialize DoT FULL tracking BEFORE the first enabled-flag update.
    # update_enabled_flag(...) can start parallel instances (which consumes tokens),
    # and we must capture the true initial "FULL" marking before any consumption.
    for place in spn.places:
        dot_full_init(place)

    ok = update_enabled_flag(spn)

    while SIMULATION_TIME < max_time and ok == True:
        ok = process_next_event(spn, max_time)
        if verbosity > 2:
            print_state(spn, SIMULATION_TIME)

    if ok == False:
        print("No transitions enabled.")

    if VERBOSITY > 0:
        print("\nTime: {}. Simulation terminated.\n".format(SIMULATION_TIME))

    complete_statistics(spn)

    if VERBOSITY > 0:
        print_statistics(spn, SIMULATION_TIME)

    # Calculate input and output values for transitions
    def _transition_input_product_multiplier(transition: Transition) -> int:
        """
        For input KPI:
        if the input transition consumes tokens with multiplicity k,
        one firing represents k product/case inputs.
        """
        mults = [
            int(getattr(arc, "multiplicity", 1) or 1)
            for arc in getattr(transition, "input_arcs", [])
        ]
        return max(mults) if mults else 1

    def _transition_output_product_multiplier(transition: Transition) -> int:
        """
        For output KPI:
        if the output transition produces product tokens with multiplicity k,
        one firing represents k product/case outputs.
        """
        mults = [
            int(getattr(arc, "multiplicity", 1) or 1)
            for arc in getattr(transition, "output_arcs", [])
        ]
        return max(mults) if mults else 1

    # Calculate input and output values for transitions
    for transition in spn.transitions:
        if transition.input_transition:
            transition.input_value = (
                    transition.n_times_fired
                    * _transition_input_product_multiplier(transition)
            )

        if transition.output_transition:
            transition.output_value = (
                    transition.n_times_fired
                    * _transition_output_product_multiplier(transition)
            )

    for transition in spn.transitions:
        if hasattr(transition, 'input_value'):
            print(f"Input value for {transition.label}: {transition.input_value}")
        if hasattr(transition, 'output_value'):
            print(f"Output value for {transition.label}: {transition.output_value}")
    finalize_parallel_inprocess_rate_impacts(spn, SIMULATION_TIME)
    finalize_enabled_timed_rate_impacts(spn, SIMULATION_TIME)
    finalize_immediate_dot_full_rate_impacts(spn, SIMULATION_TIME)
    dimension_totals = {}

    # Sum dimensions from transitions
    for transition in spn.transitions:
        if hasattr(transition, "dimension_table") and transition.dimension_table:
            for dimension, value in transition.dimension_table.items():
                dimension_totals[dimension] = dimension_totals.get(dimension, 0) + value

    #  Print Final Summary of All Dimensions
    print("\nSummary of Dimensions:")

    print("\nMain dimensions:")
    for dim in spn.dimensions:
        if is_time_dimension(dim):
            print(f"{dim}: {SIMULATION_TIME:.2f}")
        elif dim in getattr(spn, "subdimensions", {}):
            print(f"{dim}: [parent dimension]")
        else:
            print(f"{dim}: {dimension_totals.get(dim, 0.0):.2f}")

    if getattr(spn, "subdimensions", {}):
        print("\nSubdimensions:")
        for parent, children in spn.subdimensions.items():
            for child in children:
                print(f"{child}: {dimension_totals.get(child, 0.0):.2f}")
    print("Simulation ends")

    ############################
    ####WRITE KPIs#############
    ############################
    try:
        dims_source = Dimensions if Dimensions else getattr(spn, "executable_dimensions", None)
        if dims_source:
            dims_order = [d for d in dims_source if d is not None and not is_time_dimension(d)]
        else:
            dims_order = [d for d in dimension_totals.keys() if d not in (None, "time")]
    except Exception:
        dims_order = [d for d in dimension_totals.keys() if d not in (None, "time")]

    # Check if there is ANY input/output transition info at all
    has_input = any(getattr(t, "input_transition", False) or hasattr(t, "input_value") for t in spn.transitions)
    has_output = any(getattr(t, "output_transition", False) or hasattr(t, "output_value") for t in spn.transitions)

    header = ["Time_Stamp"]
    row = [round(SIMULATION_TIME, 2)]

    # Only calculate/write Inputs, Outputs, Throughput if at least one exists
    if has_input or has_output:
        # Detect transitions that actually have input/output values (same logic as your print loop)
        input_transitions = [t for t in spn.transitions if hasattr(t, "input_value")]
        output_transitions = [t for t in spn.transitions if hasattr(t, "output_value")]

        has_input = len(input_transitions) > 0
        has_output = len(output_transitions) > 0

        header = ["Time_Stamp"]
        row = [round(SIMULATION_TIME, 2)]

        # Only calculate/write these 3 if we have ANY input/output transitions
        # Only calculate/write Inputs/Outputs if at least one exists
        if has_input or has_output:
            # transitions that actually have input/output values
            input_transitions = [t for t in spn.transitions if hasattr(t, "input_value")]
            output_transitions = [t for t in spn.transitions if hasattr(t, "output_value")]

            # stable order (so header doesn’t jump around between runs)
            input_transitions = sorted(input_transitions, key=lambda t: t.label)
            output_transitions = sorted(output_transitions, key=lambda t: t.label)

            header = ["Time_Stamp"]
            row = [round(SIMULATION_TIME, 2)]

            # ---- NEW: one column per input transition ----
            for t in input_transitions:
                header.append(f"Input__{t.label}")
                row.append(round(float(getattr(t, "input_value", 0) or 0), 2))

            # ---- NEW: one column per output transition ----
            for t in output_transitions:
                header.append(f"Output__{t.label}")
                row.append(round(float(getattr(t, "output_value", 0) or 0), 2))

            # ---- NO THROUGHPUT ANYMORE ----

            # Always write dimensions
            header += dims_order
            row += [round(float(dimension_totals.get(d, 0.0)), 2) for d in dims_order]

            write_kpis_to_csv(row, path="../output/KPI/kpi.csv", header=header)

            # -----------------------------
            # KPIs per activity (unchanged)
            # -----------------------------
            per_act_header = ["Time_Stamp"]
            per_act_row = [round(SIMULATION_TIME, 2)]

            for t in spn.transitions:
                if hasattr(t, "dimension_table") and t.dimension_table:
                    for dim in sorted([d for d in t.dimension_table.keys() if d is not None]):
                        per_act_header.append(f"{t.label}__{dim}")
                        per_act_row.append(round(float(t.dimension_table.get(dim, 0.0) or 0.0), 2))

            write_kpis_to_csv(
                per_act_row,
                path="../output/KPI/KPIs_per_activitiy.csv",
                header=per_act_header
            )

def write_kpis_to_csv(data, path="../output/KPI/kpi.csv", header=None):
    import csv
    import os

    os.makedirs(os.path.dirname(path), exist_ok=True)

    # If file exists and header changed, rewrite file with the new header and pad old rows
    if header is not None and os.path.exists(path) and os.stat(path).st_size > 0:
        with open(path, "r", newline="") as f:
            reader = csv.reader(f)
            existing_header = next(reader, None)
            existing_rows = list(reader)

        if existing_header != header:
            fixed_rows = []
            for r in existing_rows:
                if len(r) < len(header):
                    r = r + [""] * (len(header) - len(r))
                elif len(r) > len(header):
                    r = r[:len(header)]
                fixed_rows.append(r)

            with open(path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(header)
                writer.writerows(fixed_rows)

    # Write header only if file is empty/new
    write_header = header is not None and (not os.path.exists(path) or os.stat(path).st_size == 0)

    with open(path, "a", newline="") as file:
        writer = csv.writer(file)
        if write_header:
            writer.writerow(header)
        writer.writerow(data)

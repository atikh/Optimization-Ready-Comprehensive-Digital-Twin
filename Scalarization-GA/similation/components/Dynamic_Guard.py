from .RNGFactory import get_max_delay_from_transition

def set_resource_xor_guards(
    spn,
    resource_option_t,
    fallback_option_t,
    resource_activity_t,
    fallback_activity_t=None,
    resource_rate=None,      # REQUIRED (e.g., kWh per minute)
    resource_dim=None        # REQUIRED (e.g., "RES", "CO2", "WASTE", ...)
):
    """
    Complementary XOR guards:
      - resource_option_t enabled iff available(resource_dim) >= required_amount(resource_activity_t)
      - fallback_option_t enabled otherwise

    required_amount = resource_rate * max_time(activity_transition)
    """

    if resource_rate is None:
        raise ValueError("resource_rate must be provided (e.g., 0.02).")
    if resource_dim is None:
        raise ValueError("resource_dim must be provided (e.g., 'RES').")

    if fallback_activity_t is None:
        fallback_activity_t = resource_activity_t

    def current_resource_value():
        total = 0.0
        for tr in spn.transitions:
            if getattr(tr, "dimension_table", None):
                total += float(tr.dimension_table.get(resource_dim, 0.0))
        return total

    def required_amount(activity_t):
        max_time = get_max_delay_from_transition(activity_t)
        return float(resource_rate) * float(max_time)

    def guard_use_resource():
        return current_resource_value() >= required_amount(resource_activity_t)

    def guard_use_fallback():
        return current_resource_value() < required_amount(fallback_activity_t)

    resource_option_t.set_guard_function(guard_use_resource)
    fallback_option_t.set_guard_function(guard_use_fallback)

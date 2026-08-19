import scipy as sp

def get_delay(distribution, a=0.0, b=1.0, c=0.0, d=0.0):

    if distribution == "det":
        return a

    if distribution == "uniform":
        return abs(sp.stats.uniform.rvs(a, b))

    if distribution == "norm":
        return abs(sp.stats.norm.rvs(a, b))

    if distribution == "uniform":
        return abs(sp.stats.uniform.rvs(a, b))

    if distribution == "cauchy":
        return abs(sp.stats.cauchy.rvs(a, b))

    if distribution == "triang":
        return abs(sp.stats.triang.rvs(a, b, c))

    if distribution == "expon":
        return abs(sp.stats.expon.rvs(a, b))

    if distribution == "weibull_min":
        return abs(sp.stats.weibull_min.rvs(a, b, c))

    if distribution == "weibull_max":
        return abs(sp.stats.weibull_max.rvs(a, b, c))

    if distribution == "lognorm":
        return abs(sp.stats.lognorm.rvs(a, b, c))

    if distribution == "gamma":
        return abs(sp.stats.gamma.rvs(a, b, c))

    if distribution == "poisson":
        return abs(sp.stats.poisson.rvs(a, b))

    if distribution == "exponpow":
        return abs(sp.stats.exponpow.rvs(a, b, c))

def get_charging_delay(current_level, charging_rate, max_charging=100.0):
    current_level = float(current_level)
    charging_rate = float(charging_rate)
    max_charging = float(max_charging)

    if charging_rate <= 0:
        raise ValueError("charging_rate must be > 0")

    missing = max(0.0, max_charging - current_level)
    return missing / charging_rate

##### DYNAMIX GUARD
import scipy as sp

def get_max_delay(distribution, a=0.0, b=0.0, c=0.0, d=0.0):
    """
    True mathematical maximum delay (upper bound of support) for your RNGFactory parameterization.
    Returns +inf for distributions with unbounded support (no finite maximum).
    """
    if distribution == "charging":
        if float(a) <= 0:
            return float("inf")
        return float(b) / float(a)

    # Bounded distributions (finite max)
    if distribution == "det":
        return float(a)

    if distribution == "uniform":
        # uniform(loc=a, scale=b) => support [a, a+b]
        return float(a) + float(b)

    if distribution == "triang":
        # triang(shape=a, loc=b, scale=c) => support [b, b+c]
        return float(b) + float(c)

    # Everything else in your RNGFactory is unbounded above (or becomes unbounded due to abs()),
    # so the true maximum is infinite.
    return float("inf")


def get_max_delay_from_transition(transition):
    """Reads transition.distribution dict and returns the true max delay (finite or +inf)."""
    if transition.distribution is None:
        raise ValueError(f"{transition.label} has no distribution set.")

    dist = list(transition.distribution.keys())[0]
    params = transition.distribution[dist]

    return get_max_delay(
        dist,
        params.get("a", 0.0),
        params.get("b", 0.0),
        params.get("c", 0.0),
        params.get("d", 0.0),
    )

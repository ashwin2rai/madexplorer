"""Food-energy quantities for the fertility-input review (MVP 3 Stage 5I). NOT ACTIVE.

Design: ``objective/MVP3_SOCIOECONOMIC_STRATA_DESIGN.md`` §AB. No simulator path calls this
module, it registers no model rule, and nothing here is a scenario setting. The
authoritative ``food_ratio`` and fertility rule are unchanged.

One unit-year of the production energy balance (``energetics.energy_balance_batch``), with
``H`` the harvest after trade (own crop + forage + received - shipped from harvest), ``S``
the stores left after trade, ``R`` the body reserve and ``N`` the requirement:

- **harvest adequacy** (the authoritative ``food_ratio``, H0): ``H / N``;
- **dietary intake** (H1): food actually eaten, ``min(H, N) + X`` with
  ``X = min(max(N - H, 0), S)`` the store withdrawal for consumption, over ``N``. Capped at
  1 (consumption never exceeds the requirement; a fed unit's surplus goes to reserves,
  storage or spoilage, not to intake). Shipped food left the donor before energetics, so
  it is never counted; received food is in ``H`` exactly once;
- **net energy sufficiency** (H2, diagnostic only): ``1 - deficit``, which also counts the
  body-reserve drawdown ``min(N - H - X, R)``. Reserve energy is not food intake.

``N = 0`` gives ratio 1, the ``food_ratio`` convention of ``energy_balance``.
"""

import numpy as np

from madexplorer.core.types import FloatArray


def harvest_adequacy(need: FloatArray, harvest: FloatArray) -> FloatArray:
    """H0: the authoritative ``food_ratio`` expression, bit for bit."""
    ratio: FloatArray = np.divide(harvest, need, out=np.ones_like(need), where=need > 0)
    return ratio


def store_withdrawal(need: FloatArray, harvest: FloatArray, stores: FloatArray) -> FloatArray:
    """``X``: stores eaten this year (the production ``from_stores``; 0 when fed)."""
    fed = harvest >= need
    withdrawn: FloatArray = np.where(fed, 0.0, np.minimum(need - harvest, stores))
    return withdrawn


def reserve_drawdown(
    need: FloatArray, harvest: FloatArray, stores: FloatArray, reserve: FloatArray
) -> FloatArray:
    """Body reserve used to cover what food did not (0 when fed). Not intake."""
    fed = harvest >= need
    left = need - harvest - store_withdrawal(need, harvest, stores)
    drawn: FloatArray = np.where(fed, 0.0, np.minimum(left, reserve))
    return drawn


def dietary_intake_ratio(need: FloatArray, harvest: FloatArray, stores: FloatArray) -> FloatArray:
    """H1: ``(min(H, N) + X) / N``, at most 1; 1 when ``N = 0``.

    ``H + X`` can exceed ``N`` by one rounding step when stores close the gap exactly, so
    the ratio is clipped at 1 (a numerical cap, not a behavioral one). Equals H0 bit for bit
    whenever no stores are eaten and the harvest is short (``X = 0``, ratio < 1); both give
    the same fertility multiplier when the harvest covers the need (the response is flat
    above 1)."""
    fed = harvest >= need
    eaten = harvest + store_withdrawal(need, harvest, stores)
    intake = np.divide(eaten, need, out=np.ones_like(need), where=need > 0)
    ratio: FloatArray = np.where(fed, 1.0, np.minimum(intake, 1.0))
    return ratio


def net_sufficiency(deficit: FloatArray) -> FloatArray:
    """H2 diagnostic: ``1 - deficit`` (intake plus reserve drawdown). Not a fertility rule."""
    out: FloatArray = 1.0 - deficit
    return out

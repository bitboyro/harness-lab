"""Model pricing.

The naive model — one input rate, one output rate — is wrong in three ways that
matter to this benchmark specifically:

1. **Cached input is an order of magnitude cheaper.** Caching disproportionately
   favours arms with a large static prefix (eager-all, flat skills), which is
   exactly why §5.6 requires cost-per-success to be reported cached *and*
   uncached. A flat model cannot express the difference.

2. **Cache writes cost more than fresh input.** So caching is not free money for
   large-prefix arms: they pay a premium on the first run and only come out
   ahead once enough runs reuse the prefix. Whether A1 beats D1 on cost can
   therefore depend on `repeats`, which is a genuinely interesting result and
   one a flat rate would hide.

3. **Long context is a step change, not a surcharge.** Crossing the threshold
   reprices *every* token, not just the excess. An arm that bloats context can
   fall off a cliff rather than sliding down a ramp — and that is precisely what
   the surface-size sweep is looking for.

Contract: archive/reference/experiment-design.md#cost
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

#: Token count above which long-context rates apply to the whole request.
#: Override per model in ``ModelPricing``.
DEFAULT_LONG_CONTEXT_THRESHOLD = 128_000

PRICES_VERIFIED = "2026-08-05"


@dataclass(frozen=True, slots=True)
class Rates:
    """USD per million tokens at one context tier."""

    input: float
    cached_input: float
    cache_write: float
    output: float


@dataclass(frozen=True, slots=True)
class ModelPricing:
    short: Rates
    long: Rates
    long_context_threshold: int = DEFAULT_LONG_CONTEXT_THRESHOLD

    def tier(self, prompt_tokens: int) -> Rates:
        """Which rate card applies. The threshold reprices the whole request."""
        return self.long if prompt_tokens > self.long_context_threshold else self.short


@dataclass(frozen=True, slots=True)
class Cost:
    """One run's cost, decomposed by what drove it."""

    fresh_input_usd: float = 0.0
    cached_input_usd: float = 0.0
    cache_write_usd: float = 0.0
    output_usd: float = 0.0
    tier: str = "short"

    @property
    def total_usd(self) -> float:
        return (self.fresh_input_usd + self.cached_input_usd
                + self.cache_write_usd + self.output_usd)

    def render(self) -> str:
        return (
            f"${self.total_usd:.4f} "
            f"(fresh ${self.fresh_input_usd:.4f}, cached ${self.cached_input_usd:.4f}, "
            f"writes ${self.cache_write_usd:.4f}, out ${self.output_usd:.4f}, {self.tier})"
        )


def price_run(
    pricing: ModelPricing,
    *,
    input_tokens: int,
    cached_input_tokens: int = 0,
    cache_write_tokens: int = 0,
    output_tokens: int = 0,
) -> Cost:
    """Cost one run.

    ``input_tokens`` is the whole prompt. ``cached_input_tokens`` is the part
    served from cache and ``cache_write_tokens`` the part written to it; both are
    *portions of* the prompt, not additions to it.

    That matters: the write rate **replaces** the input rate for those tokens
    rather than being charged on top. The published cards make this plain —
    writes at 1.25x input would be a bizarre surcharge but are a sensible
    premium. Charging both would overstate a large static prefix by more than
    double and make caching look like it never pays off.
    """
    rates = pricing.tier(input_tokens)
    fresh = max(0, input_tokens - cached_input_tokens - cache_write_tokens)
    million = 1_000_000
    return Cost(
        fresh_input_usd=fresh / million * rates.input,
        cached_input_usd=cached_input_tokens / million * rates.cached_input,
        cache_write_usd=cache_write_tokens / million * rates.cache_write,
        output_usd=output_tokens / million * rates.output,
        tier="long" if rates is pricing.long else "short",
    )


# ---- catalogue -----------------------------------------------------------
# Verified 2026-08-05. Prices are volatile; re-check before committing budget.

CATALOGUE: dict[str, ModelPricing] = {
    "gpt-5.6-sol": ModelPricing(
        short=Rates(input=5.00, cached_input=0.50, cache_write=6.25, output=30.00),
        long=Rates(input=10.00, cached_input=1.00, cache_write=12.50, output=45.00),
    ),
    "gpt-5.6-terra": ModelPricing(
        short=Rates(input=2.00, cached_input=0.20, cache_write=2.50, output=12.00),
        long=Rates(input=4.00, cached_input=0.40, cache_write=5.00, output=18.00),
    ),
    "gpt-5.6-luna": ModelPricing(
        short=Rates(input=0.20, cached_input=0.02, cache_write=0.25, output=1.20),
        long=Rates(input=0.40, cached_input=0.04, cache_write=0.50, output=1.80),
    ),
}


class UnknownModel(KeyError):
    """No price on record. Never resolved by guessing."""


def _env_key(model: str) -> str:
    return "HARNESS_PRICE_" + re.sub(r"[^A-Z0-9]", "_", model.upper())


def lookup(model: str) -> ModelPricing:
    """Pricing for a model.

    Exact match, or a *dated snapshot* of a known model. Never a prefix match:
    ``gpt-5.6-luna`` starts with ``gpt-5`` but costs a twenty-fifth as much, and
    this number is shown to a human approving spend.
    """
    if override := os.environ.get(_env_key(model)):
        return _parse_override(model, override)

    if model in CATALOGUE:
        return CATALOGUE[model]

    for base, pricing in CATALOGUE.items():
        remainder = model[len(base):]
        if model.startswith(base) and re.fullmatch(r"-\d{4}-\d{2}-\d{2}", remainder):
            return pricing

    raise UnknownModel(
        f"no price on record for {model!r}. Add it to CATALOGUE (last verified "
        f"{PRICES_VERIFIED}) or set {_env_key(model)}='in,cached,write,out' "
        "(optionally with a long-context card). Guessing would put a wrong "
        "number in front of a spend approval."
    )


def _parse_override(model: str, raw: str) -> ModelPricing:
    """``in,cached,write,out`` — optionally twice for a long-context card."""
    try:
        parts = [float(x) for x in raw.split(",")]
    except ValueError as e:
        raise ValueError(
            f"{_env_key(model)} must be comma-separated USD per Mtok, got {raw!r}"
        ) from e

    if len(parts) == 2:  # the simple case: input,output
        rates = Rates(parts[0], parts[0], parts[0], parts[1])
        return ModelPricing(short=rates, long=rates)
    if len(parts) == 4:
        rates = Rates(*parts)
        return ModelPricing(short=rates, long=rates)
    if len(parts) == 8:
        return ModelPricing(short=Rates(*parts[:4]), long=Rates(*parts[4:]))
    raise ValueError(
        f"{_env_key(model)} needs 2 (in,out), 4 (in,cached,write,out) or 8 "
        f"(short then long) values; got {len(parts)}"
    )


def known_models() -> tuple[str, ...]:
    return tuple(sorted(CATALOGUE))


def break_even_runs(pricing: ModelPricing, prefix_tokens: int) -> int | None:
    """How many runs must share a static prefix before caching pays for itself.

    Not a rounding detail. Writing the cache costs *more* than fresh input
    (~1.25x on the published cards) while reads cost ~0.1x, so a large static
    prefix is a net loss until enough runs reuse it.

    On the current cards this lands at **3 runs** — and the spec's `repeats: >=3`
    sits exactly on that boundary. So whether an eager-all arm looks cheap or
    expensive can hinge on the repeat count rather than on the packaging, which
    is precisely the confound §5.6's cached/uncached split exists to expose.
    Report both, and say which side of break-even the run was on.

    Returns None when caching never wins (cache reads no cheaper than input).
    """
    rates = pricing.tier(prefix_tokens)
    saving_per_reuse = rates.input - rates.cached_input
    if saving_per_reuse <= 0:
        return None
    premium = rates.cache_write - rates.input
    if premium <= 0:
        return 1
    # n runs cached: write + (n-1) reads. Uncached: n * input.
    # Solve for the smallest integer n where cached < uncached.
    n = 1
    while n < 1000:
        cached = rates.cache_write + (n - 1) * rates.cached_input
        if cached < n * rates.input:
            return n
        n += 1
    return None

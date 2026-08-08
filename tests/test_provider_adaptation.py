"""Provider parameter adaptation and the config snapshot.

Reasoning models reject `temperature`. Adapting is fine; adapting *silently*
would leave two arms looking identically configured while sampling differently.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from conftest import BASE_AXES

from harness.engine.axes import preset
from harness.engine.env import load_dotenv
from harness.engine.loop import AgentRunner
from harness.engine.packaging import Materials, Provenance, Result
from harness.engine.provider import ProviderConfig
from harness.engine.pricing import UnknownModel
from harness.engine.providers.openai_provider import (
    OpenAIProvider, _unsupported_parameter,
)

LUNA_ERROR = (
    "Error code: 400 - {'error': {'message': \"Unsupported parameter: "
    "'temperature' is not supported with this model.\", 'type': "
    "'invalid_request_error', 'param': 'temperature'}}"
)


def test_unsupported_parameter_is_extracted_from_the_error() -> None:
    assert _unsupported_parameter(Exception(LUNA_ERROR)) == "temperature"


def test_unrelated_400s_are_not_retried() -> None:
    """A bad schema must not be retried as if it were an unsupported parameter."""
    other = "Error code: 400 - {'error': {'message': 'Invalid schema for function'}}"
    assert _unsupported_parameter(Exception(other)) is None


@dataclass
class FakeResponses:
    """Rejects temperature once, like gpt-5.6-luna does."""

    seen: list[dict] = field(default_factory=list)

    def create(self, **payload: Any) -> Any:
        self.seen.append(payload)
        if "temperature" in payload:
            raise RuntimeError(LUNA_ERROR)
        return _FakeResponse()


class _FakeResponse:
    output: list = []
    usage = None


@dataclass
class FakeSdk:
    responses: FakeResponses = field(default_factory=FakeResponses)


def test_provider_drops_the_rejected_parameter_and_retries_once() -> None:
    p = OpenAIProvider()
    sdk = FakeSdk()
    p._client = sdk

    config = ProviderConfig(model="gpt-5.6-luna", reasoning_effort="low",
                            temperature=0.0, max_turns=4, caching=False)
    p.submit([{"role": "user", "content": "hi"}], (), config)

    assert len(sdk.responses.seen) == 2, "one rejected attempt, one retry"
    assert "temperature" in sdk.responses.seen[0]
    assert "temperature" not in sdk.responses.seen[1]
    assert p.unsupported == ("temperature",)


def test_subsequent_calls_skip_the_rejected_parameter() -> None:
    """Learned once, not re-discovered on every turn at the cost of a 400."""
    p = OpenAIProvider()
    p._client = FakeSdk()
    config = ProviderConfig(model="gpt-5.6-luna", reasoning_effort="low",
                            temperature=0.0, max_turns=4, caching=False)
    p.submit([], (), config)
    p._client = FakeSdk()
    p.submit([], (), config)
    assert len(p._client.responses.seen) == 1, "no wasted rejected attempt"


def test_reasoning_effort_is_always_sent() -> None:
    """V3: an unset default benchmarks effort levels instead of packaging."""
    p = OpenAIProvider()
    p._client = FakeSdk()
    p.submit([], (), ProviderConfig(model="m", reasoning_effort="high",
                                    temperature=None, max_turns=1, caching=False))
    assert p._client.responses.seen[0]["reasoning"] == {"effort": "high"}


def test_config_snapshot_records_the_omission() -> None:
    """The whole point: an unapplied parameter must be visible at analysis time."""

    class Method:
        name = "m"
        def supports(self, v): return True
        def materialize(self, spec, v):
            return Materials((), (), {}, 10, Provenance("g", "1"))
        def executor(self, m): return _NullExec()
        def account(self, t): return t.cost

    class Provider:
        name = "openai"
        base_url = None
        unsupported = ("temperature",)
        def capabilities(self): ...
        def price_per_mtok(self, model): return (1.0, 1.0)
        def submit(self, messages, tools, config):
            from harness.engine.provider import Completion, Usage
            return Completion("FINAL ANSWER: x", (), Usage(1, 0, 1, 0), "stop")

    runner = AgentRunner(
        provider=Provider(), method=Method(), spec=None,
        variant=preset("A1", **BASE_AXES),
        config=ProviderConfig(model="gpt-5.6-luna", reasoning_effort="low",
                              temperature=0.0, max_turns=2, caching=False),
    )
    trace = runner.run("t", "q")
    snap = trace.config_snapshot

    assert snap["temperature_requested"] == 0.0
    assert snap["temperature_applied"] is None, "must not claim it was applied"
    assert snap["unsupported_parameters"] == ["temperature"]
    assert snap["reasoning_effort"] == "low"
    assert trace.to_dict()["config_snapshot"]["unsupported_parameters"] == ["temperature"]


@dataclass
class _NullExec:
    def invoke(self, c): return Result(None, None, 0.0)
    def teardown(self): pass


def test_price_override_for_models_not_in_the_table(monkeypatch) -> None:
    """Self-hosted and private models need a price without editing the catalogue."""
    p = OpenAIProvider()
    with pytest.raises(UnknownModel):
        p.pricing("some-self-hosted-model")

    monkeypatch.setenv("HARNESS_PRICE_SOME_SELF_HOSTED_MODEL", "1.25,10.0")
    assert p.price_per_mtok("some-self-hosted-model") == (1.25, 10.0)


def test_malformed_price_override_is_rejected(monkeypatch) -> None:
    monkeypatch.setenv("HARNESS_PRICE_X", "cheap")
    with pytest.raises(ValueError, match="USD per Mtok"):
        OpenAIProvider().pricing("x")


# ---- .env loading --------------------------------------------------------

def test_dotenv_loads_names_only(tmp_path, monkeypatch) -> None:
    f = tmp_path / ".env"
    f.write_text('# comment\nA=1\nexport B="two"\nEMPTY=\nnot a pair\n')
    monkeypatch.delenv("A", raising=False)
    monkeypatch.delenv("B", raising=False)

    loaded = load_dotenv(f)
    assert set(loaded) == {"A", "B"}, "empty values and comments skipped"
    import os
    assert os.environ["B"] == "two", "quotes stripped"


def test_real_environment_wins_over_the_file(tmp_path, monkeypatch) -> None:
    """`KEY=x harness probe` must override .env, not be silently ignored."""
    f = tmp_path / ".env"
    f.write_text("A=from-file\n")
    monkeypatch.setenv("A", "from-shell")
    assert load_dotenv(f) == []
    import os
    assert os.environ["A"] == "from-shell"


def test_a_variant_is_not_priced_as_its_sibling() -> None:
    """luna and terra share a prefix and differ 10x in price."""
    p = OpenAIProvider()
    assert p.pricing("gpt-5.6-luna").short.input == 0.20
    assert p.pricing("gpt-5.6-terra").short.input == 2.00
    with pytest.raises(UnknownModel):
        p.pricing("gpt-5.6-unreleased")


def test_dated_snapshots_inherit_their_base_price() -> None:
    """A dated snapshot of a model is that model; a sibling is not."""
    p = OpenAIProvider()
    assert p.pricing("gpt-5.6-luna-2026-08-01") == p.pricing("gpt-5.6-luna")

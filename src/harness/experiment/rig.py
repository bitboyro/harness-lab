"""Instance-per-run wiring: every preset, against a fresh catalog.

The seam between the engine and the rig. One `RigInstance` per run holds a
freshly seeded API, an MCP surface over it, and an HTTP server in front of it,
and hands each packaging method the executor it needs.

Isolation is the reason this is per-run rather than per-matrix: a mutating task
that ran against shared state would contaminate every task after it, and the
contamination would be invisible in the results (L1, spec §4.4). Building a
world is milliseconds, so there is no reason to economise here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from harness.engine.axes import (
    Confirmation, Discovery, Invocation, McpRevision, Transport, Variant,
)
from harness.engine.executors import (
    HttpExecutor, McpToolCallExecutor, NullExecutor, PreExecutedExecutor,
)
from harness.engine.generate import ApiSpec, load_spec
from harness.engine.mcp import McpClient
from harness.engine.methods import (
    register_skill_root as _register_skill_root,
    CodeFsMcp, DocsShell, EagerAllMcp, GoldPreExecuted, MetaToolsMcp, NoTools,
    RetrievalMcp,
)

from .domain import WorldShape, build_world
from .http import CatalogServer
from .mcp_surface import McpSurface, transport_for
from .openapi import build_spec
from .server import CatalogApi

# The rig's own authored skill (the V9 pre-registration for the `-auth` arms)
# ships inside this package, beside the world it describes. Registered rather
# than hardcoded in the engine: `skills/` at a user's cwd is *their* convention
# for *their* API, and the engine has no business knowing this package exists.
_register_skill_root(Path(__file__).resolve().parent)

#: Which packaging method serves each preset.
METHOD_FOR_PRESET = {
    "A1": EagerAllMcp, "B1": EagerAllMcp, "B1-auth": EagerAllMcp,
    "A2": MetaToolsMcp, "B2": MetaToolsMcp, "B2-auth": MetaToolsMcp,
    "D3": MetaToolsMcp,
    "D1": CodeFsMcp, "D2": CodeFsMcp, "D2-auth": CodeFsMcp,
    "C1": DocsShell, "C2": DocsShell,
    "E1": RetrievalMcp,
    "M1": EagerAllMcp,
    "Z0": NoTools,
    "Z1": GoldPreExecuted,
}


@dataclass
class RigInstance:
    """One seeded catalog plus every surface an arm might need.

    HTTP is started lazily: only the shell and code arms leave this process, and
    a socket per run for arms that never use one would be waste and a source of
    flakiness under parallelism.
    """

    seed: int = 0
    shape: WorldShape = field(default_factory=WorldShape)
    surface_size: int = 0
    api: CatalogApi = field(init=False)
    spec: ApiSpec = field(init=False)
    _server: CatalogServer | None = field(default=None, init=False)
    _surfaces: list[McpSurface] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        self.api = CatalogApi(seed=self.seed, shape=self.shape)
        self.spec = load_spec(build_spec(self.surface_size))

    # ---- surfaces --------------------------------------------------------

    @property
    def base_url(self) -> str:
        """Start HTTP on first use and keep it for the life of the run."""
        if self._server is None:
            self._server = CatalogServer(self.api, spec=self.spec).start()
        return self._server.base_url

    def mcp_client(self, revision: McpRevision,
                   confirmation: Confirmation = Confirmation.NONE) -> McpClient:
        transport, surface = transport_for(
            self.api, self.spec, confirmation=confirmation,
        )
        self._surfaces.append(surface)
        client = McpClient(transport, revision)
        client.connect()
        return client

    # ---- the seam --------------------------------------------------------

    def executor_for(self, variant: Variant, materials: Any) -> Any:
        """The executor this variant needs, bound to this instance."""
        if variant.transport is Transport.NONE:
            return NullExecutor()

        if variant.transport is Transport.IN_PROCESS:
            # Z1 pre-executes the gold sequence; the runner supplies results.
            return PreExecutedExecutor(())

        if variant.invocation in (Invocation.SHELL, Invocation.CODE):
            # These run outside the process, so they need the socket. Their
            # executor is built by the packaging method, which reads BASE_URL
            # from the environment prepared by `sandbox_env`.
            return None

        if variant.transport is Transport.MCP:
            client = self.mcp_client(
                variant.mcp_revision or McpRevision.R2026_07_28,
                variant.confirmation,
            )
            known = frozenset(t.name for t in materials.tool_defs)
            executor = McpToolCallExecutor(client, known_tools=known)

            if variant.discovery is Discovery.META_TOOLS:
                # The triad dispatches onto the very same executor eager-all
                # uses, so A1 and A2 differ in discovery and nothing else.
                from harness.engine.dispatch import MetaToolDispatcher
                return MetaToolDispatcher(self.spec, executor,
                                          schema_detail=variant.schema_detail)
            return executor

        return HttpExecutor(send=self.api.as_callable())

    def sandbox_env(self) -> dict[str, str]:
        """What a sandboxed arm is allowed to see. Only the target's address."""
        return {"BASE_URL": self.base_url, "TARGET_BASE_URL": self.base_url}

    # ---- state -----------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        return self.api.snapshot()

    def teardown(self) -> None:
        if self._server is not None:
            self._server.stop()
            self._server = None

    def __enter__(self) -> RigInstance:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.teardown()


def method_for(preset_name: str, rig: RigInstance):
    """Build the packaging method for a preset, bound to this instance."""
    cls = METHOD_FOR_PRESET.get(preset_name)
    if cls is None:
        raise KeyError(f"no packaging method mapped for preset {preset_name!r}")

    if cls in (EagerAllMcp, MetaToolsMcp, RetrievalMcp):
        # These need an executor factory; the variant arrives with the call.
        return cls(make_executor=lambda materials, variant:
                   rig.executor_for(variant, materials))
    return cls()


def run_one(
    preset_name: str,
    variant: Variant,
    task,
    provider,
    config,
    *,
    seed: int = 0,
    shape: WorldShape | None = None,
    surface_size: int = 0,
    trace_dir: str | None = None,
    on_turn=None,
):
    """One task, one arm, one fresh catalog.

    Returns (trace, grade). State is snapshotted after the run so writes are
    graded on the server rather than on what the agent claimed — an agent that
    reports success without acting must score as a failure.
    """
    from harness.engine.grader import grade
    from harness.engine.loop import AgentRunner

    with RigInstance(seed=seed, shape=shape or WorldShape(),
                     surface_size=surface_size) as rig:
        method = _bound_method(preset_name, variant, rig, task)

        try:
            runner = AgentRunner(
                provider=provider, method=method, spec=rig.spec,
                variant=variant, config=config,
                forbidden_calls=tuple(task.forbidden_calls),
                trace_dir=trace_dir,
                on_turn=on_turn,
            )
            before = rig.snapshot()
            trace = runner.run(task.id, task.prompt)
            trace.state_before = before
            trace.state_after = rig.snapshot()
            return trace, grade(task, trace)
        finally:
            pass


@dataclass
class RigTarget:
    """The controlled rig as an `engine.target.Target`.

    Holds only the recipe for a world, never a world: isolation is per run
    (L1), so the instance is built inside `run` and torn down with it. That is
    also what lets the matrix run concurrently — a target shared across threads
    would be the one piece of shared state the design spent the most effort
    removing.

    `spec` is a spare copy built from the same parameters, for the callers that
    need to describe the surface without executing against it.
    """

    seed: int = 0
    shape: WorldShape = field(default_factory=WorldShape)
    surface_size: int = 0
    #: Passed through to the agent loop; see `engine.loop.AgentRunner.on_turn`.
    on_turn: Any = None
    spec: ApiSpec = field(init=False)

    def __post_init__(self) -> None:
        self.spec = load_spec(build_spec(self.surface_size))

    def run(self, preset_name: str, variant: Variant, task, provider, config,
            *, trace_dir: str | None = None):
        return run_one(preset_name, variant, task, provider, config,
                       seed=self.seed, shape=self.shape,
                       surface_size=self.surface_size, trace_dir=trace_dir,
                       on_turn=self.on_turn)


def _bound_method(preset_name: str, variant: Variant, rig: RigInstance,
                  task=None):
    """A packaging method whose executor is wired to this rig instance."""
    cls = METHOD_FOR_PRESET.get(preset_name)
    if cls is None:
        raise KeyError(f"no packaging method mapped for preset {preset_name!r}")

    if cls is GoldPreExecuted:
        return cls(prefetched=prefetch_gold(rig, task) if task else "")
    if cls in (EagerAllMcp, MetaToolsMcp, RetrievalMcp):
        return cls(make_executor=lambda materials, _v=None:
                   rig.executor_for(variant, materials),
                   env=rig.sandbox_env())
    return cls(env=rig.sandbox_env())


def prefetch_gold(rig: RigInstance, task) -> str:
    """Run the gold sequence and render its responses for the Z1 context.

    Truncated per response, because an unbounded dump would put Z1 in a
    different context regime from every other arm and quietly measure long
    context instead of the ceiling.
    """
    import json

    if not task.gold_call_sequence:
        return ""

    rendered = []
    for call in task.gold_call_sequence:
        operation = rig.spec.by_id(call.tool) if call.tool else None
        method = (call.method or (operation.method.upper() if operation else "GET"))
        path = call.path or (operation.path if operation else None)
        if not path:
            continue
        args = dict(call.args or {})
        for key in list(args):
            token = "{" + key + "}"
            if token in path:
                path = path.replace(token, str(args.pop(key)))
        if "{" in path:
            # An unresolved template means the gold sequence needs an id only
            # discoverable at run time; skip rather than send a broken request.
            continue
        response = rig.api.handle(method, path, args)
        body = json.dumps(response.body, default=str)
        rendered.append(f"### {method} {path}\n{body[:4000]}")
    return "\n\n".join(rendered)

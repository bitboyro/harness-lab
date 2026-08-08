"""Where an arm's calls actually land.

The only thing that ever differed between the controlled matrix and a field
probe was this: the rig seeds a fresh catalog per run and points the executor at
an ephemeral port, while a field run points it at a customer's live server.
Everything else — task selection, the ledger, concurrency, resume, preflight,
grading, the report — is identical, and for a long time was written twice, with
the field copy reaching none of it.

So the difference gets one seam and no second command. A `Target` answers one
question: given an arm and a task, produce the trace and its grade. `cmd_run`
holds the rest.

This also keeps the layering honest in the direction that matters. `engine`
cannot import `experiment`, so the rig's implementation of this protocol lives
in `experiment/rig.py` and arrives as an argument — the rig is a consumer of the
same interface a field user gets, which is exactly what the seam is for.

Contract: archive/reference/decisions.md G9
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from .generate import ApiSpec
from .grader import GradeResult, grade
from .loop import AgentRunner
from .provider import Provider, ProviderConfig
from .taskpack import TaskPack
from .trace import Trace


@runtime_checkable
class Target(Protocol):
    """One arm, one task, one place for the calls to go."""

    #: The surface every arm's materials are generated from. Held on the target
    #: because only the target knows it: the rig builds one, a field run derives
    #: it from the server's own tools/list.
    spec: ApiSpec

    def run(
        self,
        preset_name: str,
        variant: Any,
        task: Any,
        provider: Provider,
        config: ProviderConfig,
        *,
        trace_dir: str | None = None,
    ) -> tuple[Trace, GradeResult]:
        ...


@dataclass(slots=True)
class FieldTarget:
    """A live API — MCP server or HTTP surface — described by a task pack.

    No isolation and no state snapshot: on someone else's system there is
    nothing to seed and nothing safe to diff, which is why writes stay off and
    `forbidden_calls` carries the harm signal instead. An attempted call *is*
    the finding here, since the alternative evidence — the state change — is not
    ours to inspect.
    """

    pack: TaskPack
    spec: ApiSpec
    #: name -> PackagingMethod, already bound to this target's transport.
    method_for: Any
    #: Passed through to the agent loop; see `AgentRunner.on_turn`.
    on_turn: Any = None

    def run(
        self,
        preset_name: str,
        variant: Any,
        task: Any,
        provider: Provider,
        config: ProviderConfig,
        *,
        trace_dir: str | None = None,
    ) -> tuple[Trace, GradeResult]:
        runner = AgentRunner(
            provider=provider,
            method=self.method_for(preset_name),
            spec=self.spec,
            variant=variant,
            config=config,
            # Pack-level bans apply to every task; the task may add its own. A
            # task can tighten this, never loosen it.
            forbidden_calls=tuple(self.pack.safety.forbidden_calls)
            + tuple(task.forbidden_calls),
            trace_dir=trace_dir,
            on_turn=self.on_turn,
        )
        trace = runner.run(task.id, task.prompt)
        return trace, grade(task, trace)

"""Packaging method plugins.

One per point in the discovery x invocation space. Each is a self-contained file
concern: adding a method never touches the engine, which is what stops the
harness ageing out when the protocol moves — and it moved on 2026-07-28, which is
the proof the seam was needed rather than speculative.

Contract: docs/packaging-method.md §3, §6
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from . import generate
from .axes import Discovery, Instructions, Invocation, Transport, Variant
from .executors import (
    McpToolCallExecutor, NullExecutor, PreExecutedExecutor, code_executor,
    shell_executor,
)
from .generate import ApiSpec
from .packaging import ContextBlock, CostBreakdown, Executor, Materials, register

#: Injected by the runner: builds the transport-bound executor for a variant.
ExecutorFactory = Callable[[Materials, Variant], Executor]


def _instruction_block(spec: ApiSpec, variant: Variant) -> ContextBlock | None:
    """Skill or docs, per the ``instructions`` axis.

    Authored skills are read from disk rather than generated. They deliberately
    break V1, which is the point of the dual condition: the gap between the two
    is the measurement, and pooling them would erase it.
    """
    ins = variant.instructions
    if ins is Instructions.NONE:
        return None

    if ins.is_authored:
        return ContextBlock(
            role="system",
            content=_authored_skill(spec, variant),
            label=str(ins),
        )

    if ins in (Instructions.DOCS_FLAT, Instructions.DOCS_PROGRESSIVE):
        content = generate.curl_reference(spec, variant.doc_budget)
        if ins is Instructions.DOCS_PROGRESSIVE:
            content = _index_only(content)
        return ContextBlock(role="system", content=content, label=str(ins))

    progressive = ins in (
        Instructions.SKILL_GENERATED_PROGRESSIVE,
        Instructions.SKILL_AUTHORED_PROGRESSIVE,
    )
    return ContextBlock(
        role="system",
        content=generate.skill_markdown(spec, variant.doc_budget, progressive=progressive),
        label=str(ins),
    )


def _authored_skill(spec: ApiSpec, variant: Variant) -> str:
    from pathlib import Path
    path = Path("skills") / f"{spec.title.lower().replace(' ', '-')}.md"
    if not path.exists():
        raise FileNotFoundError(
            f"variant requests {variant.instructions} but {path} does not exist. "
            "The authored skill must be committed before results are seen (V9) — "
            "generating one now would defeat the condition."
        )
    return path.read_text()


def _index_only(reference: str) -> str:
    """Headings and one-liners; details fetched on demand."""
    kept, skip = [], False
    for line in reference.splitlines():
        if line.startswith("## "):
            kept.append(line)
            skip = False
        elif line.startswith("# ") or not line.strip():
            kept.append(line)
        elif not skip:
            kept.append(line)
            skip = True
    kept.append("")
    kept.append("Details for any operation are available on request.")
    return "\n".join(kept)


@dataclass
class _Base:
    name: str
    make_executor: ExecutorFactory | None = None

    def executor(self, materials: Materials) -> Executor:
        raise NotImplementedError

    def account(self, trace: Any) -> CostBreakdown:
        """Cost is accumulated live by the client and sandbox.

        Kept as a method so a plugin with an unusual cost model — a polling
        Tasks-extension arm, say, where round trips dominate — can override it
        without the engine knowing.
        """
        return trace.cost


@dataclass
class EagerAllMcp(_Base):
    """A1/B1: every schema in context before turn 1."""

    name: str = "eager-all-mcp"

    def supports(self, v: Variant) -> bool:
        return (v.transport is Transport.MCP
                and v.discovery is Discovery.EAGER_ALL
                and v.invocation is Invocation.TOOL_CALL)

    def materialize(self, spec: ApiSpec, v: Variant) -> Materials:
        spec = spec.limited_to(v.surface_size)
        blocks = [b for b in (_instruction_block(spec, v),) if b]
        return generate.assemble(
            spec, v,
            context_blocks=tuple(blocks),
            tools=generate.tool_defs(spec, v.schema_detail),
            generator="authored" if v.instructions.is_authored else "eager-all-mcp",
            authored_commit=_authored_commit(v),
        )

    def executor(self, materials: Materials) -> Executor:
        return self.make_executor(materials, None)  # type: ignore[misc,arg-type]


@dataclass
class MetaToolsMcp(_Base):
    """A2/B2/D3: a search/describe/invoke triad instead of every schema."""

    name: str = "meta-tools-mcp"

    def supports(self, v: Variant) -> bool:
        return (v.transport is Transport.MCP
                and v.discovery is Discovery.META_TOOLS)

    def materialize(self, spec: ApiSpec, v: Variant) -> Materials:
        spec = spec.limited_to(v.surface_size)
        blocks = [b for b in (_instruction_block(spec, v),) if b]
        return generate.assemble(
            spec, v,
            context_blocks=tuple(blocks),
            tools=generate.meta_tool_defs(spec),
            generator="authored" if v.instructions.is_authored else "meta-tools-mcp",
            authored_commit=_authored_commit(v),
        )

    def executor(self, materials: Materials) -> Executor:
        return self.make_executor(materials, None)  # type: ignore[misc,arg-type]


@dataclass
class CodeFsMcp(_Base):
    """D1/D2: an importable module tree; the model writes code.

    Intermediate results stay in the sandbox and never enter context. Not a
    novel arm — 2602.15945 formalised it first — but omitting it would date the
    benchmark on arrival.
    """

    name: str = "code-fs"

    def supports(self, v: Variant) -> bool:
        return v.discovery is Discovery.CODE_FS and v.invocation is Invocation.CODE

    def materialize(self, spec: ApiSpec, v: Variant) -> Materials:
        spec = spec.limited_to(v.surface_size)
        files = generate.code_module_tree(spec)
        blocks = [ContextBlock(
            role="system",
            content=(
                "An `api` package is available in the working directory. "
                "Import from `api.operations` and write Python to answer the "
                "task. Only what you print is visible to you afterwards.\n\n"
                + files[__import__("pathlib").Path("README.md")].decode()
            ),
            label="code-fs-index",
        )]
        if extra := _instruction_block(spec, v):
            blocks.append(extra)
        return generate.assemble(
            spec, v,
            context_blocks=tuple(blocks),
            sandbox_files=files,
            generator="authored" if v.instructions.is_authored else "code-fs",
            authored_commit=_authored_commit(v),
        )

    def executor(self, materials: Materials) -> Executor:
        return code_executor(materials)


@dataclass
class DocsShell(_Base):
    """C1/C2: freehand curl against a written reference.

    Distinct from ``code-fs``: this tests whether an agent can read docs and
    construct correct requests, not whether keeping intermediates out of context
    pays for itself.
    """

    name: str = "docs-shell"

    def supports(self, v: Variant) -> bool:
        return v.transport is Transport.HTTP_REST and v.invocation is Invocation.SHELL

    def materialize(self, spec: ApiSpec, v: Variant) -> Materials:
        spec = spec.limited_to(v.surface_size)
        block = _instruction_block(spec, v) or ContextBlock(
            role="system",
            content=generate.curl_reference(spec, v.doc_budget),
            label="curl-reference",
        )
        preamble = ContextBlock(
            role="system",
            content=(
                "You have a bash shell. Use `curl` against $BASE_URL to answer "
                "the task. Write one script per step; stdout and stderr come back."
            ),
            label="shell-preamble",
        )
        return generate.assemble(
            spec, v,
            context_blocks=(preamble, block),
            generator="authored" if v.instructions.is_authored else "docs-shell",
            authored_commit=_authored_commit(v),
        )

    def executor(self, materials: Materials) -> Executor:
        return shell_executor(materials)


@dataclass
class NoTools(_Base):
    """Z0: the parametric baseline.

    In controlled mode a score above ~0 voids the experiment — the domain leaked
    into pretraining. In field mode the same number is the finding: how much the
    model already knows about this API without being told anything.
    """

    name: str = "z0-none"

    def supports(self, v: Variant) -> bool:
        return v.transport is Transport.NONE

    def materialize(self, spec: ApiSpec, v: Variant) -> Materials:
        return generate.assemble(spec, v, context_blocks=(), generator="z0-none")

    def executor(self, materials: Materials) -> Executor:
        return NullExecutor()


@dataclass
class GoldPreExecuted(_Base):
    """Z1: the ceiling. The gold sequence has run; the model only synthesises."""

    name: str = "z1-pre-executed"
    results: tuple = ()

    def supports(self, v: Variant) -> bool:
        return v.transport is Transport.IN_PROCESS

    def materialize(self, spec: ApiSpec, v: Variant) -> Materials:
        return generate.assemble(spec, v, context_blocks=(), generator="z1-pre-executed")

    def executor(self, materials: Materials) -> Executor:
        return PreExecutedExecutor(self.results)


def _authored_commit(v: Variant) -> str | None:
    """The commit that proves an authored skill predates the results (V9)."""
    if not v.instructions.is_authored:
        return None
    import subprocess
    try:
        return subprocess.run(
            ["git", "log", "-1", "--format=%H", "--", "skills/"],
            capture_output=True, text=True, check=True,
        ).stdout.strip() or "uncommitted"
    except Exception:  # noqa: BLE001 — absence of git is not a run failure
        return "uncommitted"


def register_defaults(make_mcp_executor: ExecutorFactory) -> None:
    """Register the built-in methods. Called once by the runner."""
    register(EagerAllMcp(make_executor=make_mcp_executor))
    register(MetaToolsMcp(make_executor=make_mcp_executor))
    register(CodeFsMcp())
    register(DocsShell())
    register(NoTools())
    register(GoldPreExecuted())

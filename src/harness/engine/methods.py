"""Packaging method plugins.

One per point in the discovery x invocation space. Each is a self-contained file
concern: adding a method never touches the engine, which is what stops the
harness ageing out when the protocol moves — and it moved on 2026-07-28, which is
the proof the seam was needed rather than speculative.

Contract: archive/reference/packaging-axes.md#plugin-interface
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

#: How a sandboxed arm expresses an action.
#:
#: This is a fairness control, not a nicety. A tool-call arm gets an unmistakable
#: affordance from the provider's function-calling channel; a sandbox arm has
#: only prose. If the prose does not say how to emit a runnable block, the model
#: answers "cannot be determined" without ever trying — and the arm scores 0%
#: for a reason that has nothing to do with its packaging. Every sandbox arm
#: gets the identical wording so none is advantaged by better instructions (V1).
_CODE_PROTOCOL = (
    "To run something, reply with a single fenced code block. The block is "
    "executed in the working directory and you receive its stdout and stderr. "
    "Only what you print comes back to you. Keep going until you have the "
    "answer, then reply with the FINAL ANSWER line and no code block."
)


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


#: Extra places to look for an authored skill, appended by whoever owns them.
#: The rig registers its own fixture here rather than the engine hardcoding a
#: path into `experiment/` — the engine may not know that package exists, and a
#: field user's `./skills/` must keep winning, so these come last.
_EXTRA_SKILL_ROOTS: list["Path"] = []


def register_skill_root(root: "Path") -> None:
    """Add a fallback location for authored skills. Idempotent."""
    if root not in _EXTRA_SKILL_ROOTS:
        _EXTRA_SKILL_ROOTS.append(root)


def _skill_roots() -> list["Path"]:
    """Where an authored skill may live, in precedence order.

    The cwd comes first because `./skills/<api>.md` is the documented convention
    for a user bringing their own authored skill. The repo root follows so a
    matrix launched from elsewhere does not fail every -auth arm with a
    missing-file error that looks like a config mistake rather than a path bug.
    """
    from pathlib import Path
    import os
    here = Path(__file__).resolve()
    # src/harness/engine/methods.py -> repo root
    repo_root = here.parents[3]
    roots = [Path.cwd(), repo_root, *_EXTRA_SKILL_ROOTS]
    if override := os.environ.get("HARNESS_SKILLS_DIR"):
        roots.insert(0, Path(override).parent if Path(override).name == "skills"
                     else Path(override))
    return roots


def _authored_skill(spec: ApiSpec, variant: Variant) -> str:
    from pathlib import Path
    name = f"{spec.title.lower().replace(' ', '-')}.md"
    tried = []
    for root in _skill_roots():
        path = Path(root) / "skills" / name
        tried.append(str(path))
        if path.exists():
            return path.read_text()
    raise FileNotFoundError(
        f"variant requests {variant.instructions} but no authored skill was "
        f"found. Looked in: {', '.join(tried)}. The authored skill must be "
        "committed before results are seen (V9) — generating one now would "
        "defeat the condition."
    )


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
    #: What a sandboxed arm may see. Carried on the method rather than read from
    #: os.environ so runs can execute concurrently: a global mutation means two
    #: parallel runs clobber each other's BASE_URL and silently talk to the
    #: wrong catalog, which grades as a failure and looks like a model error.
    env: dict[str, str] | None = None

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

        if v.invocation is Invocation.CODE:
            # D3: the triad, reached from code rather than as tool calls.
            files = generate.meta_tool_module(spec)
            blocks.insert(0, ContextBlock(
                role="system",
                content=(
                    "An `api` package is available in the working directory. "
                    "Write Python to answer the task.\n\n"
                    + _CODE_PROTOCOL + "\n\n"
                    + files[__import__("pathlib").Path("README.md")].decode()
                ),
                label="meta-tools-code-index",
            ))
            return generate.assemble(
                spec, v,
                context_blocks=tuple(blocks),
                sandbox_files=files,
                generator="authored" if v.instructions.is_authored else "meta-tools-code",
                authored_commit=_authored_commit(v),
            )

        return generate.assemble(
            spec, v,
            context_blocks=tuple(blocks),
            tools=generate.meta_tool_defs(spec),
            generator="authored" if v.instructions.is_authored else "meta-tools-mcp",
            authored_commit=_authored_commit(v),
        )

    def executor(self, materials: Materials) -> Executor:
        if materials.sandbox_files:
            return code_executor(materials, env=self.env or _target_env())
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
                "task.\n\n"
                + _CODE_PROTOCOL
                + "\n\n"
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
        # BASE_URL is the sandbox's only route to the target. Passed explicitly
        # rather than inherited: the environment is emptied so the sandbox
        # cannot read the harness's own credentials.
        return code_executor(materials, env=self.env or _target_env())


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
                "the task.\n\n" + _CODE_PROTOCOL
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
        return shell_executor(materials, env=self.env or _target_env())


@dataclass
class RetrievalMcp(_Base):
    """E1: the harness retrieves top-k schemas; the model never asks.

    The contrast with meta-tools is the point. There, discovery is an action the
    model spends turns on; here it is done for it, so a poor result separates
    "the retriever missed" from "the model chose badly" — which the search arm
    cannot distinguish on its own.
    """

    name: str = "retrieval-mcp"
    k: int = 5

    def supports(self, v: Variant) -> bool:
        return (v.transport is Transport.MCP
                and v.discovery is Discovery.RETRIEVAL
                and v.invocation is Invocation.TOOL_CALL)

    def materialize(self, spec: ApiSpec, v: Variant) -> Materials:
        spec = spec.limited_to(v.surface_size)
        blocks = [b for b in (_instruction_block(spec, v),) if b]
        # Retrieval is per-task, so the full surface is materialised here and
        # narrowed by the runner once it knows the prompt.
        return generate.assemble(
            spec, v,
            context_blocks=tuple(blocks),
            tools=generate.tool_defs(spec, v.schema_detail),
            generator="authored" if v.instructions.is_authored else "retrieval-mcp",
            authored_commit=_authored_commit(v),
        )

    def narrow(self, spec: ApiSpec, v: Variant, prompt: str) -> Materials:
        """Re-materialise with only the top-k operations for this task."""
        from .dispatch import OperationIndex
        spec = spec.limited_to(v.surface_size)
        hits = OperationIndex(spec).search(prompt, self.k)
        kept = tuple(op for op, _ in hits)
        narrowed = type(spec)(spec.title, spec.version, kept, spec.raw)
        blocks = [b for b in (_instruction_block(narrowed, v),) if b]
        return generate.assemble(
            narrowed, v,
            context_blocks=tuple(blocks),
            tools=generate.tool_defs(narrowed, v.schema_detail),
            generator="retrieval-mcp",
        )

    def executor(self, materials: Materials) -> Executor:
        return self.make_executor(materials, None)  # type: ignore[misc,arg-type]


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
    """Z1: the ceiling.

    The gold call sequence is executed *before* the model sees anything, and its
    results are handed over as context. The model does no tool use at all — it
    only has to read the data and answer.

    This is what makes every other number interpretable. A 40% success rate
    means one thing if Z1 scores 100% (the packaging is losing information the
    model could have used) and something entirely different if Z1 scores 45%
    (the task is near-impossible however you present it, or the answer key is
    wrong). Without the ceiling you cannot tell a bad wrapper from a bad task.
    """

    name: str = "z1-pre-executed"
    #: Rendered results of the gold sequence, injected per task by the runner.
    prefetched: str = ""

    def supports(self, v: Variant) -> bool:
        return v.transport is Transport.IN_PROCESS

    def materialize(self, spec: ApiSpec, v: Variant) -> Materials:
        blocks = ()
        if self.prefetched:
            blocks = (ContextBlock(
                role="system",
                content=(
                    "The following API responses have already been fetched for "
                    "you. Answer from them directly; you have no tools.\n\n"
                    + self.prefetched
                ),
                label="z1-prefetched",
            ),)
        return generate.assemble(spec, v, context_blocks=blocks,
                                 generator="z1-pre-executed")

    def executor(self, materials: Materials) -> Executor:
        # No tools by design. A call here means the arm is misconfigured, and
        # recording that is more useful than silently succeeding.
        return PreExecutedExecutor(())


def _target_env() -> dict[str, str]:
    """What a sandbox is allowed to see.

    An allowlist, not a filter: the sandbox runs model-authored code, and one
    that can read ``OPENAI_API_KEY`` is not a sandbox. Only the target's own
    address and credential cross the boundary.
    """
    import os
    allowed = ("BASE_URL", "TARGET_BASE_URL", "TARGET_TOKEN")
    env = {k: os.environ[k] for k in allowed if k in os.environ}
    if "BASE_URL" not in env and "TARGET_BASE_URL" in env:
        env["BASE_URL"] = env["TARGET_BASE_URL"]
    return env


def _authored_commit(v: Variant) -> str | None:
    """The commit that proves an authored skill predates the results (V9)."""
    if not v.instructions.is_authored:
        return None
    import subprocess
    from pathlib import Path
    # Run git in the REPO, not the cwd. This hash is the V9 pre-registration —
    # the evidence the skill predates the results — so recording "uncommitted"
    # because the matrix was launched from elsewhere would quietly destroy it.
    repo_root = Path(__file__).resolve().parents[3]
    try:
        return subprocess.run(
            ["git", "-C", str(repo_root), "log", "-1", "--format=%H",
             "--", "src/harness/experiment/skills/", "skills/"],
            capture_output=True, text=True, check=True,
        ).stdout.strip() or "uncommitted"
    except Exception:  # noqa: BLE001 — absence of git is not a run failure
        return "uncommitted"


def register_defaults(make_mcp_executor: ExecutorFactory) -> None:
    """Register the built-in methods. Called once by the runner."""
    register(EagerAllMcp(make_executor=make_mcp_executor))
    register(MetaToolsMcp(make_executor=make_mcp_executor))
    register(RetrievalMcp(make_executor=make_mcp_executor))
    register(CodeFsMcp())
    register(DocsShell())
    register(NoTools())
    register(GoldPreExecuted())

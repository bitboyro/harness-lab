"""Command line entry point.

Three commands matching the three output tiers:

    harness lint <spec>                    T1 — static, free, no model
    harness run --pack <p> --probe         T2 — first contact with a live target
    harness run                            T3 — the controlled matrix
    harness plan <plan.yaml>               cost projection and approval gate

`run` is one command with one execution path. Whether the calls land on a
freshly seeded rig or a customer's live server is a *target* (engine/target.py),
not a separate command — when it was one, field mode reached none of the ledger,
concurrency, resume or reporting that the matrix had.

Nothing here spends money without printing the projection first and asking.
"""

from __future__ import annotations

import argparse
import json
import os

import yaml
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .engine import lint as lint_mod
from .engine.analysis import RANK_KEYS as _RANK_KEYS
from .engine.axes import (
    Caching, ConfigError, DocBudget, ErrorDetail, McpRevision, ResponseShape,
    SchemaDetail, preset,
)
from .engine.compute import compute, report_footer
from .engine.generate import load_spec
from .engine.loop import AgentRunner
from .engine.methods import register_defaults
from .engine.packaging import resolve
from .engine.planner import load_plan
from .engine.provider import ProviderConfig
from .engine.taskpack import load as load_pack

#: Distinct from Ctrl-C's 130 so a wrapper script can tell "the operator
#: stopped this" from "the machine or the provider broke".
_EXIT_INFRA = 40

#: A resume whose rebuilt world does not match the one on disk. Shares 3 with
#: `compare`'s pooling refusal because it is the same refusal caught earlier:
#: both mean "these rows cannot go in the same table", and a wrapper doing
#: `harness run --resume && harness compare … && publish` wants one code for
#: "I stopped rather than mix two worlds".
_EXIT_REFUSED = 3

def _operator_errors() -> tuple[type[BaseException], ...]:
    """Failures that are the operator's to fix, not a result to record.

    Imported lazily and by name so this module keeps its cold-start cost: the
    engine's error types pull in the provider stack, and `harness lint` should
    not pay for that to print a scorecard.
    """
    from .engine.axes import ConfigError
    from .engine.pricing import UnknownModel
    from .engine.taskpack import PackError

    return (ConfigError, UnknownModel, PackError, PackTargetError)


DEFAULT_PROBE_PRESETS = ("Z0", "A1", "A2", "C1", "D1")


def _pack_digest(tasks) -> str:
    """A content address for the task set a run actually attempted.

    `core_id` is positional — `core-000` exists in every run this rig has
    produced — so two runs cannot be paired within core on the strength of
    matching seeds alone: a manifest is hand-editable and `--classes` or
    `--max-tasks` can cut the set without changing a single world parameter.
    This digest is the thing that is actually true about the tasks, and it is
    why `stats.world_key` prefers it over the parameter tuple.

    **The prompt is what makes it a content address.** Task *ids* are as
    positional as core ids: seed 1 and seed 2 both produce a `core-000-R`, and
    they ask about different shows. A digest over ids alone therefore collides
    across worlds — and because `world_key` prefers the digest, it would
    override the `(seed, cores, fan_out, difficulty)` tuple that correctly
    refuses. That is worse than having no digest at all, so the prompt is
    hashed with the structure.
    """
    import hashlib
    material = sorted((t.id, t.core_id or "", str(t.task_class), t.answerable,
                       t.prompt)
                      for t in tasks)
    payload = json.dumps(material, sort_keys=True, default=str).encode()
    return hashlib.sha256(payload).hexdigest()[:16]


def _sanitize_target_url(value: str) -> str:
    """Drop credentials from a target identity before it hits the manifest.

    Published runs commit ``manifest.json``. A token in the query string or
    userinfo would turn a shareable artifact into a leaked key. Paths and
    non-URL values pass through unchanged.
    """
    from urllib.parse import urlsplit, urlunsplit

    parts = urlsplit(value)
    if not parts.scheme or not parts.netloc:
        return value
    host = parts.hostname
    if host is None:
        # Malformed netloc — still drop query/fragment and anything before @.
        return urlunsplit((parts.scheme, parts.netloc.rsplit("@", 1)[-1],
                           parts.path, "", ""))
    if ":" in host:
        host = f"[{host}]"
    netloc = f"{host}:{parts.port}" if parts.port is not None else host
    return urlunsplit((parts.scheme, netloc, parts.path, "", ""))


def _resolve_pack_target(pack) -> str:
    """The independent variable a field run was pointed at.

    Preference matches how ``_field_target`` chooses a surface: the live MCP
    URL, else the OpenAPI location, else whatever ``base_url_env`` names in
    the environment. Credentials never leave this function.
    """
    if pack.api.mcp and pack.api.mcp.url:
        return _sanitize_target_url(pack.api.mcp.url)
    if pack.api.openapi:
        return _sanitize_target_url(pack.api.openapi)
    env_name = pack.api.base_url_env
    if env_name:
        raw = os.environ.get(env_name)
        if raw:
            return _sanitize_target_url(raw)
        return env_name
    return ""


def _field_manifest_fields(pack, pack_path: str) -> dict[str, Any]:
    """Identity of the pack/target under test, for ``harness compare``.

    Omitted entirely on controlled runs — writing ``None`` would invent a
    recorded value, and ``NOT_RECORDED`` is the honest read for a rig matrix.
    """
    return {
        "pack_name": pack.pack.id,
        "pack_path": pack_path,
        "target": _resolve_pack_target(pack),
    }


def _base_axes(args: argparse.Namespace) -> dict:
    return dict(
        schema_detail=SchemaDetail(args.schema_detail),
        response_shape=ResponseShape(args.response_shape),
        error_detail=ErrorDetail(args.error_detail),
        doc_budget=DocBudget(args.doc_budget),
        surface_size=args.surface_size,
        model=args.model,
        reasoning_effort=args.reasoning_effort,
        temperature=args.temperature,
        caching=Caching(args.caching),
        repeats=args.repeats,
        mcp_revision=McpRevision(args.mcp_revision),
    )


# ---- T1 ------------------------------------------------------------------

def cmd_lint(args: argparse.Namespace) -> int:
    from .engine import rules
    rules.register_defaults()

    if args.demo:
        # The built-in rig's own spec. Exists so the free tier has a first
        # command that needs no file, no key and no shell tricks — the
        # documented one was a bash process substitution that broke under sh.
        from .experiment.openapi import build_spec
        spec = load_spec(build_spec())
    elif not args.spec:
        print("nothing to lint. Pass an OpenAPI file or URL, or --demo to try "
              "it on the built-in API.", file=sys.stderr)
        return 2
    else:
        spec = load_spec(args.spec)
    card = lint_mod.scorecard(spec)

    print(f"{spec.title} v{spec.version} — {len(spec.operations)} operations\n")
    if not card.findings:
        print("  no findings")
    for f in card.findings:
        mark = "!" if f.confidence is lint_mod.Confidence.MEASURED else "?"
        print(f"  [{f.severity}]{mark} {f.rule_id}: {f.message}")
    print(f"\n{card.footer()}")
    return 0


# ---- T2 ------------------------------------------------------------------

def _mcp_executor_factory(pack, revision):
    """Build the transport-bound executor the MCP arms need.

    Connects once and reuses the client, so the legacy handshake is paid once
    per run rather than once per call — otherwise the cost comparison between
    revisions would be measuring our own client instead of the protocol.
    """
    from .engine.executors import McpToolCallExecutor
    from .engine.mcp import McpClient
    from .engine.mcp.transport import HttpTransport

    if not pack.api.mcp:
        return None

    def make(materials, _variant):
        transport = HttpTransport.from_env(
            pack.api.mcp.url,
            auth_type=pack.api.auth.type,
            auth_env=pack.api.auth.env,
            header_name=pack.api.auth.header_name,
        )
        client = McpClient(transport, revision)
        client.connect()
        return McpToolCallExecutor(client)

    return make


def _bind_field_method(variant, task, make_executor, spec):
    """Wire a packaging method to a live target by axis match, not by name.

    Fail closed: an unknown arm raises ``ConfigError`` from ``preset()``
    before we get here; an unsupported axis corner raises from ``resolve``.
    There is no EagerAllMcp fallback — that is what silently dropped the
    skill condition on probe's B1/B2.
    """
    from .engine.axes import Discovery, Invocation
    from .engine.dispatch import MetaToolDispatcher

    register_defaults()
    method = resolve(variant)
    kwargs: dict[str, Any] = {}
    if "prefetch" in method.needs:
        # Field targets have no gold sequence to pre-execute. Binding an empty
        # prefetch lets materialize succeed; the matrix preflight drops the
        # arm when the target cannot supply real gold responses.
        gold = getattr(task, "gold_call_sequence", None) if task else None
        kwargs["prefetched"] = "" if not gold else ""
    if "sandbox_env" in method.needs:
        kwargs["env"] = None  # sandbox reads TARGET_BASE_URL from os.environ
    if "executor_factory" in method.needs:
        if make_executor is None:
            raise ConfigError(
                f"arm {variant.preset!r} needs an MCP executor but the pack "
                f"has no api.mcp — cannot bind {method.name}"
            )
        if (variant.discovery is Discovery.META_TOOLS
                and variant.invocation is Invocation.TOOL_CALL):
            # The triad dispatches onto the same executor eager-all uses, so
            # the arms differ in discovery and nothing else.
            kwargs["make_executor"] = (
                lambda materials, _v=None: MetaToolDispatcher(
                    spec, make_executor(materials, None)
                )
            )
        else:
            kwargs["make_executor"] = make_executor
    return method.bind(**kwargs)


def _apply_smoke_profile(args: argparse.Namespace) -> None:
    """``--smoke``: does the whole pipeline work, for about five cents.

    Not a result and never reported as one — three arms over two cores cannot
    resolve any contrast. It exists so "is this installed correctly" has an
    answer that is not "run the matrix and find out in eight hours".
    """
    if not args.presets:
        args.presets = ["Z0", "A1", "D1"]
    args.cores = min(args.cores, 2)
    args.max_tasks = args.max_tasks or 4
    args.repeats = 1


def _apply_probe_profile(args: argparse.Namespace) -> None:
    """``--probe``: first contact with a target, not a benchmark.

    The arms cmd_probe used to default to, one repeat, and no resume — a probe
    is meant to be thrown away and re-run once the pack improves, not continued
    into a ledger that then mixes two task sets.
    """
    if not args.presets:
        args.presets = list(DEFAULT_PROBE_PRESETS)
    args.repeats = 1
    args.resume = False


def _field_target(args: argparse.Namespace, pack):
    """A live target described by a pack: MCP server, or a plain HTTP surface.

    Returns ``(target, revision)``. The revision comes back because it is
    resolved here — possibly by asking the server — and both the axes and the
    manifest have to record the one actually used, never the one requested.
    """
    from .engine.axes import McpRevision
    from .engine.target import FieldTarget

    # Resolve spec_revision before anything is spent.
    revision = McpRevision(args.mcp_revision)
    if pack.api.mcp and pack.api.mcp.spec_revision == "auto":
        from .engine.mcp import detect_revision
        from .engine.mcp.transport import probe_server
        revision = detect_revision(probe_server(pack.api.mcp.url))
        print(f"detected MCP revision: {revision.value}")

    # The surface. For a live MCP target it comes from the server's own
    # tools/list — requiring a hand-written OpenAPI alongside would guarantee
    # the two drift, and the server is the thing under test.
    if args.spec:
        spec = load_spec(args.spec)
    elif pack.api.mcp:
        from .engine.generate import spec_from_tools
        from .engine.mcp import McpClient
        from .engine.mcp.transport import HttpTransport
        probe_client = McpClient(
            HttpTransport.from_env(pack.api.mcp.url,
                                   auth_type=pack.api.auth.type,
                                   auth_env=pack.api.auth.env,
                                   header_name=pack.api.auth.header_name),
            revision)
        probe_client.connect()
        listed = probe_client.list_tools()
        spec = spec_from_tools(listed.tools, title=pack.pack.id)
        print(f"derived surface from tools/list: {len(spec.operations)} tools")
    elif pack.api.openapi:
        spec = load_spec(pack.api.openapi)
    else:
        raise PackTargetError(
            "no --spec, no api.mcp, and no api.openapi — nothing to describe "
            "the surface with")

    make_executor = _mcp_executor_factory(pack, revision)
    target = FieldTarget(
        pack=pack, spec=spec,
        bind_method=lambda variant, task: _bind_field_method(
            variant, task, make_executor, spec
        ),
    )
    return target, revision


class PackTargetError(Exception):
    """A pack that names no reachable surface. Operator error, not a result."""


# ---- planning ------------------------------------------------------------

def cmd_arms(args: argparse.Namespace) -> int:
    """List resolved arms with derived names — no hand-written blurbs."""
    from .engine.axes import (
        Caching, DocBudget, ErrorDetail, McpRevision, ResponseShape,
        SchemaDetail, describe, preset, short_name,
    )
    from .engine.methods import register_defaults
    from .engine.packaging import resolve

    register_defaults()
    if args.plan:
        plan = load_plan(args.plan)
        names = plan.presets
        base = plan.base
    else:
        from .engine.axes import builtin_arm_names
        names = builtin_arm_names()
        base = dict(
            schema_detail=SchemaDetail.STANDARD,
            response_shape=ResponseShape.AS_IS,
            error_detail=ErrorDetail.FIELD_SCOPED,
            doc_budget=DocBudget.STANDARD, surface_size=0,
            model="?", reasoning_effort="low", temperature=0.0,
            caching=Caching.OFF, repeats=1,
            mcp_revision=McpRevision.R2026_07_28,
        )
    # Coerce YAML strings in plan.base.
    from .engine.axes import axis_by_name, coerce_axis_value
    typed = {}
    for k, v in base.items():
        typed[k] = coerce_axis_value(k, v) if axis_by_name(k) else v

    for name in names:
        variant = preset(name, **typed)
        method = resolve(variant)
        print(f"{name:<12} {method.name:<18} {short_name(variant)}")
        print(f"{'':12} {describe(variant)}")
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    plan = load_plan(args.plan)
    plan.validate_contrasts()
    if args.strict:
        plan.require_preregistration()

    from .engine.providers import get as get_provider
    estimate = plan.estimate(get_provider(args.provider))

    print(f"{plan.id}\n  {plan.rationale.strip()}\n")
    if getattr(args, "explain", False):
        print(_explain_plan(plan, estimate))
    else:
        print(estimate.render())
    if plan.max_usd is not None and estimate.projected_usd > plan.max_usd:
        print(f"\nrefuses budget.max_usd=${plan.max_usd:,.2f}: "
              f"projection ${estimate.projected_usd:,.2f}. Cut arms, cores, "
              f"or repeats — cheapest cut is usually dropping an exploratory arm.")

    if args.approve:
        if not _confirm():
            print("\nnot approved")
            return 1
        plan.approve(estimate, persist=True)
        print(f"\napproved for this matrix size "
              f"(digest {plan.digest()}, {estimate.runs} runs)")
    return 0


def _explain_plan(plan, estimate) -> str:
    lines = [
        f"  arms:      {len(plan.presets)} ({', '.join(plan.presets)})",
        f"  tasks:     {plan.task_count}"
        + (f"  via {plan.tasks}" if plan.tasks else ""),
        f"  sweep:     {plan.sweep or '(none)'}",
        f"  budget:    {plan.budget or '(none)'}",
        f"  digest:    {plan.digest()}",
        "",
        estimate.render(),
    ]
    return "\n".join(lines)


def _apply_plan(args: argparse.Namespace) -> None:
    """Overlay a run plan onto argparse defaults. Flags already set win."""
    if not getattr(args, "plan", None):
        return
    plan = load_plan(args.plan)
    _apply_run_plan_to_args(args, plan)
    args._plan = plan


def _apply_run_plan_to_args(args: argparse.Namespace, plan) -> None:
    """Fill unset run flags from a resolved :class:`RunPlan`."""
    args.plan_id = plan.id
    if not args.presets:
        args.presets = list(plan.presets)
    if args.id in ("phase-0", None):
        args.id = plan.id
    base = plan.base
    for flag, key in (
        ("model", "model"), ("reasoning_effort", "reasoning_effort"),
        ("temperature", "temperature"), ("caching", "caching"),
        ("repeats", "repeats"), ("surface_size", "surface_size"),
        ("schema_detail", "schema_detail"), ("response_shape", "response_shape"),
        ("error_detail", "error_detail"), ("doc_budget", "doc_budget"),
        ("mcp_revision", "mcp_revision"),
    ):
        if key in base and _is_cli_default(args, flag):
            val = base[key]
            setattr(args, flag, getattr(val, "value", val))
    gen = (plan.tasks or {}).get("generate") or {}
    if gen:
        if _is_cli_default(args, "cores") and "cores" in gen:
            args.cores = int(gen["cores"])
        if _is_cli_default(args, "seed") and "seed" in gen:
            args.seed = int(gen["seed"])
        if _is_cli_default(args, "fan_out") and "fan_out" in gen:
            args.fan_out = int(gen["fan_out"])
        if _is_cli_default(args, "difficulty") and "difficulty" in gen:
            args.difficulty = str(gen["difficulty"])
    pack = (plan.tasks or {}).get("pack")
    if pack and not getattr(args, "pack", None):
        args.pack = Path(pack)
    if plan.sweep.get("error_detail") and not getattr(args, "sweep_error_detail", None):
        args.sweep_error_detail = list(plan.sweep["error_detail"])


def _is_cli_default(args: argparse.Namespace, flag: str) -> bool:
    """Whether ``flag`` still holds the argparse default (plan may override)."""
    defaults = {
        "model": "gpt-5.6-luna", "reasoning_effort": "low", "temperature": 0.0,
        "caching": "off", "repeats": 1, "surface_size": 0,
        "schema_detail": "standard", "response_shape": "as-is",
        "error_detail": "field-scoped", "doc_budget": "standard",
        "mcp_revision": "2026-07-28", "cores": 3, "seed": 1, "fan_out": 8,
        "difficulty": "standard",
    }
    return getattr(args, flag, None) == defaults.get(flag)


def cmd_rig(args: argparse.Namespace) -> int:
    """Generate a controlled rig: OpenAPI spec + task pack, sized deliberately.

    Core count is per-run, not a global constant, because different comparisons
    need different amounts of data. The power table prints alongside so the size
    is chosen against what it buys rather than inherited.
    """
    import json

    from .engine.taskpack import TaskPack
    from .experiment.domain import WorldShape, build_world, shape_for_cores
    from .experiment.openapi import build_spec
    from .experiment.power import Contrast, analyse, cores_for, report
    from .experiment.tasks import build_pack

    if args.for_contrast and args.target_mde:
        contrast = Contrast(args.for_contrast)
        needed = cores_for(contrast, args.target_mde, repeats=args.repeats)
        if needed is None:
            print(f"cannot reach {args.target_mde} pp on {contrast} at any "
                  "practical core count; relax the target or the design")
            return 1
        print(f"{contrast} at {args.target_mde} pp needs {needed} cores "
              f"({args.repeats} repeats) — using that")
        cores = needed
    else:
        cores = args.cores

    print()
    print(report(cores, repeats=args.repeats))
    print()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    # Grow the world to fit the requested cores. Too few would silently
    # invalidate the power table printed above.
    shape = shape_for_cores(cores, WorldShape(episodes_per_season=args.fan_out))
    world = build_world(args.seed, shape)
    spec = build_spec(args.surface_size)
    pack = build_pack(world, cores=cores, seed=args.seed,
                      openapi_path="./catalog.openapi.json")

    # Validate through the public loader — the rig is a consumer of the engine,
    # so a pack it cannot load is a bug in the rig, not a special case.
    loaded = TaskPack.parse(pack)

    (out / "catalog.openapi.json").write_text(json.dumps(spec, indent=2))
    (out / "pack.yaml").write_text(yaml.safe_dump(pack, sort_keys=False))

    operations = len(spec["paths"])
    print(f"wrote {out}/catalog.openapi.json  ({operations} paths, "
          f"surface_size={args.surface_size or 'core only'})")
    print(f"wrote {out}/pack.yaml            ({len(loaded.tasks)} tasks "
          f"from {cores} cores, seed={args.seed})")

    unanswerable = sum(1 for t in loaded.tasks if not t.answerable)
    print(f"  {unanswerable} unanswerable tasks (false-positive answering)")
    print(f"  fan-out {args.fan_out} episodes per season")
    return 0


#: Headroom left unclaimed by a matrix. On an 8GB machine macOS grows its swap
#: file on the same volume the traces land on; filling the disk therefore does
#: not merely fail a write, it removes the kernel's ability to page and the
#: matrix gets SIGKILLed at 99% complete. Ask 5GB observed once, on 2026-08-06.
_DISK_RESERVE_BYTES = 5 * 2**30

#: Observed mean across matrix-40's 6189 traces, compressed: 870KB of JSON at
#: ~87% gzip. Only used for the projection, and only until this run has written
#: traces of its own to measure.
_TRACE_BYTES = 230_000


def _disk_reserve_bytes(args: argparse.Namespace) -> int:
    """Swap headroom required before a matrix starts.

    Full matrices keep the 5GB default — the 2026-08-06 incident. Smoke,
    probe, and experiment smoke slices skip it: they finish in a minute and
    write a few MB of traces, so the reserve was blocking dev machines that
    had room for the run itself.
    """
    if getattr(args, "disk_reserve_gb", None) is not None:
        return max(0, int(args.disk_reserve_gb * 2**30))
    if args.smoke or args.probe:
        return 0
    if getattr(args, "experiment_slice", None) == "smoke":
        return 0
    return _DISK_RESERVE_BYTES


def _disk_shortfall(store, planned: int,
                    reserve_bytes: int = _DISK_RESERVE_BYTES) -> tuple[int, int] | None:
    """(needed, free) if this matrix cannot fit, else None.

    Eight hours of API spend should not die at 99% because nothing looked at
    free space first.
    """
    import shutil

    # Only `.json.gz` samples: what this run will write is compressed, and a
    # resumed directory can still hold uncompressed traces from before the
    # format changed. Averaging the two would project ~4x the real need and
    # refuse a matrix that fits comfortably.
    sample = [p.stat().st_size for p in
              sorted((store.root / "traces").glob("*.json.gz"))[-200:]]
    per_trace = (sum(sample) / len(sample)) if sample else _TRACE_BYTES
    need = int(planned * max(per_trace, 1))
    free = shutil.disk_usage(store.root).free
    return (need, free) if need + reserve_bytes > free else None


def _preflight(provider, config) -> str | None:
    """One cheap completion before the matrix starts. Returns a reason to stop.

    A dead key or an unknown model is Layer 1 — an operator mistake, not a
    result — and finding it on cell 1 of 7800 after the spend prompt has been
    accepted is finding it too late. Anything transient is ignored here: the
    retry and resume paths exist for that, and refusing to start over one
    timeout would be its own kind of broken.
    """
    from .engine.infra import FATAL, classify

    try:
        provider.submit([{"role": "user", "content": "ok"}], (), config)
    except Exception as e:  # noqa: BLE001 — classifying is the whole job
        kind = classify(e)
        if kind in FATAL:
            return f"{kind}: {type(e).__name__}: {e}"
        # Layer 1 shows up as a plain RuntimeError from client construction
        # (missing key, missing SDK) — no status, no provider code to read.
        if not getattr(e, "status_code", None) and isinstance(e, (RuntimeError, ImportError)):
            return f"config: {type(e).__name__}: {e}"
    return None


#: Manifest fields that define *which matrix this is*, under the argparse dest
#: they were parsed from. A resume has to reproduce every one: each either
#: seeds the world, selects the cells, or lands in a pooling key. `concurrency`
#: is deliberately absent — it changes how fast the remaining cells run, never
#: what they measure — as are `id`, `out` and `yes`.
_RESUME_INHERITED = (
    "model", "provider", "reasoning_effort", "temperature", "caching",
    "max_turns", "repeats", "seed", "cores", "fan_out", "surface_size",
    "difficulty", "schema_detail", "response_shape", "error_detail",
    "doc_budget", "mcp_revision", "presets", "sweep_error_detail",
    "classes", "max_tasks",
)

#: Of those, the ones argparse leaves as None-or-list, where None and [] mean
#: the same thing and a bare `!=` would report a difference that isn't one.
_RESUME_LIST_FIELDS = frozenset({"presets", "sweep_error_detail", "classes"})


def _inherit_run_config(args: argparse.Namespace,
                        manifest: dict[str, Any],
                        *,
                        skip: frozenset[str] = frozenset()) -> list[str]:
    """Make `--resume` reproduce the run it is resuming.

    Without this a resume is shaped by argparse defaults rather than by the
    matrix on disk, and the two disagree in silence. Not a cosmetic bug:
    `--cores` reseeds the world, so a default-shaped resume rebuilds a
    *different* catalog and grades the re-run cells against the wrong answer
    key; `--model` and `--mcp-revision` are pooling keys (G-rule "never pool"),
    so a mismatch appends rows `harness compare` must then refuse to average.
    A row carries no record of which invocation produced it, so none of that is
    recoverable afterwards — it has to be prevented here.

    The manifest is authoritative because it is what produced the rows already
    on disk. Returns the fields it had to change so the caller can print them
    before spending: an overridden flag that nobody mentions is its own trap.

    ``skip`` names fields an experiment sidecar owns (``presets``) so additive
    arm growth does not inherit the manifest's frozen arm list.
    """
    changed: list[str] = []
    for field in _RESUME_INHERITED:
        if field in skip:
            continue
        if field not in manifest:
            continue  # written by an older harness; leave this arg alone
        stored, current = manifest[field], getattr(args, field)
        if field in _RESUME_LIST_FIELDS:
            stored, current = list(stored or []), list(current or [])
            if stored != current:
                setattr(args, field, stored or None)
        elif stored != current:
            setattr(args, field, stored)
        if stored != current:
            changed.append(f"  {field}: {current!r} -> {stored!r}")
    return changed


def _stream_watcher(concurrency: int):
    """Print each turn as it lands. Returns None when streaming is off.

    Serialised behind a lock because at any concurrency above 1 several runs
    interleave, and two half-written turns spliced together are less readable
    than no transcript at all. The lock is held only for the write, so a slow
    terminal cannot stall a provider call.

    Uses the showcase style: MCP envelopes unwrapped, arguments as key/value
    lines, preamble collapsed, FINAL ANSWER highlighted — the plain style is
    what ``harness transcript`` keeps for machine-stable replay.
    """
    import threading

    from .engine.transcript import render_turn, stream_run_banner

    lock = threading.Lock()
    seen: set[str] = set()

    def watch(trace, index: int) -> None:
        text = render_turn(trace, index, style="showcase")
        with lock:
            if trace.run_id not in seen:
                seen.add(trace.run_id)
                print(f"\n{stream_run_banner(trace)}", flush=True)
            print(text, flush=True)

    if concurrency > 1:
        print(f"note: --stream at --concurrency {concurrency}; turns from "
              f"different runs interleave. Use --concurrency 1 to read one "
              f"run end to end.")
    return watch


def cmd_run(args: argparse.Namespace) -> int:
    """Run the controlled rig across arms and persist everything."""
    from .engine.compute import compute
    from .engine.pricing import lookup, price_run
    from .engine.reporting import render
    from collections import Counter

    from .engine.infra import FATAL, classify
    from .engine.results import ResultStore, build_row, infra_row
    from .engine.taskpack import TaskPack
    from .experiment.domain import WorldShape, build_world, shape_for_cores
    from .experiment.rig import RigTarget
    from .experiment.tasks import build_pack

    if args.smoke:
        _apply_smoke_profile(args)
    if args.probe:
        _apply_probe_profile(args)
    _apply_plan(args)

    # Priced before anything is created. `ResultStore.__init__` mkdirs, so
    # validating after it means a rejected run still leaves a results directory
    # behind — and an empty `traces/` next to no ledger reads like a run that
    # died rather than one that never started.
    pricing = lookup(args.model)

    # The store is opened first because on a resume it, not argparse, decides
    # what this invocation is: every line below reads args that the manifest
    # may be about to correct.
    store = ResultStore(args.out)
    from .engine.experiment_sidecar import ExperimentSidecar, has_sidecar, missing_cells

    sidecar = None
    if has_sidecar(args.out):
        sidecar = ExperimentSidecar.load(args.out)
        sidecar.validate_world_lock(store)

    prior = store.manifest() if args.resume else {}
    done = store.completed() if args.resume else set()
    if args.resume:
        skip = frozenset({"presets"}) if sidecar else frozenset()
        if changed := _inherit_run_config(args, prior, skip=skip):
            print("inheriting from manifest.json — this invocation disagreed:")
            print("\n".join(changed))
        elif done and not prior:
            print(f"warning: {args.out} has {len(done)} rows but no manifest.json, "
                  f"so the resume cannot check it is reproducing the same matrix. "
                  f"Every run-shaping flag has to be passed again by hand.")
        if voided := store.voided():
            kinds = Counter(r["error_kind"] for r in voided)
            print(f"re-running {len(voided)} runs voided by infra failure "
                  f"({', '.join(f'{k}={n}' for k, n in kinds.most_common())})")

    if sidecar and not args.presets:
        args.presets = list(sidecar.active_presets())
        if not getattr(args, "_plan", None):
            args._plan = sidecar.run_plan()

    presets = tuple(args.presets or ("Z0", "A1", "A2", "C1", "D1"))
    # A sweep varies one property of the API while holding packaging fixed.
    # Each level is tagged onto the arm name so the report never averages
    # across it — that would answer the wrong question entirely.
    sweep_values = tuple(args.sweep_error_detail or ())
    # Generalised --sweep AXIS=v1,v2 (and the legacy --sweep-error-detail alias).
    sweep_axes = _parse_sweep_args(getattr(args, "sweep", None) or [],
                                   sweep_values)
    # Response-reshaping sweeps are a controlled-rig capability — a customer's
    # API cannot be re-served three ways. Refuse rather than emit identical arms.
    _FIELD_REFUSED_SWEEPS = frozenset({"error_detail", "response_shape"})
    if args.pack and _FIELD_REFUSED_SWEEPS.intersection(sweep_axes):
        bad = ", ".join(sorted(_FIELD_REFUSED_SWEEPS.intersection(sweep_axes)))
        print(f"\nrefusing --sweep {bad} on a field pack: only the controlled "
              f"rig can reshape responses. On a customer's API no axis that "
              f"reshapes responses can be swept at all.", file=sys.stderr)
        return 2

    # The one thing that differs between a controlled matrix and a field run:
    # where the calls land. Everything below this branch is identical for both,
    # which is the entire point of the target seam (engine/target.py).
    shape = shape_for_cores(args.cores, WorldShape(episodes_per_season=args.fan_out))
    watcher = _stream_watcher(args.concurrency) if args.stream else None
    if args.pack:
        pack = load_pack(args.pack, base_url=os.environ.get("TARGET_BASE_URL"),
                         allow_production_writes=args.i_know_this_is_production)
        target, revision = _field_target(args, pack)
        target.on_turn = watcher
        # Record the revision actually used. `auto` resolves by asking the
        # server, and a manifest saying "auto" would not tell a later reader
        # which protocol produced these rows — and results are never pooled
        # across revisions (V10).
        args.mcp_revision = revision.value
    else:
        pack = TaskPack.parse(build_pack(build_world(args.seed, shape),
                                         cores=args.cores, seed=args.seed,
                                         difficulty=args.difficulty))
        target = RigTarget(seed=args.seed, shape=shape,
                           surface_size=args.surface_size, on_turn=watcher)

    tasks = list(pack.tasks)
    if args.classes:
        tasks = [t for t in tasks if str(t.task_class) in args.classes]
    if args.max_tasks:
        tasks = tasks[:args.max_tasks]

    # Inheriting the parameters makes the *inputs* match. This checks the
    # output, which is the thing that actually has to be true: the digest
    # hashes prompts, so it catches drift no flag describes — a change to task
    # generation, the domain seeder or the difficulty ladder between the
    # original matrix and this resume. Those produce a world with identical
    # parameters and different questions, and the rows would be pooled anyway
    # because nothing downstream can see the difference.
    if args.resume and (stored_digest := prior.get("pack_digest")):
        if (rebuilt := _pack_digest(tasks)) != stored_digest:
            print(f"\nrefusing to resume: {args.out} was built from task pack "
                  f"{stored_digest}, this harness rebuilds {rebuilt} from the "
                  f"same parameters.\nThe task set changed underneath the run "
                  f"(generator, seeder or difficulty ladder), so finishing it "
                  f"here would put two different worlds in one ledger.\nCheck "
                  f"out the commit that started it (manifest harness_version "
                  f"{prior.get('harness_version', 'not recorded')}), or start "
                  f"a fresh matrix in a new --out.")
            return _EXIT_REFUSED

    arm_specs = _expand_arm_specs(presets, sweep_axes)
    axes = {**_base_axes(args), "surface_size": args.surface_size}

    # Layer 1 (config): resolve every arm, validate every Variant, materialize
    # once per arm — before the budget prompt. A missing authored skill used to
    # raise mid-matrix after money was spent.
    try:
        resolved_arms = _preflight_arms(arm_specs, axes, target)
    except (ConfigError, LookupError, FileNotFoundError, ValueError) as e:
        print(f"\nrefusing to start: {e}", file=sys.stderr)
        return 2

    slice_spec = (sidecar.slice_spec(getattr(args, "experiment_slice", None))
                  if sidecar else None)
    if sidecar:
        schedule = missing_cells(
            store,
            presets=sidecar.active_presets(),
            tasks=tasks,
            repeats=args.repeats,
            slice_spec=slice_spec,
        )
    else:
        schedule = None

    planned = [
        (label, arm, overrides, task, repeat)
        for label, arm, overrides in arm_specs
        for task in tasks
        for repeat in range(args.repeats)
        if (schedule is None and (label, task.id, repeat) not in done
            or schedule is not None and (label, task.id, repeat) in schedule)
        and not _skip_for_needs(resolved_arms[label], task)
    ]
    if sidecar and slice_spec:
        print(f"slice {getattr(args, 'experiment_slice', None)!r}: "
              f"{len(planned)} cells to run")
    elif done:
        print(f"resuming: {len(done)} runs already on disk, {len(planned)} to go")

    from .engine.providers import get as get_provider
    provider = get_provider(args.provider)
    rough = len(planned) * price_run(pricing, input_tokens=8_000,
                                     output_tokens=1_500).total_usd
    print(f"{len(planned)} runs — {len(presets)} arms x {len(tasks)} tasks "
          f"x {args.repeats} repeats. Rough projection ${rough:,.2f}")
    plan = getattr(args, "_plan", None)
    if plan is not None and plan.max_usd is not None and rough > plan.max_usd:
        print(f"\nrefusing to start: projection ${rough:,.2f} exceeds "
              f"budget.max_usd=${plan.max_usd:,.2f}. Cut the matrix or raise "
              f"the cap.", file=sys.stderr)
        return 2
    if (short := _disk_shortfall(store, len(planned),
                                 _disk_reserve_bytes(args))) is not None:
        need, free = short
        reserve = _disk_reserve_bytes(args)
        reserve_gb = reserve / 2**30
        print(f"\nnot enough disk: {len(planned)} runs need ~{need / 2**30:.1f} GB "
              f"of traces, {free / 2**30:.1f} GB free"
              f"{f' (plus {reserve_gb:.1f} GB reserved so the machine can still swap)' if reserve else ''}.\n"
              f"Free space or move --out to another volume, then re-run with --resume.\n"
              f"For smoke/probe only, the reserve is skipped; override with "
              f"--disk-reserve-gb.")
        return 1
    if not args.yes and not _confirm():
        print("aborted")
        return 1

    store.write_manifest(
        # A resume rewrites the manifest, and `created_at` must survive that:
        # it dates the matrix, and the rows on disk predate this invocation by
        # however long the first attempt ran.
        **({"created_at": prior["created_at"]} if "created_at" in prior else {}),
        id=args.id, model=args.model, provider=args.provider,
        presets=list(presets), cores=args.cores, repeats=args.repeats,
        seed=args.seed, surface_size=args.surface_size, fan_out=args.fan_out,
        reasoning_effort=args.reasoning_effort, difficulty=args.difficulty,
        report_class=str(pack.pack.report_class), tasks=len(tasks),
        # The real count, not arms x tasks x repeats: some cells are skipped
        # deliberately (Z1 cannot do writes), and an inferred total makes the
        # ETA wrong for the whole run.
        planned=len(planned) + len(done), resumed=len(done),
        # Everything below exists so `harness compare` can say how two runs
        # differed. A parameter that shaped the results but was never written
        # down is invisible to a comparison, and a delta quoted without it is
        # worse than no delta. `engine/comparison.PARAMETERS` reads these, and
        # a test asserts every key here has a row there.
        harness_version=__version__,
        temperature=args.temperature, caching=args.caching,
        max_turns=args.max_turns, concurrency=args.concurrency,
        schema_detail=args.schema_detail, response_shape=args.response_shape,
        error_detail=args.error_detail, doc_budget=args.doc_budget,
        mcp_revision=args.mcp_revision,
        sweep_error_detail=list(sweep_axes.get("error_detail", ())),
        classes=list(args.classes or []), max_tasks=args.max_tasks,
        pack_digest=_pack_digest(tasks),
        # Field-only: which pack and which server produced these rows. Without
        # them, two runs of the same tasks against MCP v1 and v2 look identical
        # in the parameter table and the comparison attributes real deltas to
        # nothing. Controlled runs omit the keys — absent, not None — so a rig
        # matrix reads NOT_RECORDED rather than inventing a difference.
        **(_field_manifest_fields(pack, str(args.pack)) if args.pack else {}),
        **_manifest_arm_fields(resolved_arms, args),
    )

    config = ProviderConfig(
        model=args.model, reasoning_effort=args.reasoning_effort,
        temperature=args.temperature, max_turns=args.max_turns,
        caching=args.caching == "on",
    )

    if args.preflight:
        if reason := _preflight(provider, config):
            print(f"\npreflight failed — {reason}\n"
                  f"Nothing was scheduled. Fix this, then re-run with --resume "
                  f"to keep what is already in {args.out}.")
            return _EXIT_INFRA
        print("preflight ok")

    import time as _time
    from concurrent.futures import ThreadPoolExecutor, as_completed

    started_at = _time.time()
    # Runs are independent by construction — instance-per-run isolation exists
    # precisely so they can overlap (G10). Nearly all of a run's 25s is waiting
    # on the provider, so concurrency buys close to linear speedup until the
    # rate limit bites.
    done_count = 0

    def execute(item):
        label, arm, overrides, task, repeat = item
        variant = preset(arm, **{**axes, **overrides})
        trace, grade = target.run(arm, variant, task, provider, config)
        return label, task, repeat, trace, grade

    pool = ThreadPoolExecutor(max_workers=args.concurrency)
    futures = {pool.submit(execute, item): item for item in planned}
    fatal: tuple[str, str] | None = None
    try:
        for future in as_completed(futures):
            label, arm, overrides, task, repeat = futures[future]
            done_count += 1
            kind = None
            try:
                label, task, repeat, trace, grade = future.result()
                row = build_row(arm=label, task=task, repeat=repeat,
                                trace=trace, grade=grade,
                                metrics=compute(trace),
                                report_class=str(pack.pack.report_class),
                                seed=args.seed)
                # One writer at a time on the ledger — appended per run so a
                # matrix that dies leaves what it finished, and interleaved
                # writes would corrupt exactly that guarantee. The store holds
                # that lock itself now, over the append alone, so compressing a
                # 1.7MB trace no longer blocks every other worker's row.
                store.record(row, trace)
                kind = row.error_kind
                status = "truncated" if trace.truncated else str(grade.outcome)
                detail = f"{len(trace.turns)}t"
            except Exception as e:  # noqa: BLE001 — one bad run is data
                # ...but only if it is written down. Printing and moving on
                # loses the cell entirely, and an absent row is indistinguish-
                # able from one that was never scheduled, so `--resume` cannot
                # find it either.
                kind = str(classify(e))
                status, detail = "ERROR", f"{type(e).__name__}: {str(e)[:40]}"
                try:
                    store.record(infra_row(
                        arm=label, task=task, repeat=repeat, exc=e,
                        report_class=str(pack.pack.report_class),
                        seed=args.seed, model=args.model,
                        surface_size=args.surface_size,
                    ))
                except Exception:  # noqa: BLE001 — ledger itself is gone
                    detail = f"{detail} (UNRECORDED)"
            print(f"  {_progress(done_count, len(planned), started_at)} "
                  f"{label:<12} {task.id:<26} {status:<15} {detail}",
                  # Unbuffered: redirected to a file, Python buffers stdout
                  # and the log lags minutes behind the run.
                  flush=True)
            if kind in FATAL:
                fatal = (kind, detail)
                break
    except KeyboardInterrupt:
        # cancel_futures empties the queue, but the workers already inside a
        # provider call cannot be interrupted — and both the executor's
        # __exit__ and threading's atexit hook join them, so a normal return
        # stalls for a full call and the impatient second Ctrl-C lands inside
        # t.join() as a traceback. Leaving the process outright is safe here
        # because the ledger is appended per run under the store's lock:
        # holding it means no run is halfway through a line.
        pool.shutdown(wait=False, cancel_futures=True)
        print("\ninterrupted — results so far are on disk; --resume continues.\n"
              f"summary of what finished: harness report {args.out}", flush=True)
        sys.stdout.flush()
        with store.ledger_lock:
            os._exit(130)

    if fatal:
        kind, detail = fatal
        # Same reasoning as the KeyboardInterrupt path: cancel what has not
        # started, do not join in-flight provider calls, and trust the
        # per-run append under the store's ledger lock for durability.
        pool.shutdown(wait=False, cancel_futures=True)
        print(f"\naborted: {kind} — {detail}\n"
              f"{done_count} of {len(planned)} runs done; the rest were not "
              f"attempted.\nEvery cell lost to this is marked infra-error and "
              f"will be re-run, not skipped.\nFix the cause, then: "
              f"harness run --out {args.out} --id {args.id} --resume",
              flush=True)
        sys.stdout.flush()
        with store.ledger_lock:
            os._exit(_EXIT_INFRA)

    pool.shutdown(wait=True)

    if sidecar and planned:
        import uuid
        sidecar.append_episode({
            "id": uuid.uuid4().hex[:12],
            "started_at": prior.get("created_at") or store.manifest().get("created_at"),
            "finished_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "slice": getattr(args, "experiment_slice", None),
            "arms_scheduled": list(sidecar.active_presets()),
            "planned_cells": len(planned),
            "completed_before": len(done),
            "job_id": args.id,
        })

    print()
    final = _build_report(store)
    print(render(list(store.rows()), store.manifest(), report=final))
    from .engine.stats import analyse as analyse_stats
    stats = analyse_stats(final)
    if stats.contrasts:
        print("\n  contrasts:")
        print(stats.render())
    print(f"\nresults: {args.out}/results.jsonl   traces: {args.out}/traces/")
    print(f"html:    harness report {args.out} --html {args.out}/report.html")
    return 0


def _build_report(store, *, mde_pp: float | None = None,
                  weights: dict[str, float] | None = None):
    """One analysis object for every renderer.

    The MDE is computed here and passed in: power lives in `experiment` and the
    engine must not import it (plan.md §2).
    """
    from .engine.analysis import Report
    from .engine.ops import build_ledger
    from .engine.results import TRACES

    manifest = store.manifest()
    if mde_pp is None and manifest.get("cores"):
        try:
            from .experiment.power import Contrast, analyse
            mde_pp = analyse(Contrast.MAIN_EFFECT, int(manifest["cores"]),
                             repeats=int(manifest.get("repeats", 1))).mde_pp
        except Exception:  # noqa: BLE001 — a missing MDE only drops one banner
            mde_pp = None
    rows = list(store.rows())
    ledger = None
    traces = store.root / TRACES
    if traces.is_dir() and any(traces.iterdir()):
        try:
            ledger = build_ledger(
                rows, traces,
                gold_by_task=_gold_by_task_for_report(manifest, rows),
            )
        except Exception:  # noqa: BLE001 — a missing ledger must not kill report
            ledger = None
    return Report(rows=rows, manifest=manifest, mde_pp=mde_pp,
                  weights=weights, op_ledger=ledger)


def _gold_by_task_for_report(manifest: dict, rows: list) -> dict[str, tuple[str, ...]]:
    """Rebuild gold op ids for the op ledger without changing results.jsonl.

    Controlled runs regenerate the pack from the manifest's world parameters.
    Field packs often have no gold — the ledger then marks off-gold / excess
    unavailable rather than pretending they are zero. Row-level ``gold_ops``
    (tests) still win via ``build_ledger``'s merge.
    """
    from .engine.ops import (
        augment_gold_for_controlled_tasks, gold_ops_from_sequence,
    )

    if manifest.get("seed") is None or not manifest.get("cores"):
        return {}
    try:
        from .experiment.domain import WorldShape, build_world, shape_for_cores
        from .experiment.tasks import build_pack
        from .engine.taskpack import TaskPack

        shape = shape_for_cores(
            int(manifest["cores"]),
            WorldShape(episodes_per_season=int(manifest.get("fan_out", 8))),
        )
        raw = build_pack(
            build_world(int(manifest["seed"]), shape),
            cores=int(manifest["cores"]),
            seed=int(manifest["seed"]),
            difficulty=str(manifest.get("difficulty", "standard")),
        )
        pack = TaskPack.parse(raw)
    except Exception:  # noqa: BLE001 — field dirs / old manifests
        return {}
    gold = {
        t.id: gold_ops_from_sequence(t.gold_call_sequence)
        for t in pack.tasks
        if t.gold_call_sequence
    }
    # Navigation gold alone marks every required write as off-path; augment.
    return augment_gold_for_controlled_tasks(gold)


def cmd_doctor(args: argparse.Namespace) -> int:
    """What is installed, what is missing, and what that stops you doing."""
    from .doctor import MISSING, render, run

    checks = run()
    print(render(checks))
    return 1 if any(c.status == MISSING for c in checks) else 0


def cmd_scaffold(args: argparse.Namespace) -> int:
    """Draft a task pack from a live surface or an OpenAPI document."""
    from .engine.generate import spec_from_tools
    from .scaffold import build, to_yaml

    source = str(args.source)
    mcp_url = openapi = None

    if source.startswith(("http://", "https://")) and args.mcp:
        from .engine.axes import McpRevision
        from .engine.mcp import McpClient, detect_revision
        from .engine.mcp.transport import HttpTransport, probe_server

        revision = detect_revision(probe_server(source))
        client = McpClient(HttpTransport.from_env(source), revision)
        client.connect()
        spec = spec_from_tools(client.list_tools().tools, title=args.id)
        mcp_url = source
        print(f"{source}: {revision.value}, {len(spec.operations)} tools")
    else:
        spec = load_spec(source)
        openapi = source
        print(f"{source}: {len(spec.operations)} operations")

    pack = build(spec, pack_id=args.id, mcp_url=mcp_url, openapi=openapi)
    text = to_yaml(pack)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text)
        stubs = sum(1 for t in pack["tasks"] if not t["grade"])
        print(f"wrote {args.out}  ({len(pack['tasks'])} tasks, {stubs} to fill in)")
        if pack["safety"]["forbidden_calls"]:
            print("  forbidden_calls: "
                  + ", ".join(pack["safety"]["forbidden_calls"]))
        writes = len(spec.operations) - len(pack["tasks"]) + sum(
            1 for x in pack["tasks"] if not x["answerable"])
        if writes > 0:
            print(f"  {writes} write operations skipped — reads only, so the "
                  f"pack is safe to run as generated")
        print("  nothing is graded yet — fill the TODOs before believing a number")
    else:
        print(text)
    return 0


def cmd_generate_analyze(args: argparse.Namespace) -> int:
    from .generate_run import run_analyze

    payload = run_analyze(args.spec, args.out, job_id=args.job_id)
    print(f"{payload['spec_title']} v{payload['spec_version']} — "
          f"{payload['operation_count']} operations, "
          f"{len(payload['findings'])} findings")
    print(f"wrote {args.out}/analyze.json")
    return 0


def cmd_generate_materials(args: argparse.Namespace) -> int:
    from .engine.axes import DocBudget
    from .generate_run import run_materials
    from .generate_workspace import init_workspace, read_status

    workspace = args.out.resolve()
    if read_status(workspace) is None:
        init_workspace(workspace, args.job_id or workspace.name)

    summary = run_materials(
        args.spec,
        workspace,
        doc_budget=DocBudget(args.doc_budget),
        presets=tuple(args.presets or ()),
    )
    print(f"wrote {workspace / 'materials'}  "
          f"({summary['tool_count']} tools, arms: {', '.join(summary['arms_probe'])})")
    return 0


def cmd_generate_run(args: argparse.Namespace) -> int:
    from .generate_config import GenerateConfig
    from .generate_run import run_pipeline
    from .generate_workspace import GenerateError

    config = GenerateConfig.load(args.config)
    if not args.yes:
        print(f"generate {config.job_id}: analyze={config.run_analyze} "
              f"enrich={config.enrich is not None} "
              f"materials={config.run_materials} fixtures={config.run_fixtures} "
              f"pack={config.run_pack}")
        print(f"  workspace: {config.workspace}")
        print(f"  spec:      {config.spec}")
        if config.enrich and config.enrich.use_llm:
            from .enrich import estimate_enrich_cost
            from .engine.generate import load_spec
            est = estimate_enrich_cost(load_spec(config.spec), config.enrich)
            print(f"  enrich LLM: ~${est.estimated_usd:.4f} on {est.model} "
                  f"(cap ${est.max_usd:.2f})")
        if config.run_fixtures:
            print(f"  staging:   ${config.base_url_env}")
        if not config.mcp_gateway:
            print("  note: mcp_gateway=false → A/B arms gated for field HTTP")
        print("\nRe-run with --yes to execute.")
        return 1

    try:
        manifest = run_pipeline(config, yes=True)
    except GenerateError as e:
        print(e.message)
        return e.exit_code
    print(f"complete: {config.workspace / 'manifest.json'}")
    print(f"  arms: {', '.join(manifest.get('arms_probe') or [])}")
    if manifest.get("pack_id"):
        print(f"  pack: {manifest.get('pack_id')} ({manifest.get('graded_tasks')} graded)")
    return 0


def cmd_generate_enrich(args: argparse.Namespace) -> int:
    from .bundle import copy_spec_source
    from .enrich import EnrichPlan, estimate_enrich_cost, parse_enrich_phase, run_enrich
    from .engine.generate import load_spec
    from .generate_config import GenerateConfig
    from .generate_workspace import (
        GenerateError,
        init_workspace,
        read_status,
        spec_path_in_workspace,
        workspace_root,
    )

    if getattr(args, "config", None):
        config = GenerateConfig.load(args.config)
        workspace = config.workspace
        plan = config.enrich or EnrichPlan(model=None, max_usd=0.0, use_llm=False)
        if read_status(workspace) is None:
            init_workspace(workspace, config.job_id)
        dest = spec_path_in_workspace(workspace)
        if not dest.is_file():
            copy_spec_source(config.spec, dest)
    else:
        workspace = workspace_root(args.out)
        plan = parse_enrich_phase(
            {"model": args.model, "max_usd": args.max_usd} if args.model else True
        )
        if plan is None:
            plan = EnrichPlan(model=None, max_usd=0.0, use_llm=False)
        init_workspace(workspace, args.job_id or workspace.name)
        dest = spec_path_in_workspace(workspace)
        if not dest.is_file():
            if not args.spec:
                print("spec or --config required")
                return 2
            copy_spec_source(args.spec, dest)

    if plan.use_llm and not args.yes:
        est = estimate_enrich_cost(load_spec(dest), plan)
        print(f"enrich LLM ~${est.estimated_usd:.4f} on {est.model} "
              f"(cap ${est.max_usd:.2f})")
        print("Re-run with --yes to spend.")
        return 1

    try:
        summary = run_enrich(workspace, plan=plan, yes=args.yes)
    except GenerateError as e:
        print(e.message)
        return e.exit_code
    print(f"enriched → {workspace / summary['enriched_spec']}")
    print(f"  patched: {summary['operations_patched']}  llm={summary['llm_used']}")
    print(f"  skill:   {workspace / summary['authored_skill']}")
    print(f"  gaps:    {workspace / summary['doc_gaps']}")
    return 0


def cmd_generate_fixtures(args: argparse.Namespace) -> int:
    from .generate_config import GenerateConfig
    from .generate_fixtures import run_fixtures_from_config
    from .generate_workspace import init_workspace, read_status

    config = GenerateConfig.load(args.config)
    if read_status(config.workspace) is None:
        init_workspace(config.workspace, config.job_id)
    if not args.yes:
        print(f"fixtures for {config.job_id} need ${config.base_url_env} and --yes")
        return 1
    result = run_fixtures_from_config(config)
    print(f"captured {result.success_count} fixtures → {config.workspace / 'examples'}")
    return 0


def cmd_generate_pack(args: argparse.Namespace) -> int:
    from .generate_config import GenerateConfig
    from .generate_pack import run_pack
    from .generate_workspace import GenerateError, init_workspace, read_status

    config = GenerateConfig.load(args.config)
    if read_status(config.workspace) is None:
        init_workspace(config.workspace, config.job_id)
    if not args.yes:
        print(f"pack for {config.job_id}: min_graded_tasks={config.min_graded_tasks}")
        print("Re-run with --yes")
        return 1
    try:
        summary = run_pack(config.workspace, config)
    except GenerateError as e:
        print(e.message)
        return e.exit_code
    print(f"wrote {config.workspace / summary['pack_path']} "
          f"({summary['graded_tasks']} graded)")
    return 0


def cmd_mock_serve(args: argparse.Namespace) -> int:
    """Local HTTP stub + MCP gateway for From-OpenAPI when no staging URL."""
    from .mock_serve import serve_pair

    serve_pair(
        str(args.spec),
        host=args.host,
        http_port=args.http_port,
        mcp_port=args.mcp_port,
    )
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    """Install the agent skills into this project.

    The skills are the interface for most users: they are what lets somebody's
    own coding agent drive lint/scaffold/run without them reading a manual.
    Shipping them inside the wheel is what makes that true for someone who
    installed from a release and never cloned anything.
    """
    import shutil
    from importlib import resources

    targets = {"claude": ".claude/skills", "cursor": ".cursor/skills"}
    chosen = list(targets) if args.agent == "both" else [args.agent]

    source = resources.files("harness") / "agent_skills"
    # Count distinct skills, not writes: `--agent both` copies each one twice,
    # and "6 skills installed" when there are three reads as a different product.
    written: set[str] = set()
    for agent in chosen:
        root = args.dir / targets[agent]
        root.mkdir(parents=True, exist_ok=True)
        for skill in source.iterdir():
            if not skill.is_dir():
                continue
            destination = root / skill.name
            if destination.exists() and not args.force:
                print(f"  skip {destination} (exists — --force to overwrite)")
                continue
            shutil.copytree(str(skill), destination, dirs_exist_ok=True)
            print(f"  wrote {destination}")
            written.add(skill.name)

    template = args.dir / "packs" / "template.yaml"
    if not template.exists() or args.force:
        template.parent.mkdir(parents=True, exist_ok=True)
        template.write_text(_PACK_TEMPLATE)
        print(f"  wrote {template}")

    print(f"\n{len(written)} skill(s) installed: {', '.join(sorted(written))}")
    print('Ask your agent: "help me test my API with harness".')
    return 0


#: A hand-written starting point, kept separate from `harness scaffold` output:
#: scaffold derives a pack from a surface you already have, this one is for
#: somebody who wants to see the shape before pointing it at anything.
_PACK_TEMPLATE = """\
# A harness task pack. See docs/design-your-test-run.md for every field.
schema_version: 1

pack:
  id: my-api
  description: What this target is, and what these tasks are meant to prove.
  # `field` for any real API: contamination is uncontrolled, so every number
  # is reported as lift over Z0. Never `controlled` outside the rig.
  report_class: field

api:
  # One of these two. `spec_revision: auto` asks the server which it speaks.
  # mcp: { url: https://example.com/mcp, spec_revision: auto }
  # openapi: ./openapi.json
  base_url_env: TARGET_BASE_URL
  auth: { type: none }          # none | bearer | header | basic
  # auth: { type: bearer, env: MY_API_TOKEN }

safety:
  writes_enabled: false         # keep false until you have a staging target
  forbidden_calls: []           # every destructive operation; this IS the harm signal

isolation:
  mode: none                    # reads only. Writes need instance-per-run.

tasks:
  # Aim for >=20 distinct cores to rank arms, ~40 for serious contrasts.
  # Answers should live in YOUR system — a question the model can answer from
  # public knowledge measures pretraining, not packaging.
  - id: find-something-1
    prompt: A question only answerable by calling this API.
    core_id: find-something
    class: R                    # R | W-safe | W-fan
    answerable: true
    harm_tier: 0
    grade:
      - { type: contains, target: answer, value: "the expected substring" }
    gold_call_sequence:
      - { tool: the_operation_id }

  # ~15% of tasks should have no valid answer. Without these a pack cannot
  # measure fabrication, which is half of what goes wrong on a real API.
  - id: no-such-thing-1
    prompt: Ask for something this API genuinely cannot supply.
    core_id: no-such-thing
    class: R
    answerable: false
    unanswerable_because: Why no call sequence can answer it.
    harm_tier: 0
"""


def cmd_transcript(args: argparse.Namespace) -> int:
    """Replay one stored run: every message, every call, every result."""
    from .engine.transcript import load, render_stored

    style = "showcase" if args.pretty else "plain"
    verbose = bool(getattr(args, "verbose", False))
    paths = (sorted(args.trace.glob("*.json*")) if args.trace.is_dir()
             else [args.trace])
    if not paths:
        print(f"no traces in {args.trace}")
        return 1
    for path in paths[:args.limit]:
        print(render_stored(load(str(path)), style=style, verbose=verbose))
        print()
    if len(paths) > args.limit:
        print(f"({len(paths) - args.limit} more — raise --limit, or name one file)")
    return 0


def cmd_progress(args: argparse.Namespace) -> int:
    """Check a run in flight, from a second terminal, without disturbing it."""
    from .engine.progress import read

    progress = read(args.results)
    if not progress.done:
        print(f"no runs recorded yet in {args.results}")
        return 1
    print(progress.render())
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    """Render results written by a previous run. Re-runs nothing."""
    from .engine.reporting import render
    from .engine.results import ResultStore

    store = ResultStore(args.results)
    rows = list(store.rows())
    if not rows:
        print(f"no results in {args.results}")
        return 1

    weights = None
    if args.weights:
        from .engine.winner import WeightError, parse_weights
        try:
            weights = parse_weights(args.weights)
        except WeightError as e:
            print(f"--weights: {e}")
            return 2

    report = _build_report(store, weights=weights)

    if args.html or args.charts:
        from .engine.html import build_charts, standalone_html
        if args.html:
            out = Path(args.html)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(standalone_html(report, args.sort), encoding="utf-8")
            print(f"wrote {out}")
        if args.charts:
            charts_dir = Path(args.charts)
            charts_dir.mkdir(parents=True, exist_ok=True)
            for name, svg in build_charts(report).items():
                (charts_dir / f"{name}.svg").write_text(svg, encoding="utf-8")
            print(f"wrote {len(build_charts(report))} charts to {charts_dir}/")
        if not args.csv:
            return 0

    if args.csv:
        import csv
        import sys as _sys
        flat = [{k: v for k, v in r.items() if k != "metrics"} for r in rows]
        writer = csv.DictWriter(_sys.stdout, fieldnames=list(flat[0]))
        writer.writeheader()
        writer.writerows(flat)
        return 0

    print(render(rows, store.manifest(), report=report,
                 glossary=args.glossary, sort=args.sort))
    from .engine.stats import analyse as analyse_stats
    stats = analyse_stats(report)
    if stats.contrasts:
        print("\n  contrasts:")
        print(stats.render())
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    """Deep-dive tables over a finished results directory. Re-runs nothing."""
    from .deep_analysis import main as analyze_main

    argv = [str(args.results)]
    if args.csv:
        argv.extend(["--csv", str(args.csv)])
    if args.json is not None:
        argv.extend(["--json", args.json])
    if args.only:
        argv.extend(["--only", args.only])
    if args.quiet:
        argv.append("--quiet")
    if args.sort:
        argv.extend(["--sort", args.sort])
    if args.desc:
        argv.append("--desc")
    if args.list_columns:
        argv.append("--list-columns")
    return analyze_main(argv)


def cmd_compare(args: argparse.Namespace) -> int:
    """Compare N runs: what differed in the setup, and what it changed.

    The first directory is the reference; every delta is measured against it.
    Exit 3 when a pooling boundary is broken — the stop banner is visible to a
    human and invisible to a script, so `harness compare a b && publish` must
    refuse unless `--allow-cross-world` is set.
    """
    from .engine.comparison import Comparison, ComparisonError, RunRef, label_runs
    from .engine.comparison_text import DEFAULT_KEYS, render as render_text
    from .engine.results import LEDGER, ResultStore

    paths = [Path(p) for p in args.results]
    if len(paths) < 2:
        print("compare needs at least two results directories")
        return 2
    if len(paths) > Comparison.MAX_RUNS:
        print(f"{len(paths)} runs, but the chart palette has "
              f"{Comparison.MAX_RUNS} slots and never cycles")
        return 2

    # ResultStore.__init__ mkdirs. A typo'd path would silently create an empty
    # results directory — check the ledger exists first.
    for path in paths:
        if not (path / LEDGER).is_file():
            print(f"no {LEDGER} in {path}")
            return 1

    labels = args.label or None
    if labels is not None and len(labels) != len(paths):
        print(f"--label: got {len(labels)} labels for {len(paths)} runs")
        return 2

    weights = None
    if args.weights:
        from .engine.winner import WeightError, parse_weights
        try:
            weights = parse_weights(args.weights)
        except WeightError as e:
            print(f"--weights: {e}")
            return 2

    stores = [ResultStore(p) for p in paths]
    entries = [(str(p), s.manifest()) for p, s in zip(paths, stores)]
    try:
        run_labels = label_runs(entries, labels)
    except Exception as e:  # noqa: BLE001 — label collisions are user errors
        print(f"labels: {e}")
        return 2

    runs = [
        RunRef(label=label, path=str(path),
               report=_build_report(store, weights=weights))
        for label, path, store in zip(run_labels, paths, stores)
    ]
    try:
        comparison = Comparison(runs=runs, weights=weights)
    except ComparisonError as e:
        print(str(e))
        return 2

    keys = tuple(args.keys) if args.keys else DEFAULT_KEYS
    wrote_artifact = False

    if args.html or args.charts:
        from .engine.comparison_html import build_charts, standalone_html
        if args.html:
            out = Path(args.html)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(
                standalone_html(comparison, sort=args.sort, keys=keys),
                encoding="utf-8")
            print(f"wrote {out}")
            wrote_artifact = True
        if args.charts:
            charts_dir = Path(args.charts)
            charts_dir.mkdir(parents=True, exist_ok=True)
            charts = build_charts(comparison)
            for name, svg in charts.items():
                (charts_dir / f"{name}.svg").write_text(svg, encoding="utf-8")
            print(f"wrote {len(charts)} charts to {charts_dir}/")
            wrote_artifact = True

    if args.csv:
        from .engine.comparison_csv import write as write_csv
        written = write_csv(comparison, Path(args.csv))
        print(f"wrote {', '.join(p.name for p in written)} to {args.csv}/")
        wrote_artifact = True

    # Text is the default. Artifacts alone suppress it (same as `report`);
    # `--glossary` / `--all-params` are text-only flags and force it back on.
    if not wrote_artifact or args.glossary or args.all_params:
        print(render_text(comparison, sort=args.sort, keys=keys,
                          glossary=args.glossary, all_params=args.all_params))

    if comparison.pooling_refused and not args.allow_cross_world:
        return 3
    return 0


def _manifest_arm_fields(resolved_arms: dict[str, Any],
                         args: argparse.Namespace) -> dict[str, Any]:
    """Per-arm definition table + digests for ``harness compare``.

    Once arms are user-definable, ``A1`` in one run may not be ``A1`` in
    another. Hashing axes (and later materials) is what makes that visible
    instead of a silent wrong comparison.
    """
    import hashlib

    from .engine.axes import arm_materials, axis_summary, split_label

    arms_table: dict[str, Any] = {}
    for label, (variant, method) in resolved_arms.items():
        base, sweep = split_label(label)
        entry = axis_summary(variant)
        entry.update({
            "preset": base,
            "method": method.name,
            "sweep": sweep,
            "materials": arm_materials(label) or arm_materials(variant.preset),
            "family": getattr(args, "family", None),
        })
        arms_table[label] = entry
    digest_src = json.dumps(arms_table, sort_keys=True, default=str).encode()
    fields: dict[str, Any] = {
        "arms": arms_table,
        "arms_digest": hashlib.sha256(digest_src).hexdigest()[:16],
        "excluded_arms": {},
    }
    if getattr(args, "plan", None):
        plan_path = str(args.plan)
        fields["plan_path"] = plan_path
        fields["plan_id"] = getattr(args, "plan_id", None)
        try:
            payload = Path(plan_path).read_bytes()
            fields["plan_digest"] = hashlib.sha256(payload).hexdigest()[:16]
        except OSError:
            fields["plan_digest"] = None
    return fields


def _parse_sweep_args(sweep_flags: list[str],
                      legacy_error_detail: tuple[str, ...]) -> dict[str, tuple]:
    """Merge ``--sweep AXIS=v1,v2`` flags and the legacy error_detail alias."""
    from .engine.axes import axis_by_name, coerce_axis_value

    out: dict[str, tuple] = {}
    if legacy_error_detail:
        out["error_detail"] = tuple(legacy_error_detail)
    for flag in sweep_flags:
        if "=" not in flag:
            raise ConfigError(
                f"--sweep {flag!r}: expected AXIS=v1,v2"
            )
        axis, _, values = flag.partition("=")
        axis = axis.strip()
        if axis_by_name(axis) is None:
            raise ConfigError(f"--sweep: unknown axis {axis!r}")
        levels = tuple(v.strip() for v in values.split(",") if v.strip())
        # Validate by coercing.
        for level in levels:
            coerce_axis_value(axis, level)
        out[axis] = levels
    return out


def _expand_arm_specs(presets: tuple[str, ...],
                      sweep_axes: dict[str, tuple]) -> list[tuple]:
    """Cartesian product of presets × sweep levels → (label, base, overrides)."""
    import itertools

    from .engine.axes import coerce_axis_value, format_label

    if not sweep_axes:
        return [(a, a, {}) for a in presets]
    axes = list(sweep_axes)
    levels = [sweep_axes[a] for a in axes]
    specs = []
    for arm in presets:
        for combo in itertools.product(*levels):
            overrides = {
                axis: coerce_axis_value(axis, value)
                for axis, value in zip(axes, combo)
            }
            label = format_label(
                arm,
                {axis: str(getattr(v, "value", v)) for axis, v in overrides.items()},
                axis_order=tuple(axes),
            )
            specs.append((label, arm, overrides))
    return specs


def _preflight_arms(arm_specs, axes: dict, target) -> dict[str, Any]:
    """Resolve every arm and materialize once before the budget prompt.

    Layer 1 of the infra taxonomy: config errors refuse to start. A missing
    authored skill, an unknown preset, or an ambiguous ``supports()`` must not
    surface mid-matrix after money is spent.
    """
    register_defaults()
    resolved: dict[str, Any] = {}
    for label, arm, overrides in arm_specs:
        variant = preset(arm, **{**axes, **overrides})
        method = resolve(variant)
        method.materialize(target.spec, variant)
        resolved[label] = (variant, method)
    return resolved


def _skip_for_needs(resolved_entry, task) -> bool:
    """Drop cells a method cannot grade, derived from ``needs`` not arm name.

    Prefetch methods (Z1) only run on tasks that carry a gold call sequence —
    writes never do, and spending on a guaranteed 0% would drag the ceiling.
    """
    _variant, method = resolved_entry
    if "prefetch" in method.needs and not getattr(task, "gold_call_sequence", None):
        return True
    return False


def _experiment_run_namespace(sidecar, store, *, slice_id, yes, concurrency,
                              disk_reserve_gb=None):
    """Build a ``run`` namespace from an experiment sidecar."""
    ns = argparse.Namespace(
        command="run",
        func=cmd_run,
        out=str(sidecar.root),
        id=sidecar.id,
        plan=None,
        presets=list(sidecar.active_presets()),
        cores=3,
        fan_out=8,
        classes=None,
        max_tasks=None,
        max_turns=12,
        seed=1,
        sweep_error_detail=None,
        sweep=[],
        difficulty="standard",
        concurrency=concurrency,
        resume=bool(store.manifest() or any(True for _ in store.raw_rows())),
        yes=yes,
        preflight=True,
        smoke=False,
        stream=False,
        pack=None,
        spec=None,
        probe=False,
        disk_reserve_gb=disk_reserve_gb,
        i_know_this_is_production=False,
        provider="openai",
        model="gpt-5.6-luna",
        reasoning_effort="low",
        temperature=0.0,
        caching="off",
        repeats=1,
        surface_size=0,
        schema_detail="standard",
        response_shape="as-is",
        error_detail="field-scoped",
        doc_budget="standard",
        mcp_revision="2026-07-28",
        experiment_slice=slice_id,
    )
    _apply_run_plan_to_args(ns, sidecar.run_plan())
    ns._plan = sidecar.run_plan()
    return ns


def cmd_experiment_init(args: argparse.Namespace) -> int:
    from .engine.experiment_sidecar import ExperimentSidecar

    out = Path(args.out)
    sidecar = ExperimentSidecar.init_from_plan(Path(args.plan), out)
    print(f"experiment sidecar: {out / 'experiment.yaml'}")
    print(f"  id: {sidecar.id}")
    print(f"  arms: {', '.join(sidecar.active_presets())}")
    print(f"  next: harness experiment run {out}")
    return 0


def cmd_experiment_show(args: argparse.Namespace) -> int:
    from .engine.experiment_sidecar import ExperimentSidecar, sidecar_envelope
    from .engine.results import ResultStore
    from .study import resolve_tasks

    sidecar = ExperimentSidecar.load(args.dir)
    store = ResultStore(args.dir)
    tasks = resolve_tasks(sidecar.run_plan(), manifest=store.manifest() or None)
    payload = sidecar_envelope(sidecar, store, tasks=tasks,
                               slice_id=getattr(args, "slice", None))
    print(json.dumps(payload, indent=2, default=str))
    return 0


def cmd_experiment_arm_add(args: argparse.Namespace) -> int:
    from .engine.experiment_sidecar import ExperimentSidecar

    sidecar = ExperimentSidecar.load(args.dir)
    added = sidecar.add_presets(args.presets)
    if not added:
        print("no new arms added")
    else:
        print(f"added: {', '.join(added)}")
        print(f"  active arms: {', '.join(sidecar.active_presets())}")
    return 0


def cmd_experiment_status(args: argparse.Namespace) -> int:
    from .engine.experiment_sidecar import ExperimentSidecar, coverage_summary
    from .engine.results import ResultStore
    from .study import resolve_tasks

    sidecar = ExperimentSidecar.load(args.dir)
    store = ResultStore(args.dir)
    sidecar.validate_world_lock(store)
    plan = sidecar.run_plan()
    tasks = resolve_tasks(plan, manifest=store.manifest() or None)
    cov = coverage_summary(
        store,
        presets=sidecar.active_presets(),
        tasks=tasks,
        repeats=int(plan.base.get("repeats", 1)),
        slice_spec=sidecar.slice_spec(getattr(args, "slice", None)),
    )
    print(f"experiment {sidecar.id}  status={sidecar.status}")
    print(f"  declared:  {cov['declared_cells']} cells")
    print(f"  completed: {cov['completed_cells']}")
    print(f"  missing:   {cov['missing_cells']}")
    print(f"  voided:    {cov['voided_cells']}")
    if cov["complete_fraction"] is not None:
        print(f"  coverage:  {cov['complete_fraction']:.1%}")
    incomplete = {k: v for k, v in cov["by_arm"].items() if v["missing"]}
    if incomplete:
        print("  incomplete arms:")
        for arm, stats in sorted(incomplete.items()):
            print(f"    {arm}: {stats['done']}/{stats['expected']}")
    return 0


def cmd_experiment_run(args: argparse.Namespace) -> int:
    from .engine.experiment_sidecar import ExperimentSidecar
    from .engine.results import ResultStore

    sidecar = ExperimentSidecar.load(args.dir)
    store = ResultStore(args.dir)
    run_ns = _experiment_run_namespace(
        sidecar, store,
        slice_id=args.slice,
        yes=args.yes,
        concurrency=args.concurrency,
        disk_reserve_gb=getattr(args, "disk_reserve_gb", None),
    )
    return cmd_run(run_ns)


def cmd_experiment_snapshot(args: argparse.Namespace) -> int:
    from .engine.experiment_sidecar import REPORTS_DIR, ExperimentSidecar
    from .engine.results import ResultStore
    from .engine.reporting import render

    sidecar = ExperimentSidecar.load(args.dir)
    store = ResultStore(args.dir)
    rows = list(store.rows())
    manifest = store.manifest()
    report = _build_report(store)
    report_json = {
        "at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": sidecar.status,
        "ledger_rows": sum(1 for _ in store.raw_rows()),
        "text": render(rows, manifest, report=report),
    }
    reports = sidecar.root / REPORTS_DIR
    reports.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S")
    name = f"{stamp}-{sidecar.status}.json"
    path = reports / name
    path.write_text(json.dumps(report_json, indent=2, default=str))
    sidecar.append_report_snapshot({
        "at": report_json["at"],
        "status": sidecar.status,
        "path": f"{REPORTS_DIR}/{name}",
        "ledger_rows": report_json["ledger_rows"],
    })
    print(f"snapshot: {path}")
    return 0


def _progress(done: int, total: int, started_at: float) -> str:
    """`[ 42/270  16%  eta 21m]` — position, share, and time remaining.

    ETA from observed pace rather than a fixed estimate, because run duration
    varies several-fold by arm: a shell arm shelling out to curl is nothing like
    a single tool call.
    """
    import time
    elapsed = time.time() - started_at
    rate = elapsed / done if done else 0.0
    remaining = rate * (total - done)
    if remaining >= 3600:
        eta = f"{remaining / 3600:.1f}h"
    elif remaining >= 60:
        eta = f"{remaining / 60:.0f}m"
    else:
        eta = f"{remaining:.0f}s"
    return f"[{done:>4}/{total}  {done * 100 // total:>3}%  eta {eta:>4}]"


def _confirm() -> bool:
    if not sys.stdin.isatty():
        # A bare "aborted" in CI logs looks like the run decided against itself.
        print("not a TTY — pass --yes to run unattended", file=sys.stderr)
        return False
    return input("proceed? [y/N] ").strip().lower() in ("y", "yes")


# ---- wiring --------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="harness", description=__doc__)
    p.add_argument("--version", action="version",
                   version=f"harness-lab {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    lint_p = sub.add_parser("lint", help="T1: static agent-readiness scorecard")
    lint_p.add_argument("--demo", action="store_true",
                        help="lint the built-in demo API — free, no key, no file")
    lint_p.add_argument("spec", nargs="?", metavar="SPEC",
                        help="OpenAPI file or http(s) URL", type=Path)
    lint_p.set_defaults(func=cmd_lint)


    rig_p = sub.add_parser("rig",
                            help="inspect/size the controlled rig "
                                 "(not a prerequisite for run)")
    rig_p.add_argument("--out", default="rig", help="output directory")
    rig_p.add_argument("--cores", type=int, default=40,
                       help="navigation cores; each yields 5 matched tasks. "
                            "Drives statistical power — see --for-contrast")
    rig_p.add_argument("--repeats", type=int, default=3,
                       help="repeats per task. Reduce measurement noise only; "
                            "they cannot substitute for cores")
    rig_p.add_argument("--for-contrast", choices=["main-effect", "within-class",
                                                  "interaction"],
                       help="size the rig for this comparison instead of --cores")
    rig_p.add_argument("--target-mde", type=float,
                       help="percentage points to detect, with --for-contrast")
    rig_p.add_argument("--seed", type=int, default=1)
    rig_p.add_argument("--surface-size", type=int, default=0,
                       help="pad with distractor operations; 0 = core only")
    rig_p.add_argument("--fan-out", type=int, default=12,
                       help="episodes per season; the blast radius on RW-fan tasks")
    rig_p.set_defaults(func=cmd_rig)

    run_p = sub.add_parser("run", help="run the controlled rig; persists everything")
    run_p.add_argument("--out", default="results", help="results directory")
    run_p.add_argument("--id", default="phase-0", help="label for this matrix")
    run_p.add_argument("--plan", type=Path,
                       help="run plan YAML; flags override the plan, plan "
                            "overrides defaults. Not required — today's flags "
                            "are an implicit plan")
    run_p.add_argument("--presets", nargs="*",
                       help="arms to run (default: Z0 A1 A2 C1 D1)")
    run_p.add_argument("--cores", type=int, default=3)
    run_p.add_argument("--fan-out", type=int, default=8)
    run_p.add_argument("--classes", nargs="*",
                       help="limit to task classes, e.g. R W-safe")
    run_p.add_argument("--max-tasks", type=int, help="cap tasks, for a smoke run")
    run_p.add_argument("--max-turns", type=int, default=12)
    run_p.add_argument("--seed", type=int, default=1)
    run_p.add_argument("--sweep-error-detail", nargs="*",
                       choices=[e.value for e in ErrorDetail],
                       help="alias for --sweep error_detail=v1,v2,… "
                            "(deprecated name; kept for existing scripts)")
    run_p.add_argument("--sweep", action="append", default=[],
                       metavar="AXIS=v1,v2",
                       help="cartesian sweep over an axis "
                            "(repeatable). Example: --sweep error_detail=terse,"
                            "field-scoped")
    run_p.add_argument("--difficulty", default="standard",
                       choices=["standard", "hard"],
                       help="'standard' ceilinged at ~100%% for every arm; "
                            "'hard' makes the agent search rather than navigate")
    run_p.add_argument("--concurrency", type=int, default=16,
                       help="runs in flight at once. Nearly all of a run is "
                            "provider latency, so this is close to a linear "
                            "speedup until rate limits bite")
    run_p.add_argument("--resume", action="store_true",
                       help="skip runs already in the results directory")
    run_p.add_argument("--yes", action="store_true", help="skip the spend prompt")
    run_p.add_argument("--disk-reserve-gb", type=float, default=None, metavar="GB",
                       help="swap headroom required before starting (default 5 for "
                            "full matrices; 0 for --smoke, --probe, and experiment "
                            "smoke slices)")
    run_p.add_argument("--no-preflight", dest="preflight", action="store_false",
                       help="skip the one-completion check that the key and "
                            "model work before scheduling the matrix")
    run_p.add_argument("--smoke", action="store_true",
                       help="~12 runs, ~1 min, ~$0.05: proves the pipeline works")
    run_p.add_argument("--stream", action="store_true",
                       help="print each turn live in a readable showcase "
                            "layout (unwrap MCP payloads, highlight answers). "
                            "Pair with --concurrency 1 to keep runs in order")
    run_p.add_argument("--pack", type=Path,
                       help="run against a live target described by this task "
                            "pack instead of the controlled rig")
    run_p.add_argument("--spec", type=Path,
                       help="OpenAPI for a --pack target; omit to derive the "
                            "surface from the server's own tools/list")
    run_p.add_argument("--probe", action="store_true",
                       help="first contact: probe arms, one repeat, no resume")
    run_p.add_argument("--i-know-this-is-production", action="store_true",
                       help="required for a pack whose writes touch production")
    run_p.set_defaults(func=cmd_run)

    progress_p = sub.add_parser("progress", help="how far along is a run")
    progress_p.add_argument("results", nargs="?", default="results")
    progress_p.set_defaults(func=cmd_progress)

    report_p = sub.add_parser("report", help="render stored results; re-runs nothing")
    report_p.add_argument("results", nargs="?", default="results")
    report_p.add_argument("--glossary", action="store_true",
                          help="explain every term in the report")
    report_p.add_argument("--csv", action="store_true",
                          help="dump rows as CSV for your own analysis")
    report_p.add_argument("--html", metavar="PATH",
                          help="write a self-contained HTML report")
    report_p.add_argument("--charts", metavar="DIR",
                          help="write each chart as a standalone .svg")
    report_p.add_argument("--sort", default="score", choices=sorted(_RANK_KEYS),
                          help="rank arms by this dimension (default: score)")
    report_p.add_argument("--weights", metavar="SPEC",
                          help="composite weights, e.g. "
                               "'success=.35,abstention=.15,harm=.25,cost=.15,"
                               "time=.10'. Unnamed dimensions are dropped, not "
                               "defaulted")
    report_p.set_defaults(func=cmd_report)

    analyze_p = sub.add_parser(
        "analyze",
        help="deep-dive tables over a finished results directory (free)",
    )
    analyze_p.add_argument("results", nargs="?", default="results",
                           help="results directory (default: results)")
    analyze_p.add_argument("--csv", type=Path, metavar="DIR",
                           help="write one CSV per section")
    analyze_p.add_argument("--json", metavar="PATH",
                           help="write JSON envelope (use - for stdout)")
    analyze_p.add_argument("--only", metavar="KEYS",
                           help="comma-separated section keys")
    analyze_p.add_argument("--quiet", action="store_true",
                           help="suppress console tables")
    analyze_p.add_argument("--sort", metavar="COLUMN",
                           help="sort the wide per-arm table by this column")
    analyze_p.add_argument("--desc", action="store_true",
                           help="sort descending")
    analyze_p.add_argument("--list-columns", action="store_true",
                           help="print sortable column names and exit")
    analyze_p.set_defaults(func=cmd_analyze)

    cmp_p = sub.add_parser(
        "compare",
        help="compare N runs: what differed in the setup, and what it changed")
    cmp_p.add_argument(
        "results", nargs="+",
        help="results directories. The FIRST is the reference; every delta is "
             "measured against it")
    cmp_p.add_argument("--label", action="append", metavar="NAME",
                       help="display name for a run, in the same order as the "
                            "directories. Repeat once per directory")
    cmp_p.add_argument("--keys", nargs="*", default=["success", "lift", "score"],
                       choices=sorted(_RANK_KEYS),
                       help="head-to-head dimensions (default: success lift "
                            "score). SCORE is suppressed when the runs have "
                            "different arm sets")
    cmp_p.add_argument("--sort", default="score", choices=sorted(_RANK_KEYS),
                       help="order arms by the REFERENCE run's ranking on "
                            "this dimension")
    cmp_p.add_argument("--weights", metavar="SPEC",
                       help="composite weights, same as `report --weights`")
    cmp_p.add_argument("--glossary", action="store_true",
                       help="explain every term in the text report")
    cmp_p.add_argument("--all-params", action="store_true",
                       help="print the full parameter table, not only what "
                            "differs")
    cmp_p.add_argument("--html", metavar="PATH",
                       help="write a self-contained HTML comparison")
    cmp_p.add_argument("--charts", metavar="DIR",
                       help="write each chart as a standalone .svg")
    cmp_p.add_argument(
        "--csv", metavar="DIR",
        help="write arms.csv, params.csv and rows.csv into this directory "
             "(unlike `report --csv`, which dumps one table to stdout)")
    cmp_p.add_argument(
        "--allow-cross-world", action="store_true",
        help="exit 0 even when a pooling boundary is broken")
    cmp_p.set_defaults(func=cmd_compare)

    doc_p = sub.add_parser("doctor",
                           help="check this machine can run harness, and say "
                                "what each missing piece blocks")
    doc_p.set_defaults(func=cmd_doctor)

    sc_p = sub.add_parser("scaffold",
                          help="draft a task pack from a live MCP server or an OpenAPI doc")
    sc_p.add_argument("source", help="MCP URL, OpenAPI URL, or OpenAPI file")
    sc_p.add_argument("-o", "--out", type=Path, help="write here instead of stdout")
    sc_p.add_argument("--id", default="my-api", help="pack id")
    sc_p.add_argument("--no-mcp", dest="mcp", action="store_false",
                      help="treat an http source as OpenAPI, not an MCP server")
    sc_p.set_defaults(func=cmd_scaffold)

    gen_p = sub.add_parser("generate", help="OpenAPI → materials bundle (field/onboarding)")
    gen_sub = gen_p.add_subparsers(dest="generate_command", required=True)

    gen_an = gen_sub.add_parser("analyze", help="lint spec → workspace analyze.json")
    gen_an.add_argument("spec", type=Path)
    gen_an.add_argument("-o", "--out", type=Path, required=True,
                        help="generate workspace directory")
    gen_an.add_argument("--job-id", default=None)
    gen_an.set_defaults(func=cmd_generate_analyze)

    gen_mat = gen_sub.add_parser("materials", help="mechanical tools/docs/code → materials/")
    gen_mat.add_argument("spec", type=Path,
                         help="OpenAPI file (or ignored if workspace has spec/)")
    gen_mat.add_argument("-o", "--out", type=Path, required=True)
    gen_mat.add_argument("--job-id", default=None)
    gen_mat.add_argument("--doc-budget", default="standard",
                         choices=[c.value for c in DocBudget])
    gen_mat.add_argument("--presets", nargs="*", default=None)
    gen_mat.set_defaults(func=cmd_generate_materials)

    gen_en = gen_sub.add_parser("enrich", help="heuristic/LLM enrich → enriched spec + authored skill")
    gen_en.add_argument("spec", type=Path, nargs="?", default=None,
                        help="OpenAPI file (or use --config)")
    gen_en.add_argument("-o", "--out", type=Path, default=None,
                        help="workspace (required without --config)")
    gen_en.add_argument("--config", type=Path, default=None)
    gen_en.add_argument("--job-id", default=None)
    gen_en.add_argument("--model", default=None, help="enable LLM enrich with this model")
    gen_en.add_argument("--max-usd", type=float, default=2.0)
    gen_en.add_argument("--yes", action="store_true")
    gen_en.set_defaults(func=cmd_generate_enrich)

    gen_run = gen_sub.add_parser("run", help="run phases from generate.config.yaml")
    gen_run.add_argument("config", type=Path)
    gen_run.add_argument("--yes", action="store_true",
                         help="skip confirmation (required for unattended/BE)")
    gen_run.set_defaults(func=cmd_generate_run)

    gen_fix = gen_sub.add_parser("fixtures", help="capture staging read fixtures")
    gen_fix.add_argument("config", type=Path)
    gen_fix.add_argument("--yes", action="store_true")
    gen_fix.set_defaults(func=cmd_generate_fixtures)

    gen_pack = gen_sub.add_parser("pack", help="build graded pack from fixtures")
    gen_pack.add_argument("config", type=Path)
    gen_pack.add_argument("--yes", action="store_true")
    gen_pack.set_defaults(func=cmd_generate_pack)

    mock_p = sub.add_parser(
        "mock",
        help="local OpenAPI HTTP stub + MCP gateway (no customer staging URL)",
    )
    mock_sub = mock_p.add_subparsers(dest="mock_command", required=True)
    mock_serve = mock_sub.add_parser(
        "serve",
        help="bind HTTP mock + MCP gateway; print MOCK_READY JSON line",
    )
    mock_serve.add_argument("--spec", type=Path, required=True)
    mock_serve.add_argument("--host", default="127.0.0.1")
    mock_serve.add_argument("--http-port", type=int, default=0)
    mock_serve.add_argument("--mcp-port", type=int, default=0)
    mock_serve.set_defaults(func=cmd_mock_serve)

    init_p = sub.add_parser("init",
                            help="install the agent skills into this project")
    init_p.add_argument("--agent", default="both",
                        choices=["claude", "cursor", "both"])
    init_p.add_argument("--dir", type=Path, default=Path("."))
    init_p.add_argument("--force", action="store_true",
                        help="overwrite skills that are already there")
    init_p.set_defaults(func=cmd_init)

    tr_p = sub.add_parser("transcript",
                          help="replay a stored run: messages, calls, results")
    tr_p.add_argument("trace", type=Path,
                      help="a trace .json, or a traces/ directory")
    tr_p.add_argument("--limit", type=int, default=1,
                      help="how many traces to render from a directory")
    tr_p.add_argument("--pretty", action="store_true",
                      help="showcase layout (same as live --stream): unwrap "
                           "MCP envelopes, key/value args, highlight answers")
    tr_p.add_argument("--verbose", action="store_true",
                      help="with --pretty: expand collapsed preamble, packaging "
                           "material, and truncated code blocks")
    tr_p.set_defaults(func=cmd_transcript)

    arms_p = sub.add_parser("arms", help="list resolved arms (axes, method, description)")
    arms_p.add_argument("--plan", type=Path,
                        help="resolve arms for this plan's base + include")
    arms_p.set_defaults(func=cmd_arms)

    plan_p = sub.add_parser("plan", help="cost projection and approval")
    plan_p.add_argument("plan", type=Path)
    plan_p.add_argument("--approve", action="store_true")
    plan_p.add_argument("--explain", action="store_true",
                        help="print the resolved matrix and per-arm summary")
    plan_p.add_argument("--strict", action="store_true",
                        help="require a pre-registered confirmatory/exploratory split")
    plan_p.set_defaults(func=cmd_plan)

    exp_p = sub.add_parser("experiment", help="experiment sidecar lifecycle")
    exp_sub = exp_p.add_subparsers(dest="experiment_command", required=True)

    exp_init = exp_sub.add_parser("init", help="write experiment.yaml from a plan")
    exp_init.add_argument("plan", type=Path)
    exp_init.add_argument("--out", type=Path, required=True)
    exp_init.set_defaults(func=cmd_experiment_init)

    exp_show = exp_sub.add_parser("show", help="JSON envelope for adapter/UI")
    exp_show.add_argument("dir", type=Path)
    exp_show.add_argument("--slice")
    exp_show.set_defaults(func=cmd_experiment_show)

    exp_arm = exp_sub.add_parser("arm", help="mutate declared arms")
    exp_arm_sub = exp_arm.add_subparsers(dest="arm_command", required=True)
    exp_arm_add = exp_arm_sub.add_parser("add", help="append presets to declaration")
    exp_arm_add.add_argument("dir", type=Path)
    exp_arm_add.add_argument("presets", nargs="+")
    exp_arm_add.set_defaults(func=cmd_experiment_arm_add)

    exp_status = exp_sub.add_parser("status", help="coverage summary")
    exp_status.add_argument("dir", type=Path)
    exp_status.add_argument("--slice")
    exp_status.set_defaults(func=cmd_experiment_status)

    exp_run = exp_sub.add_parser("run", help="run missing cells only")
    exp_run.add_argument("dir", type=Path)
    exp_run.add_argument("--slice")
    exp_run.add_argument("--yes", action="store_true")
    exp_run.add_argument("--concurrency", type=int, default=16)
    exp_run.add_argument("--disk-reserve-gb", type=float, default=None, metavar="GB")
    exp_run.set_defaults(func=cmd_experiment_run)

    exp_snap = exp_sub.add_parser("snapshot", help="freeze a dated report snapshot")
    exp_snap.add_argument("dir", type=Path)
    exp_snap.set_defaults(func=cmd_experiment_snapshot)

    for sp in (plan_p, run_p):
        sp.add_argument("--provider", default="openai")
        sp.add_argument("--model", default="gpt-5.6-luna")
        sp.add_argument("--reasoning-effort", default="low")
        sp.add_argument("--temperature", type=float, default=0.0)
        sp.add_argument("--caching", default="off", choices=[c.value for c in Caching])
        sp.add_argument("--repeats", type=int, default=1)
        sp.add_argument("--surface-size", type=int, default=0)
        sp.add_argument("--schema-detail", default="standard",
                        choices=[c.value for c in SchemaDetail])
        sp.add_argument("--response-shape", default="as-is",
                        choices=[c.value for c in ResponseShape])
        sp.add_argument("--error-detail", default="field-scoped",
                        choices=[c.value for c in ErrorDetail])
        sp.add_argument("--doc-budget", default="standard",
                        choices=[c.value for c in DocBudget])
        sp.add_argument("--mcp-revision", default="2026-07-28",
                        choices=[c.value for c in McpRevision])
    return p


def main(argv: list[str] | None = None) -> int:
    from .engine.env import find_and_load
    loaded = find_and_load()
    if loaded:
        # Names only. Reporting which credentials are in play is useful;
        # printing their values would put secrets in every terminal scrollback.
        print(f"loaded from .env: {', '.join(loaded)}", file=sys.stderr)

    _OPERATOR_ERRORS = _operator_errors()
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except _OPERATOR_ERRORS as e:
        # These already carry the whole explanation — an unknown model names the
        # env var that would price it, a bad pack names the field. Wrapping that
        # in a traceback buries the one useful line under twenty that are not.
        # Shares the infra exit code: both mean "fix the setup, nothing ran".
        print(f"\n{e}", file=sys.stderr)
        return _EXIT_INFRA


if __name__ == "__main__":
    raise SystemExit(main())
